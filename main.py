import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    filters, CallbackContext, CallbackQueryHandler, ConversationHandler
)
import config
import liara_s3_utils

# فعال کردن لاگ‌گیری
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# وضعیت‌های ConversationHandler
CHOOSING_SERVER, MANAGING_FILES, RENAMING_FILE = range(3)

def restricted(func):
    """دکوراتور محدودکننده دسترسی به ادمین ارشد"""
    async def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id != config.SUPER_ADMIN_USER_ID:
            if update.message:
                await update.message.reply_text("⛔ شما اجازه دسترسی به این ربات را ندارید.")
            elif update.callback_query:
                await update.callback_query.answer("عدم دسترسی ارشد!", show_alert=True)
            return ConversationHandler.END
        return await func(update, context, *args, **kwargs)
    return wrapped

@restricted
async def start_command(update: Update, context: CallbackContext) -> int:
    """شروع ربات و نمایش لیست سرورها"""
    context.user_data.clear() # پاکسازی دیتای قبلی جلسه
    
    keyboard = []
    for server_key in config.SERVERS.keys():
        keyboard.append([InlineKeyboardButton(server_key.upper(), callback_data=f"server_{server_key}")])
    keyboard.append([InlineKeyboardButton("📊 آمار کلی سرورها", callback_data="stats_all_servers")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    msg_text = "👋 سلام ادمین عزیز!\nلطفاً یکی از سرورهای زیر را جهت مدیریت انتخاب کنید:"
    
    if update.message:
        await update.message.reply_text(msg_text, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(msg_text, reply_markup=reply_markup)
        
    return CHOOSING_SERVER

async def show_server_files(update: Update, context: CallbackContext, server_name: str) -> None:
    """نمایش لیست فایل‌ها و مشخصات سرور انتخاب شده"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    context.user_data['current_server'] = server_name
    server_info = config.SERVERS.get(server_name)

    if not server_info:
        msg = "❌ سرور یافت نشد."
        if query: await query.edit_message_text(msg)
        else: await update.message.reply_text(msg)
        return

    s3_client = liara_s3_utils.get_s3_client(
        server_info["access_key"], server_info["secret_key"],
        server_info["endpoint_url"], server_info.get("region_name")
    )

    if not s3_client:
        msg = "❌ خطا در اتصال به کلاینت S3 سرور."
        if query: await query.edit_message_text(msg)
        else: await update.message.reply_text(msg)
        return

    usage_stats = liara_s3_utils.get_bucket_usage(s3_client, server_info["bucket"], config.SERVER_CAPACITY_GB)
    stats_message = (
        f"📊 آمار سرور {server_name.upper()}:\n"
        f"🔹 استفاده شده: {usage_stats['used_gb']} GB ({usage_stats['file_count']} فایل)\n"
        f"🔸 فضای خالی: {usage_stats['free_gb']} GB از {usage_stats['total_gb']} GB\n\n"
        f"📂 لیست فایل‌های موجود:"
    )

    files = liara_s3_utils.list_files(s3_client, server_info["bucket"])
    keyboard = []
    skipped_count = 0

    if files:
        for f in files:
            f_name = f['name']
            f_size = round(f['size'] / (1024 * 1024), 2)
            
            display_name = f_name if len(f_name) <= 25 else f_name[:22] + "..."
            btn_text = f"📄 {display_name} ({f_size} MB)"
            cb_data = f"file_{f_name}"

            if len(cb_data.encode('utf-8')) > 64:
                skipped_count += 1
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"⚠️ فایل `{f_name}` به دلیل طولانی بودن نام در دکمه‌ها لود نشد."
                )
                continue

            keyboard.append([InlineKeyboardButton(btn_text, callback_data=cb_data)])

    if skipped_count > 0:
        stats_message += f"\n\n⚠️ تعداد {skipped_count} فایل به دلیل محدودیت تلگرام نادیده گرفته شدند."
    if not files and skipped_count == 0:
        stats_message += "\nهیچ فایلی در این باکت وجود ندارد."

    keyboard.append([InlineKeyboardButton("⬅️ بازگشت به منوی سرورها", callback_data="back_to_servers")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    if query:
        await query.edit_message_text(text=stats_message, reply_markup=reply_markup)
    else:
        await context.bot.send_message(chat_id=user_id, text=stats_message, reply_markup=reply_markup)

@restricted
async def server_choice_handler(update: Update, context: CallbackContext) -> int:
    """مدیریت کلیک روی دکمه‌های منوی اصلی (انتخاب سرور یا آمار کلی)"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "stats_all_servers":
        full_stats = "📊 آمار کلی تمام باکت‌ها:\n\n"
        for s_name, s_info in config.SERVERS.items():
            client = liara_s3_utils.get_s3_client(s_info["access_key"], s_info["secret_key"], s_info["endpoint_url"])
            if client:
                usage = liara_s3_utils.get_bucket_usage(client, s_info["bucket"], config.SERVER_CAPACITY_GB)
                full_stats += f"🌐 {s_name.upper()}: {usage['used_gb']}/{usage['total_gb']} GB ({usage['file_count']} فایل)\n"
            else:
                full_stats += f"🌐 {s_name.upper()}: خطای اتصال\n"
        
        kb = [[InlineKeyboardButton("⬅️ بازگشت", callback_data="back_to_servers")]]
        await query.edit_message_text(full_stats, reply_markup=InlineKeyboardMarkup(kb))
        return CHOOSING_SERVER

    elif query.data.startswith("server_"):
        server_name = query.data[len("server_"):]
        await show_server_files(update, context, server_name)
        return MANAGING_FILES
    
    return CHOOSING_SERVER

@restricted
async def file_management_handler(update: Update, context: CallbackContext) -> int:
    """مدیریت عملیات روی فایل انتخاب شده (لینک، حذف، تغییر نام)"""
    query = update.callback_query
    await query.answer()
    
    server_name = context.user_data.get('current_server')
    server_info = config.SERVERS.get(server_name)
    
    if query.data == "back_to_servers":
        return await start_command(update, context)
        
    elif query.data.startswith("file_"):
        file_name = query.data[len("file_"):]
        context.user_data['selected_file'] = file_name
        
        kb = [
            [InlineKeyboardButton("🔗 دریافت لینک دانلود موقت", callback_data=f"getlink_{file_name}")],
            [InlineKeyboardButton("✏️ تغییر نام فایل", callback_data=f"rename_{file_name}")],
            [InlineKeyboardButton("🗑️ حذف فایل", callback_data=f"delete_{file_name}")],
            [InlineKeyboardButton(f"⬅️ بازگشت به لیست فایلهای {server_name.upper()}", callback_data=f"server_{server_name}")]
        ]
        display_name = file_name if len(file_name) <= 35 else file_name[:32] + "..."
        await query.edit_message_text(f"📁 مدیریت فایل: `{display_name}`\n🖥️ سرور: {server_name.upper()}\n\nیک عملیات را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(kb))
        return MANAGING_FILES

    elif query.data.startswith("server_"):
        server_name = query.data[len("server_"):]
        await show_server_files(update, context, server_name)
        return MANAGING_FILES

    elif query.data.startswith("getlink_"):
        file_name = query.data[len("getlink_"):]
        client = liara_s3_utils.get_s3_client(server_info["access_key"], server_info["secret_key"], server_info["endpoint_url"])
        link = liara_s3_utils.get_download_link(client, server_info["bucket"], file_name)
        
        if link:
            # ارسال لینک به صورت مونو اسپیس با قبلیت کپی آسان
            await context.bot.send_message(chat_id=update.effective_user.id, text=f"🔗 لینک دانلود (معتبر برای ۱ ساعت):\n\n`{link}`", parse_mode="Markdown")
        else:
            await query.message.reply_text("❌ خطا در ساخت لینک دانلود.")
        return MANAGING_FILES

    elif query.data.startswith("delete_"):
        file_name = query.data[len("delete_"):]
        kb = [
            [InlineKeyboardButton("✅ بله، کاملاً مطمئنم", callback_data=f"confirm_del_{file_name}")],
            [InlineKeyboardButton("❌ خیر، انصراف", callback_data=f"file_{file_name}")]
        ]
        await query.edit_message_text(f"⚠️ آیا از حذف دائمی فایل `{file_name}` از سرور مطمئن هستید؟", reply_markup=InlineKeyboardMarkup(kb))
        return MANAGING_FILES

    elif query.data.startswith("confirm_del_"):
        file_name = query.data[len("confirm_del_"):]
        client = liara_s3_utils.get_s3_client(server_info["access_key"], server_info["secret_key"], server_info["endpoint_url"])
        
        if liara_s3_utils.delete_file(client, server_info["bucket"], file_name):
            await context.bot.send_message(chat_id=update.effective_user.id, text=f"✅ فایل `{file_name}` با موفقیت حذف شد.")
        else:
            await context.bot.send_message(chat_id=update.effective_user.id, text="❌ خطا در حذف فایل رخ داد.")
            
        await show_server_files(update, context, server_name)
        return MANAGING_FILES

    elif query.data.startswith("rename_"):
        file_name = query.data[len("rename_"):]
        context.user_data['file_to_rename'] = file_name
        await query.edit_message_text(f"✏️ نام فعلی: `{file_name}`\n\nلطفاً نام جدید فایل را (همراه با فرمت آن، مثلاً image.png) ارسال کنید:")
        return RENAMING_FILE

@restricted
async def handle_rename_message(update: Update, context: CallbackContext) -> int:
    """دریافت نام جدید از کاربر متنی و اعمال روی فایل S3 Compatible"""
    new_name = update.message.text.strip()
    old_name = context.user_data.get('file_to_rename')
    server_name = context.user_data.get('current_server')
    server_info = config.SERVERS.get(server_name)

    if not new_name or "/" in new_name or "\\" in new_name:
        await update.message.reply_text("❌ نام وارد شده غیرمجاز است. نباید شامل خط مورب یا خالی باشد. دوباره تلاش کنید:")
        return RENAMING_FILE

    client = liara_s3_utils.get_s3_client(server_info["access_key"], server_info["secret_key"], server_info["endpoint_url"])
    
    if liara_s3_utils.rename_file(client, server_info["bucket"], old_name, new_name):
        await update.message.reply_text(f"✅ فایل با موفقیت از `{old_name}` به `{new_name}` تغییر نام یافت.")
    else:
        await update.message.reply_text("❌ خطا در تغییر نام! مطمئن شوید نام جدید تکراری نیست.")

    # بازگشت اتوماتیک به لیست فایل‌های همان سرور
    await show_server_files(update, context, server_name)
    return MANAGING_FILES

async def cancel_handler(update: Update, context: CallbackContext) -> int:
    """لغو مکالمه و بازگشت به منوی شروع"""
    await start_command(update, context)
    return CHOOSING_SERVER

def main() -> None:
    """راه‌اندازی و اجرای ربات تلگرام"""
    if config.BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or config.SUPER_ADMIN_USER_ID == 0:
        logger.critical("⚠️ لطفا ابتدا فایل .env یا مقادیر config.py را با اطلاعات واقعی پر کنید!")
        return

    application = Application.builder().token(config.BOT_TOKEN).build()

    # تعریف پایداری وضعیت‌ها با استفاده از ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={
            CHOOSING_SERVER: [CallbackQueryHandler(server_choice_handler)],
            MANAGING_FILES: [CallbackQueryHandler(file_management_handler)],
            RENAMING_FILE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_rename_message)]
        },
        fallbacks=[CommandHandler("cancel", cancel_handler), CommandHandler("start", start_command)],
        per_user=True,
        per_chat=True
    )

    application.add_handler(conv_handler)

    logger.info("🚀 ربات با موفقیت فعال شد و در حال شنود است...")
    application.run_polling()

if __name__ == "__main__":
    main()
