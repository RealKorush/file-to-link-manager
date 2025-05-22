import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
import config # فرض بر این است که فایل config.py شما موجود و صحیح است
import liara_s3_utils # فرض بر این است که فایل liara_s3_utils.py شما موجود و صحیح است

# فعال کردن لاگ‌گیری
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# وضعیت‌های مکالمه (برای مدیریت انتخاب سرور و فایل) - اگر از ConversationHandler استفاده می‌کنید
# در این نسخه ساده شده، از user_data برای نگهداری وضعیت استفاده می‌کنیم
CHOOSING_SERVER, CHOOSING_ACTION, RENAMING_FILE = range(3) # اینها برای ConversationHandler مناسب‌ترند
# داده‌های کاربر برای نگهداری انتخاب‌ها
user_data = {}


# --- تابع محدود کننده دسترسی به ادمین ---
def restricted(func):
    async def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id != config.SUPER_ADMIN_USER_ID:
            # اگر پیام از طرف کاربر غیر ادمین بود و message داشت (نه callback_query)
            if update.message:
                await update.message.reply_text("شما اجازه دسترسی به این ربات را ندارید.")
            # اگر callback_query بود، با یک answer می‌توان به کاربر اطلاع داد (اختیاری)
            elif update.callback_query:
                await update.callback_query.answer("عدم دسترسی", show_alert=True)
            return
        return await func(update, context, *args, **kwargs)
    return wrapped


