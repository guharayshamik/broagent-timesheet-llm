# broagent_main.py

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import os
import logging
from dotenv import load_dotenv
# Import handlers from atTimesheetBot.bot
from atTimesheetBot.bot import (
    start,
    month_handler,
    apply_leave,
    special_efforts_handler,
    ns_leave_handler,
    weekend_efforts_handler,
    half_day_handler,
    action_completed,
    leave_type_handler,
    start_date_handler,
    end_date_handler,
    generate_timesheet,
    restart_handler,
    handle_text_input,
)
from atTimesheetBot.registration import register_new_user, handle_registration_buttons
from atTimesheetBot.de_registration import confirm_deregistration, handle_deregistration_buttons
from atTimesheetBot.timesheet_generator import generate_timesheet_excel
from datetime import datetime
import os

# Global user modes
user_modes = {}

# Load environment
load_dotenv()
BOT_TOKEN = os.getenv("BROAGENT_BOT_TOKEN")

# ----------------------------------------------------------------
# 🔐 Redact sensitive token from all log messages (including httpx)
# ----------------------------------------------------------------
class RedactTokenFilter(logging.Filter):
    def filter(self, record):
        if BOT_TOKEN and isinstance(record.msg, str):
            record.msg = record.msg.replace(BOT_TOKEN, "***REDACTED_TOKEN***")
        return True

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.addFilter(RedactTokenFilter())

# 📉 Reduce verbosity of httpx (prevents token URL leak)
logging.getLogger("httpx").setLevel(logging.WARNING)

# ----------------------------------------------------------------
# 🧾 /start menu
# ----------------------------------------------------------------
async def broagent_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("🤖 LLM-based GovTech Submission", callback_data="govtech_llm")],
        [InlineKeyboardButton("👆 Touch-based GovTech Submission", callback_data="govtech_touch")],
        [InlineKeyboardButton("⏳ Napta Submission (Coming Soon)", callback_data="napta_comingsoon")]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)

    await update.message.reply_text(
        "🧾 Choose your timesheet submission method:",
        reply_markup=reply_markup
    )

# 🚦 Option selector
async def handle_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data

    if choice == "govtech_llm":
        await query.message.reply_text(
            "📝 Please describe your leave/work in plain English (e.g., 'I took sick leave Aug 2-4').")
        user_modes[query.from_user.id] = "llm"

    elif choice == "govtech_touch":
        await query.message.reply_text("🧮 Launching touch-based timesheet flow...")
        from atTimesheetBot.bot import start
        return await start(update, context)

    elif choice == "napta_comingsoon":
        await query.message.reply_text("⏳ Napta integration is under construction.")


# 🚧 LLM Handler (stub for now)
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("mode") == "llm":
        user_input = update.message.text.strip()
        await update.message.reply_text(f"(LLM) You said: {user_input}\n➡️ Timesheet generation will happen here.")
    else:
        await update.message.reply_text("🤖 Type /start to begin.")

# 🧠 Main app launcher
def main():
    if not BOT_TOKEN:
        raise ValueError("BROAGENT_BOT_TOKEN missing in .env")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", broagent_start))
    app.add_handler(CallbackQueryHandler(handle_option, pattern="^(govtech_llm|govtech_touch|napta_comingsoon)$"))
    # app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    # 💡 Core Handlers from atTimesheetBot
    app.add_handler(CommandHandler("register", register_new_user))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))

    app.add_handler(CallbackQueryHandler(handle_registration_buttons,
                                         pattern="^(timesheet_preference|skill_level|role_specialization|contractor)_.+"))
    app.add_handler(CallbackQueryHandler(month_handler, pattern=r"^month_.*"))
    app.add_handler(CallbackQueryHandler(apply_leave, pattern="^apply_leave$"))
    app.add_handler(CallbackQueryHandler(special_efforts_handler, pattern="^special_efforts$"))
    app.add_handler(CallbackQueryHandler(ns_leave_handler, pattern="^ns_leave$"))
    app.add_handler(CallbackQueryHandler(weekend_efforts_handler, pattern="^weekend_efforts$"))
    app.add_handler(CallbackQueryHandler(half_day_handler, pattern="^half_day$"))
    app.add_handler(CallbackQueryHandler(action_completed, pattern="^(ns_leave_|weekend_efforts_|half_day_)"))
    app.add_handler(CallbackQueryHandler(leave_type_handler, pattern="^leave_"))
    app.add_handler(CallbackQueryHandler(start_date_handler, pattern="^start_date_"))
    app.add_handler(CallbackQueryHandler(end_date_handler, pattern="^end_date_"))
    app.add_handler(
        CallbackQueryHandler(generate_timesheet, pattern="^(generate_timesheet_now|generate_timesheet_after_leave)$"))
    app.add_handler(CallbackQueryHandler(restart_handler, pattern="^restart_timesheet$"))
    app.add_handler(CommandHandler("reset", confirm_deregistration))
    app.add_handler(CommandHandler("deregister", confirm_deregistration))
    app.add_handler(CallbackQueryHandler(handle_deregistration_buttons, pattern="^deregister_"))

    logger.info("✅ BroAgent is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
