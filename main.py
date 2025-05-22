import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
import config
import liara_s3_utils

# فعال کردن لاگ‌گیری
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# وضعیت‌های مکالمه (برای مدیریت انتخاب سرور و فایل)
CHOOSING_SERVER, CHOOSING_ACTION, RENAMING_FILE = range(3)
# داده‌های کاربر برای نگهداری انتخاب‌ها
user_data = {}


# --- تابع محدود کننده دسترسی به ادمین ---
def restricted(func):
    async def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id != config.SUPER_ADMIN_USER_ID:
            await update.message.reply_text("شما اجازه دسترسی به این ربات را ندارید.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped


# --- دستورات ربات ---
@restricted
async def start_command(update: Update, context: CallbackContext) -> None:
    """دستور /start برای نمایش سرورها"""
    user_id = update.effective_user.id
    user_data[user_id] = {} # ریست کردن داده‌های کاربر

    keyboard = []
    for server_name in config.SERVERS.keys():
        keyboard.append([InlineKeyboardButton(server_name.capitalize(), callback_data=f"server_{server_name}")])
    keyboard.append([InlineKeyboardButton("📊 آمار کلی سرورها", callback_data="stats_all_servers")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("لطفاً یک سرور را انتخاب کنید یا آمار کلی را مشاهده کنید:", reply_markup=reply_markup)
    return CHOOSING_SERVER

async def show_server_files(update: Update, context: CallbackContext, server_name: str) -> None:
    """نمایش فایل‌های یک سرور و آمار آن"""
    query = update.callback_query
    if query: # اگر از دکمه inline آمده است
        await query.answer()

    user_id = update.effective_user.id
    user_data[user_id]['current_server'] = server_name
    server_info = config.SERVERS.get(server_name)

    if not server_info:
        await (query.edit_message_text if query else update.message.reply_text)("سرور نامعتبر است.")
        return CHOOSING_SERVER

    s3_client = liara_s3_utils.get_s3_client(
        server_info["access_key"],
        server_info["secret_key"],
        server_info["endpoint_url"],
        server_info.get("region_name")
    )

    if not s3_client:
        await (query.edit_message_text if query else update.message.reply_text)("خطا در اتصال به سرور.")
        return CHOOSING_SERVER

    # دریافت آمار سرور
    usage_stats = liara_s3_utils.get_bucket_usage(s3_client, server_info["bucket"], config.SERVER_CAPACITY_GB)
    stats_message = (
        f"📊 آمار سرور {server_name.capitalize()}:\n"
        f"استفاده شده: {usage_stats['used_gb']} گیگابایت\n"
        f"فضای خالی: {usage_stats['free_gb']} گیگابایت\n"
        f"تعداد فایل‌ها: {usage_stats['file_count']}"
    )

    files = liara_s3_utils.list_files(s3_client, server_info["bucket"])
    user_data[user_id]['files'] = {file['name']: file for file in files} # ذخیره فایل‌ها برای دسترسی سریع

    keyboard = []
    if files:
        for file in files:
            # نمایش نام فایل و در پرانتز حجم آن به مگابایت
            file_size_mb = round(file['size'] / (1024 * 1024), 2)
            keyboard.append([InlineKeyboardButton(f"{file['name']} ({file_size_mb} MB)", callback_data=f"file_{file['name']}")])
    else:
        stats_message += "\n\nهیچ فایلی در این سرور یافت نشد."

    keyboard.append([InlineKeyboardButton("بازگشت به لیست سرورها", callback_data="back_to_servers")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    message_text = f"{stats_message}\n\nفایل‌های سرور {server_name.capitalize()}:"
    if query:
        await query.edit_message_text(text=message_text, reply_markup=reply_markup)
    else: # اگر مستقیم به این تابع آمده باشیم (مثلا بعد از تغییر نام)
        await update.message.reply_text(text=message_text, reply_markup=reply_markup)

    return CHOOSING_ACTION


async def handle_all_server_stats(update: Update, context: CallbackContext) -> None:
    """نمایش آمار همه سرورها"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    full_stats_message = "📊 آمار کلی سرورها:\n\n"
    total_used_gb = 0
    total_capacity_gb = 0

    for server_name, server_info in config.SERVERS.items():
        s3_client = liara_s3_utils.get_s3_client(
            server_info["access_key"],
            server_info["secret_key"],
            server_info["endpoint_url"],
            server_info.get("region_name")
        )
        if s3_client:
            usage = liara_s3_utils.get_bucket_usage(s3_client, server_info["bucket"], config.SERVER_CAPACITY_GB)
            full_stats_message += (
                f"🔸 سرور {server_name.capitalize()}:\n"
                f"   - استفاده شده: {usage['used_gb']} / {usage['total_gb']} گیگابایت\n"
                f"   - تعداد فایل‌ها: {usage['file_count']}\n\n"
            )
            total_used_gb += usage['used_gb']
            total_capacity_gb += usage['total_gb']
        else:
            full_stats_message += f"🔸 سرور {server_name.capitalize()}: خطا در اتصال\n\n"

    overall_free_gb = total_capacity_gb - total_used_gb
    full_stats_message += (
        f"جمع کل:\n"
        f"   - کل فضای استفاده شده: {round(total_used_gb, 2)} گیگابایت\n"
        f"   - کل ظرفیت: {round(total_capacity_gb, 2)} گیگابایت\n"
        f"   - کل فضای خالی: {round(overall_free_gb, 2)} گیگابایت"
    )

    keyboard = [[InlineKeyboardButton("بازگشت به لیست سرورها", callback_data="back_to_servers")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=full_stats_message, reply_markup=reply_markup)
    return CHOOSING_SERVER


async def button_callback_handler(update: Update, context: CallbackContext) -> None:
    """مدیریت دکمه‌های inline"""
    query = update.callback_query
    await query.answer() # مهم: برای اینکه تلگرام بفهمد به کلیک پاسخ داده شده
    user_id = update.effective_user.id

    # اطمینان از وجود user_data[user_id]
    if user_id not in user_data:
        user_data[user_id] = {}

    callback_data = query.data

    if callback_data == "back_to_servers":
        # استفاده از context.bot به جای update.message برای ارسال پیام جدید یا ویرایش
        keyboard = []
        for server_name_key in config.SERVERS.keys():
            keyboard.append([InlineKeyboardButton(server_name_key.capitalize(), callback_data=f"server_{server_name_key}")])
        keyboard.append([InlineKeyboardButton("📊 آمار کلی سرورها", callback_data="stats_all_servers")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("لطفاً یک سرور را انتخاب کنید یا آمار کلی را مشاهده کنید:", reply_markup=reply_markup)
        return CHOOSING_SERVER

    elif callback_data.startswith("server_"):
        server_name = callback_data.split("_")[1]
        await show_server_files(update, context, server_name)
        return CHOOSING_ACTION

    elif callback_data == "stats_all_servers":
        await handle_all_server_stats(update, context)
        return CHOOSING_SERVER


    elif callback_data.startswith("file_"):
        file_key = callback_data[len("file_"):] # جدا کردن نام فایل از callback_data
        user_data[user_id]['selected_file'] = file_key
        server_name = user_data[user_id].get('current_server')

        if not server_name:
            await query.edit_message_text("خطا: سرور فعلی مشخص نیست. لطفاً از ابتدا شروع کنید.")
            # اینجا باید کاربر را به مرحله انتخاب سرور برگردانید
            # برای سادگی، فعلا فقط پیام خطا می‌دهیم
            return CHOOSING_SERVER # یا یک وضعیت خطای دیگر

        keyboard = [
            [InlineKeyboardButton(f"🔗 دریافت لینک دانلود", callback_data=f"getlink_{file_key}")],
            [InlineKeyboardButton(f"✏️ تغییر نام", callback_data=f"rename_{file_key}")],
            [InlineKeyboardButton(f"🗑️ حذف فایل", callback_data=f"delete_{file_key}")],
            [InlineKeyboardButton(f"بازگشت به لیست فایل‌ها ({server_name.capitalize()})", callback_data=f"server_{server_name}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"عملیات مورد نظر برای فایل '{file_key}' را انتخاب کنید:", reply_markup=reply_markup)
        return CHOOSING_ACTION


    elif callback_data.startswith("delete_"):
        file_key = callback_data[len("delete_"):]
        server_name = user_data[user_id].get('current_server')
        # تاییدیه حذف
        keyboard = [
            [InlineKeyboardButton(f"✅ بله، حذف کن", callback_data=f"confirmdelete_{file_key}")],
            [InlineKeyboardButton(f"❌ انصراف", callback_data=f"file_{file_key}")] # بازگشت به گزینه‌های فایل
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"آیا از حذف فایل '{file_key}' مطمئن هستید؟", reply_markup=reply_markup)
        return CHOOSING_ACTION


    elif callback_data.startswith("confirmdelete_"):
        file_key = callback_data[len("confirmdelete_"):]
        server_name = user_data[user_id].get('current_server')
        server_info = config.SERVERS[server_name]

        s3_client = liara_s3_utils.get_s3_client(
            server_info["access_key"], server_info["secret_key"], server_info["endpoint_url"], server_info.get("region_name")
        )
        if s3_client and liara_s3_utils.delete_file(s3_client, server_info["bucket"], file_key):
            await query.edit_message_text(f"فایل '{file_key}' با موفقیت حذف شد.")
        else:
            await query.edit_message_text(f"خطا در حذف فایل '{file_key}'.")
        # نمایش مجدد فایل‌های سرور
        await show_server_files(update, context, server_name)
        return CHOOSING_ACTION


    elif callback_data.startswith("getlink_"):
        file_key = callback_data[len("getlink_"):]
        server_name = user_data[user_id].get('current_server')
        server_info = config.SERVERS[server_name]
        s3_client = liara_s3_utils.get_s3_client(
            server_info["access_key"], server_info["secret_key"], server_info["endpoint_url"], server_info.get("region_name")
        )
        if s3_client:
            link = liara_s3_utils.get_download_link(s3_client, server_info["bucket"], file_key)
            if link:
                # برای جلوگیری از مشکلات Markdown در لینک، از parse_mode=None استفاده می‌کنیم
                # یا لینک را در تگ <pre> قرار می‌دهیم
                await query.message.reply_text(f"لینک دانلود برای '{file_key}':\n`{link}`", parse_mode='MarkdownV2') # یا HTML
                # بازگشت به گزینه‌های فایل بعد از ارسال لینک
                # await query.answer() # برای اینکه پیام "loading" دکمه از بین برود
                # current_text = query.message.text
                # await query.edit_message_text(text=current_text) # متن قبلی را حفظ میکنیم
            else:
                await query.edit_message_text("خطا در ایجاد لینک دانلود.")
        else:
            await query.edit_message_text("خطا در اتصال به سرور برای دریافت لینک.")
        # کاربر همچنان در مرحله انتخاب عملیات برای فایل است
        return CHOOSING_ACTION


    elif callback_data.startswith("rename_"):
        file_key = callback_data[len("rename_"):]
        user_data[user_id]['file_to_rename'] = file_key
        await query.edit_message_text(f"لطفاً نام جدید را برای فایل '{file_key}' ارسال کنید:")
        return RENAMING_FILE

    # اگر callback_data شناخته نشد (نباید اتفاق بیفتد)
    # await query.edit_message_text("دستور نامشخص.")
    # return CHOOSING_SERVER # یا هر وضعیت پیش‌فرض دیگر


@restricted
async def handle_rename_message(update: Update, context: CallbackContext) -> int:
    """دریافت نام جدید فایل و انجام تغییر نام"""
    user_id = update.effective_user.id
    new_file_key = update.message.text.strip()
    old_file_key = user_data[user_id].get('file_to_rename')
    server_name = user_data[user_id].get('current_server')

    if not old_file_key or not server_name:
        await update.message.reply_text("خطا: اطلاعات لازم برای تغییر نام موجود نیست. لطفاً دوباره تلاش کنید.")
        await start_command(update, context) # بازگشت به شروع
        return CHOOSING_SERVER

    if not new_file_key:
        await update.message.reply_text("نام فایل نمی‌تواند خالی باشد. لطفاً نام جدید را ارسال کنید:")
        return RENAMING_FILE # باقی ماندن در وضعیت تغییر نام

    # بررسی کاراکترهای غیرمجاز (بسته به محدودیت‌های S3/Liara)
    if "/" in new_file_key: # S3 از / برای شبیه‌سازی پوشه استفاده می‌کند
        await update.message.reply_text("نام فایل نمی‌تواند شامل '/' باشد. لطفاً نام دیگری انتخاب کنید:")
        return RENAMING_FILE

    server_info = config.SERVERS[server_name]
    s3_client = liara_s3_utils.get_s3_client(
        server_info["access_key"], server_info["secret_key"], server_info["endpoint_url"], server_info.get("region_name")
    )

    if s3_client:
        if liara_s3_utils.rename_file(s3_client, server_info["bucket"], old_file_key, new_file_key):
            await update.message.reply_text(f"نام فایل '{old_file_key}' با موفقیت به '{new_file_key}' تغییر یافت.")
            del user_data[user_id]['file_to_rename'] # پاک کردن فایل در حال تغییر نام
            # نمایش مجدد فایل‌های سرور با نام جدید
            # اینجا چون پیام جدید ارسال می‌شود، باید show_server_files را با update (و نه query) فراخوانی کنیم
            # اما show_server_files انتظار query دارد. باید آن را اصلاح کنیم یا یک wrapper بسازیم.
            # برای سادگی، کاربر را به لیست فایل‌ها برمی‌گردانیم.
            await show_server_files(update, context, server_name) # نیاز به اصلاح show_server_files دارد
            return CHOOSING_ACTION
        else:
            await update.message.reply_text(f"خطا در تغییر نام فایل '{old_file_key}'. ممکن است نام جدید تکراری باشد یا خطایی رخ داده باشد.")
            # بازگشت به گزینه‌های فایل اصلی
            file_key = old_file_key # برای نمایش دکمه‌های فایل قبلی
            keyboard = [
                [InlineKeyboardButton(f"🔗 دریافت لینک دانلود", callback_data=f"getlink_{file_key}")],
                [InlineKeyboardButton(f"✏️ تغییر نام", callback_data=f"rename_{file_key}")],
                [InlineKeyboardButton(f"🗑️ حذف فایل", callback_data=f"delete_{file_key}")],
                [InlineKeyboardButton(f"بازگشت به لیست فایل‌ها ({server_name.capitalize()})", callback_data=f"server_{server_name}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(f"عملیات مورد نظر برای فایل '{file_key}' را انتخاب کنید:", reply_markup=reply_markup)
            return CHOOSING_ACTION
    else:
        await update.message.reply_text("خطا در اتصال به سرور برای تغییر نام.")
        await start_command(update, context) # بازگشت به شروع
        return CHOOSING_SERVER


# --- تابع اصلی ---
def main() -> None:
    """ربات را راه‌اندازی می‌کند."""
    application = Application.builder().token(config.BOT_TOKEN).build()

    # افزودن CommandHandler برای دستور /start
    application.add_handler(CommandHandler("start", start_command))

    # افزودن CallbackQueryHandler برای دکمه‌های inline
    # اینجا باید مشخص کنیم که این هندلر در چه وضعیتی از مکالمه فعال باشد
    # یا اینکه یک هندلر کلی برای همه callback ها داشته باشیم و داخل آن وضعیت را چک کنیم
    application.add_handler(CallbackQueryHandler(button_callback_handler))


    # افزودن MessageHandler برای دریافت نام جدید فایل (وقتی در وضعیت RENAMING_FILE هستیم)
    # این بخش نیاز به استفاده از ConversationHandler دارد برای مدیریت بهتر وضعیت‌ها
    # برای سادگی فعلی، یک MessageHandler ساده اضافه می‌کنیم که فقط وقتی file_to_rename ست شده عمل کند
    # راه حل بهتر استفاده از ConversationHandler است.
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Chat(config.SUPER_ADMIN_USER_ID), handle_rename_message_wrapper))


    # اجرای ربات تا زمانی که کاربر Ctrl-C را فشار دهد
    logger.info("ربات در حال اجراست...")
    application.run_polling()

async def handle_rename_message_wrapper(update: Update, context: CallbackContext):
    """
    یک wrapper برای handle_rename_message تا بتوانیم وضعیت را قبل از فراخوانی چک کنیم.
    این یک راه حل ساده است. ConversationHandler برای این موارد بسیار بهتر است.
    """
    user_id = update.effective_user.id
    if user_data.get(user_id, {}).get('file_to_rename'): # فقط اگر در حال تغییر نام هستیم
        await handle_rename_message(update, context)
    else:
        # اگر کاربر متنی ارسال کرد و در وضعیت تغییر نام نبود، می‌توانیم آن را نادیده بگیریم
        # یا یک پیام راهنما ارسال کنیم.
        # await update.message.reply_text("لطفاً ابتدا یک دستور را انتخاب کنید یا از /start استفاده کنید.")
        pass # فعلا نادیده می‌گیریم


if __name__ == "__main__":
    main()