# --- دستورات ربات ---
@restricted
async def start_command(update: Update, context: CallbackContext) -> None:
    """دستور /start برای نمایش سرورها"""
    user_id = update.effective_user.id
    user_data[user_id] = {} # ریست کردن داده‌های کاربر هنگام شروع مجدد

    keyboard = []
    for server_name_key in config.SERVERS.keys(): # استفاده از server_name_key برای وضوح
        keyboard.append([InlineKeyboardButton(server_name_key.capitalize(), callback_data=f"server_{server_name_key}")])
    keyboard.append([InlineKeyboardButton("📊 آمار کلی سرورها", callback_data="stats_all_servers")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("سلام! لطفاً یک سرور را انتخاب کنید یا آمار کلی را مشاهده کنید:", reply_markup=reply_markup)
    # return CHOOSING_SERVER # برای ConversationHandler


async def show_server_files(update: Update, context: CallbackContext, server_name: str) -> None:
    """نمایش فایل‌های یک سرور و آمار آن"""
    query = update.callback_query # این می‌تواند None باشد اگر تابع از جای دیگری فراخوانی شود
    user_id = update.effective_user.id

    if user_id not in user_data: # اطمینان از وجود user_data
        user_data[user_id] = {}

    user_data[user_id]['current_server'] = server_name
    server_info = config.SERVERS.get(server_name)

    # تعیین اینکه پیام باید ویرایش شود یا پیام جدید ارسال شود
    reply_method = query.edit_message_text if query else context.bot.send_message
    chat_id_to_reply = query.message.chat_id if query else update.message.chat_id


    if not server_info:
        await reply_method(text="سرور نامعتبر است." if query else "سرور نامعتبر است.", chat_id=chat_id_to_reply if not query else None)
        return # بازگشت به منوی اصلی یا وضعیت قبلی لازم است

    s3_client = liara_s3_utils.get_s3_client(
        server_info["access_key"],
        server_info["secret_key"],
        server_info["endpoint_url"],
        server_info.get("region_name")
    )

    if not s3_client:
        await reply_method(text="خطا در اتصال به سرور." if query else "خطا در اتصال به سرور.", chat_id=chat_id_to_reply if not query else None)
        return

    # دریافت آمار سرور
    usage_stats = liara_s3_utils.get_bucket_usage(s3_client, server_info["bucket"], config.SERVER_CAPACITY_GB)
    stats_message = (
        f"📊 آمار سرور {server_name.capitalize()}:\n"
        f"استفاده شده: {usage_stats['used_gb']} گیگابایت ({usage_stats['file_count']} فایل)\n"
        f"فضای خالی: {usage_stats['free_gb']} گیگابایت (از {usage_stats['total_gb']} گیگابایت)"
    )

    files = liara_s3_utils.list_files(s3_client, server_info["bucket"])
    user_data[user_id]['files'] = {file_item['name']: file_item for file_item in files} # ذخیره فایل‌ها

    keyboard = []
    skipped_files_count = 0
    if files:
        for file_item in files:
            file_name_original = file_item['name']
            file_size_mb = round(file_item['size'] / (1024 * 1024), 2)

            # کوتاه کردن نام فایل برای نمایش در دکمه اگر خیلی طولانی است
            display_file_name = file_name_original
            if len(display_file_name) > 30: # مثال: حداکثر 30 کاراکتر برای نام در دکمه
                 display_file_name = display_file_name[:27] + "..."

            button_text = f"{display_file_name} ({file_size_mb} MB)"
            full_callback_data = f"file_{file_name_original}" # استفاده از نام کامل و اصلی برای callback_data
            callback_data_bytes = len(full_callback_data.encode('utf-8'))

            logger.info(
                f"دکمه برای فایل: '{file_name_original}', "
                f"متن دکمه: '{button_text}', "
                f"callback_data: '{full_callback_data}', "
                f"طول callback_data (بایت): {callback_data_bytes}"
            )

            if callback_data_bytes > 64:
                skipped_files_count += 1
                logger.error(
                    f"خطا: callback_data برای فایل '{file_name_original}' در سرور '{server_name}' بیش از حد طولانی است "
                    f"({callback_data_bytes} بایت). این دکمه ایجاد نخواهد شد."
                )
                # ارسال پیام به ادمین در مورد فایل رد شده
                # این پیام در چت با ربات ارسال می‌شود
                await context.bot.send_message(
                    chat_id=user_id, # ارسال به کاربر ادمین
                    text=f"⚠️ فایل '{file_name_original}' در سرور '{server_name.capitalize()}' به دلیل نام بسیار طولانی (callback_data با بیش از 64 بایت) در لیست دکمه‌ها نمایش داده نشد."
                )
                continue # از ایجاد این دکمه صرف نظر کن

            keyboard.append([InlineKeyboardButton(button_text, callback_data=full_callback_data)])
    
    if skipped_files_count > 0:
        stats_message += f"\n\n⚠️ {skipped_files_count} فایل به دلیل نام طولانی در لیست دکمه‌ها نمایش داده نشدند (اطلاعات در پیام جداگانه)."


    if not files and skipped_files_count == 0: # اگر هیچ فایلی نبود و هیچ فایلی هم skip نشده بود
        stats_message += "\n\nهیچ فایلی در این سرور یافت نشد."
    elif not keyboard and skipped_files_count > 0: # اگر همه فایل‌ها skip شده بودند
         stats_message += "\n\nهمه فایل‌های موجود به دلیل نام طولانی قابل نمایش در دکمه‌ها نبودند."


    keyboard.append([InlineKeyboardButton("بازگشت به لیست سرورها", callback_data="back_to_servers")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    message_text = f"{stats_message}\n\nفایل‌های سرور {server_name.capitalize()}:"

    if query:
        try:
            await query.edit_message_text(text=message_text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"خطا در ویرایش پیام (show_server_files): {e}")
            # اگر ویرایش ناموفق بود (مثلا پیام تغییر نکرده)، پیام جدید بفرست
            await context.bot.send_message(chat_id=chat_id_to_reply, text=message_text, reply_markup=reply_markup)
    else:
        await context.bot.send_message(chat_id=chat_id_to_reply, text=message_text, reply_markup=reply_markup)

    # return CHOOSING_ACTION # برای ConversationHandler


async def handle_all_server_stats(update: Update, context: CallbackContext) -> None:
    """نمایش آمار همه سرورها"""
    query = update.callback_query
    await query.answer()

    full_stats_message = "📊 آمار کلی سرورها:\n\n"
    total_used_gb_all = 0
    total_capacity_gb_all = 0
    total_files_all = 0

    for server_name_key, server_info_val in config.SERVERS.items():
        s3_client = liara_s3_utils.get_s3_client(
            server_info_val["access_key"],
            server_info_val["secret_key"],
            server_info_val["endpoint_url"],
            server_info_val.get("region_name")
        )
        if s3_client:
            usage = liara_s3_utils.get_bucket_usage(s3_client, server_info_val["bucket"], config.SERVER_CAPACITY_GB)
            full_stats_message += (
                f"🔸 سرور {server_name_key.capitalize()}:\n"
                f"   - استفاده شده: {usage['used_gb']} / {usage['total_gb']} گیگابایت\n"
                f"   - تعداد فایل‌ها: {usage['file_count']}\n\n"
            )
            total_used_gb_all += usage['used_gb']
            total_capacity_gb_all += usage['total_gb']
            total_files_all += usage['file_count']
        else:
            full_stats_message += f"🔸 سرور {server_name_key.capitalize()}: خطا در اتصال یا دریافت آمار\n\n"

    overall_free_gb_all = total_capacity_gb_all - total_used_gb_all
    full_stats_message += (
        f"جمع کل:\n"
        f"   - کل فضای استفاده شده: {round(total_used_gb_all, 2)} گیگابایت\n"
        f"   - کل ظرفیت: {round(total_capacity_gb_all, 2)} گیگابایت\n"
        f"   - کل فضای خالی: {round(overall_free_gb_all, 2)} گیگابایت\n"
        f"   - کل تعداد فایل‌ها: {total_files_all}"
    )

    keyboard = [[InlineKeyboardButton("بازگشت به لیست سرورها", callback_data="back_to_servers")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=full_stats_message, reply_markup=reply_markup)
    # return CHOOSING_SERVER # برای ConversationHandler


async def button_callback_handler(update: Update, context: CallbackContext) -> None:
    """مدیریت دکمه‌های inline"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    if user_id not in user_data: # اطمینان از وجود user_data
        user_data[user_id] = {}

    callback_data = query.data
    logger.info(f"Callback received: {callback_data} from user {user_id}")


    if callback_data == "back_to_servers":
        keyboard_main = []
        for server_name_key in config.SERVERS.keys():
            keyboard_main.append([InlineKeyboardButton(server_name_key.capitalize(), callback_data=f"server_{server_name_key}")])
        keyboard_main.append([InlineKeyboardButton("📊 آمار کلی سرورها", callback_data="stats_all_servers")])
        reply_markup_main = InlineKeyboardMarkup(keyboard_main)
        try:
            await query.edit_message_text("لطفاً یک سرور را انتخاب کنید یا آمار کلی را مشاهده کنید:", reply_markup=reply_markup_main)
        except Exception as e: # اگر ویرایش ممکن نبود (مثلا پیام خیلی قدیمی است یا محتوا یکسان است)
            logger.warning(f"Failed to edit message for back_to_servers, sending new one: {e}")
            await context.bot.send_message(chat_id=query.message.chat_id, text="لطفاً یک سرور را انتخاب کنید یا آمار کلی را مشاهده کنید:", reply_markup=reply_markup_main)

        user_data[user_id].pop('current_server', None) # پاک کردن سرور فعلی
        user_data[user_id].pop('selected_file', None) # پاک کردن فایل انتخابی
        user_data[user_id].pop('file_to_rename', None) # پاک کردن فایل در حال تغییر نام
        # return CHOOSING_SERVER

    elif callback_data.startswith("server_"):
        server_name_selected = callback_data[len("server_"):]
        await show_server_files(update, context, server_name_selected)
        # return CHOOSING_ACTION

    elif callback_data == "stats_all_servers":
        await handle_all_server_stats(update, context)
        # return CHOOSING_SERVER


    elif callback_data.startswith("file_"):
        file_key_selected = callback_data[len("file_"):]
        user_data[user_id]['selected_file'] = file_key_selected
        current_server_name = user_data[user_id].get('current_server')

        if not current_server_name:
            await query.edit_message_text("خطا: سرور فعلی مشخص نیست. لطفاً با دستور /start مجددا شروع کنید.")
            return

        # کوتاه کردن نام فایل برای نمایش در پیام
        display_file_key = file_key_selected
        if len(display_file_key) > 40:
            display_file_key = display_file_key[:37] + "..."


        keyboard_actions = [
            [InlineKeyboardButton(f"🔗 لینک دانلود", callback_data=f"getlink_{file_key_selected}")],
            [InlineKeyboardButton(f"✏️ تغییر نام", callback_data=f"rename_{file_key_selected}")],
            [InlineKeyboardButton(f"🗑️ حذف", callback_data=f"delete_{file_key_selected}")],
            [InlineKeyboardButton(f"بازگشت به فایل‌های سرور {current_server_name.capitalize()}", callback_data=f"server_{current_server_name}")]
        ]
        reply_markup_actions = InlineKeyboardMarkup(keyboard_actions)
        await query.edit_message_text(f"فایل: '{display_file_key}'\nسرور: {current_server_name.capitalize()}\n\nعملیات مورد نظر را انتخاب کنید:", reply_markup=reply_markup_actions)
        # return CHOOSING_ACTION


    elif callback_data.startswith("delete_"):
        file_to_delete = callback_data[len("delete_"):]
        # تاییدیه حذف
        keyboard_confirm = [
            [InlineKeyboardButton(f"✅ بله، حذف کن", callback_data=f"confirmdelete_{file_to_delete}")],
            [InlineKeyboardButton(f"❌ انصراف", callback_data=f"file_{file_to_delete}")]
        ]
        reply_markup_confirm = InlineKeyboardMarkup(keyboard_confirm)
        await query.edit_message_text(f"آیا از حذف فایل '{file_to_delete}' مطمئن هستید؟", reply_markup=reply_markup_confirm)
        # return CHOOSING_ACTION


    elif callback_data.startswith("confirmdelete_"):
        file_to_delete_confirmed = callback_data[len("confirmdelete_"):]
        server_name_of_file = user_data[user_id].get('current_server')
        server_info_of_file = config.SERVERS[server_name_of_file]

        s3_client_del = liara_s3_utils.get_s3_client(
            server_info_of_file["access_key"], server_info_of_file["secret_key"], server_info_of_file["endpoint_url"], server_info_of_file.get("region_name")
        )
        if s3_client_del and liara_s3_utils.delete_file(s3_client_del, server_info_of_file["bucket"], file_to_delete_confirmed):
            await query.edit_message_text(f"فایل '{file_to_delete_confirmed}' با موفقیت حذف شد.")
        else:
            await query.edit_message_text(f"خطا در حذف فایل '{file_to_delete_confirmed}'.")

        await show_server_files(update, context, server_name_of_file) # نمایش مجدد فایل‌ها
        # return CHOOSING_ACTION


    elif callback_data.startswith("getlink_"):
        file_to_link = callback_data[len("getlink_"):]
        server_name_for_link = user_data[user_id].get('current_server')
        server_info_for_link = config.SERVERS[server_name_for_link]
        s3_client_link = liara_s3_utils.get_s3_client(
            server_info_for_link["access_key"], server_info_for_link["secret_key"], server_info_for_link["endpoint_url"], server_info_for_link.get("region_name")
        )
        if s3_client_link:
            link = liara_s3_utils.get_download_link(s3_client_link, server_info_for_link["bucket"], file_to_link)
            if link:
                # پیام قبلی را ویرایش نمی‌کنیم، لینک را در پیام جدید می‌فرستیم
                await query.message.reply_text(f"لینک دانلود برای '{file_to_link}':\n`{link}`", parse_mode='MarkdownV2')
                # await query.answer("لینک دانلود ارسال شد.") # یک نوتیفیکیشن کوچک به کاربر
            else:
                await query.edit_message_text("خطا در ایجاد لینک دانلود.")
        else:
            await query.edit_message_text("خطا در اتصال به سرور برای دریافت لینک.")
        # کاربر همچنان در مرحله انتخاب عملیات برای فایل است، پس صفحه کلید قبلی را دست نمی‌زنیم
        # مگر اینکه بخواهیم به لیست فایل‌ها برگردیم. در اینجا، کاربر باید خودش بازگشت را بزند.
        # return CHOOSING_ACTION


    elif callback_data.startswith("rename_"):
        file_to_rename_original = callback_data[len("rename_"):]
        user_data[user_id]['file_to_rename'] = file_to_rename_original # ذخیره نام فایل اصلی
        user_data[user_id]['renaming_in_progress'] = True # یک فلگ برای handle_rename_message
        await query.edit_message_text(f"نام فعلی: '{file_to_rename_original}'.\nلطفاً نام جدید را ارسال کنید:")
        # return RENAMING_FILE

    # ... سایر بخش‌های button_callback_handler


@restricted
async def handle_rename_message(update: Update, context: CallbackContext) -> None:
    """دریافت نام جدید فایل و انجام تغییر نام (فقط اگر renaming_in_progress ست شده باشد)"""
    user_id = update.effective_user.id

    # بررسی اینکه آیا واقعا در فرآیند تغییر نام هستیم
    if not user_data.get(user_id, {}).get('renaming_in_progress', False):
        # اگر کاربر متنی فرستاد و انتظار تغییر نام نداشتیم، آن را نادیده می‌گیریم
        # یا یک پیام راهنما ارسال می‌کنیم که از /start استفاده کند
        # logger.info(f"Received unexpected text from user {user_id} while not in renaming state: {update.message.text}")
        return

    new_file_key = update.message.text.strip()
    old_file_key = user_data[user_id].get('file_to_rename')
    current_server_name_for_rename = user_data[user_id].get('current_server')

    # پاک کردن فلگ تغییر نام در هر صورت
    user_data[user_id].pop('renaming_in_progress', None)


    if not old_file_key or not current_server_name_for_rename:
        await update.message.reply_text("خطا: اطلاعات لازم برای تغییر نام موجود نیست. لطفاً دوباره از لیست فایل‌ها اقدام کنید.")
        # await start_command(update, context) # یا بازگشت به لیست سرورها
        return

    if not new_file_key:
        await update.message.reply_text("نام فایل نمی‌تواند خالی باشد. لطفاً نام جدید را ارسال کنید یا برای لغو، عملیات دیگری انتخاب کنید.")
        # بازگرداندن کاربر به منوی عملیات فایل قبلی
        # این بخش نیاز به بازسازی دکمه‌های قبلی دارد
        user_data[user_id]['renaming_in_progress'] = True # دوباره فلگ را ست می‌کنیم تا بتواند دوباره تلاش کند
        await update.message.reply_text(f"نام فعلی: '{old_file_key}'.\nلطفاً نام جدید را ارسال کنید (یا برای لغو، از دکمه بازگشت قبلی استفاده کنید اگر هنوز موجود است):")

        return

    if "/" in new_file_key or "\\" in new_file_key:
        await update.message.reply_text("نام فایل نمی‌تواند شامل '/' یا '\\' باشد. لطفاً نام دیگری انتخاب کنید:")
        user_data[user_id]['renaming_in_progress'] = True # دوباره فلگ را ست می‌کنیم
        await update.message.reply_text(f"نام فعلی: '{old_file_key}'.\nلطفاً نام جدید را ارسال کنید:")
        return

    server_info_rename = config.SERVERS[current_server_name_for_rename]
    s3_client_rename = liara_s3_utils.get_s3_client(
        server_info_rename["access_key"], server_info_rename["secret_key"], server_info_rename["endpoint_url"], server_info_rename.get("region_name")
    )

    if s3_client_rename:
        if liara_s3_utils.rename_file(s3_client_rename, server_info_rename["bucket"], old_file_key, new_file_key):
            await update.message.reply_text(f"نام فایل '{old_file_key}' با موفقیت به '{new_file_key}' تغییر یافت.")
            user_data[user_id].pop('file_to_rename', None)
            # نمایش مجدد فایل‌های سرور با نام جدید
            # چون show_server_files انتظار query دارد و اینجا نداریم، باید آن را تطبیق دهیم
            # یا یک wrapper بسازیم. برای سادگی، پیام می‌دهیم و از کاربر می‌خواهیم بازگردد.
            # await show_server_files(update, context, current_server_name_for_rename) # این کار نخواهد کرد چون update اینجا Message است
            # یک راه حل ساده:
            await context.bot.send_message(chat_id=user_id, text=f"لیست فایل‌های سرور {current_server_name_for_rename.capitalize()} به‌روز شد. برای مشاهده، لطفاً سرور را مجدداً انتخاب کنید یا از دکمه بازگشت استفاده نمایید.")
            # ایده بهتر: show_server_files را طوری بازنویسی کنیم که هم با query و هم بدون آن کار کند
            # یا یک پیام با دکمه "نمایش مجدد فایل‌ها" بفرستیم.
            # فعلا، کاربر باید دستی به لیست فایل‌ها برگردد یا از /start استفاده کند.

        else:
            await update.message.reply_text(f"خطا در تغییر نام فایل '{old_file_key}'. ممکن است نام جدید تکراری باشد یا خطایی رخ داده باشد.")
            # بازگرداندن کاربر به منوی قبلی (عملیات روی فایل)
            # این بخش هم نیاز به بازسازی دکمه‌های آن مرحله دارد
            await context.bot.send_message(chat_id=user_id, text="لطفاً برای ادامه، فایل مورد نظر را مجددا از لیست انتخاب کنید.")

    else:
        await update.message.reply_text("خطا در اتصال به سرور برای تغییر نام.")
        # await start_command(update, context)
    # return CHOOSING_ACTION (بستگی به طراحی ConversationHandler دارد)


def main() -> None:
    """ربات را راه‌اندازی می‌کند."""
    application = Application.builder().token(config.BOT_TOKEN).build()

    # استفاده از ConversationHandler برای مدیریت بهتر وضعیت‌ها توصیه می‌شود.
    # در این نسخه ساده‌شده، از CallbackQueryHandler و MessageHandler به صورت جداگانه استفاده می‌کنیم.

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(button_callback_handler))

    # این MessageHandler برای دریافت نام جدید فایل است.
    # مهم: این هندلر باید فقط زمانی فعال شود که کاربر در وضعیت تغییر نام است.
    # فیلتر Chat(config.SUPER_ADMIN_USER_ID) تضمین می‌کند که فقط ادمین می‌تواند این پیام‌ها را بفرستد.
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(config.SUPER_ADMIN_USER_ID), handle_rename_message))


    logger.info("ربات در حال اجراست...")
    application.run_polling()


if __name__ == "__main__":
    main()
