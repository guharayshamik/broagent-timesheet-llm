# broagent_main.py

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
import os
import logging
from dotenv import load_dotenv

# atTimesheetBot imports (touch-based flow stays unchanged)
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

# LLM free-text parser/handler (your lightweight parser)
from broagent_llm import handle_llm_input as llm_free_text_handler


# -------------------------------
# Environment & Logging
# -------------------------------
load_dotenv()
BOT_TOKEN = os.getenv("BROAGENT_BOT_TOKEN")

class RedactTokenFilter(logging.Filter):
    """Redact the bot token from all logs."""
    def filter(self, record):
        if BOT_TOKEN and isinstance(record.msg, str):
            record.msg = record.msg.replace(BOT_TOKEN, "***REDACTED_TOKEN***")
        return True

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
logger.addFilter(RedactTokenFilter())

# Reduce very noisy libs
logging.getLogger("httpx").setLevel(logging.WARNING)


# -------------------------------
# /start menu
# -------------------------------
async def broagent_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("🤖 LLM-based GovTech Submission", callback_data="govtech_llm")],
        [InlineKeyboardButton("👆 Touch-based GovTech Submission", callback_data="govtech_touch")],
        [InlineKeyboardButton("⏳ Napta Submission (Coming Soon)", callback_data="napta_comingsoon")],
    ]
    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("🧾 Choose your timesheet submission method:", reply_markup=reply_markup)


# -------------------------------
# Option selector (callback)
# -------------------------------
async def handle_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data

    if choice == "govtech_llm":
        # Clear any stale state and enter LLM mode
        context.user_data.clear()
        context.user_data["mode"] = "llm"
        await query.message.reply_text(
            "📝 LLM mode ON.\n"
            "Describe your work/leave in plain English, e.g.:\n"
            "• “generate timesheet for August”\n"
            "• “annual leave 11–13 Aug”\n"
            "• “sick leave on 11 Aug”"
        )

    elif choice == "govtech_touch":
        # Touch-based flow is fully managed by atTimesheetBot
        context.user_data["mode"] = "touch"
        await query.message.reply_text("🧮 Launching touch-based timesheet flow…")
        return await start(update, context)

    elif choice == "napta_comingsoon":
        await query.message.reply_text("⏳ Napta integration is under construction. Stay tuned!")


# -------------------------------
# Text routing
# -------------------------------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    All free-text messages land here.
    - If user is in LLM mode: delegate to broagent_llm handler.
    - Otherwise: delegate to touch-based handler in atTimesheetBot.
    """
    mode = context.user_data.get("mode")
    if mode == "llm":
        return await llm_free_text_handler(update, context)
    # default / touch flow
    return await handle_text_input(update, context)


async def route_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Compatibility wrapper for any code referencing a router."""
    return await handle_text(update, context)


# -------------------------------
# App launcher
# -------------------------------
def main():
    if not BOT_TOKEN:
        raise ValueError("BROAGENT_BOT_TOKEN missing in .env")

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", broagent_start))
    app.add_handler(CommandHandler("register", register_new_user))
    app.add_handler(CommandHandler("reset", confirm_deregistration))
    app.add_handler(CommandHandler("deregister", confirm_deregistration))

    # Callback query handlers (menus & touch flow)
    app.add_handler(CallbackQueryHandler(handle_option, pattern="^(govtech_llm|govtech_touch|napta_comingsoon)$"))
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
    app.add_handler(CallbackQueryHandler(generate_timesheet, pattern="^(generate_timesheet_now|generate_timesheet_after_leave)$"))
    app.add_handler(CallbackQueryHandler(restart_handler, pattern="^restart_timesheet$"))
    app.add_handler(CallbackQueryHandler(handle_deregistration_buttons, pattern="^deregister_"))

    # Text messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, route_text_input))

    logger.info("✅ BroAgent is running…")
    app.run_polling()


if __name__ == "__main__":
    main()




# # broagent_main.py
#
# from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
# from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
# import os
# import logging
# from dotenv import load_dotenv
# # Import handlers from atTimesheetBot.bot
# from atTimesheetBot.bot import (
#     start,
#     month_handler,
#     apply_leave,
#     special_efforts_handler,
#     ns_leave_handler,
#     weekend_efforts_handler,
#     half_day_handler,
#     action_completed,
#     leave_type_handler,
#     start_date_handler,
#     end_date_handler,
#     generate_timesheet,
#     restart_handler,
#     handle_text_input,
# )
# from atTimesheetBot.registration import register_new_user, handle_registration_buttons
# from atTimesheetBot.de_registration import confirm_deregistration, handle_deregistration_buttons
# from datetime import datetime
# import os
# from broagent_llm import handle_llm_input as llm_free_text_handler
# from llm_agent.llm_agent import chain
# import traceback
# from llm_agent.utils.llm_output_validator import get_closest_leave_type
#
#
#
#
# # Global user modes
# user_modes = {}
#
# # Load environment
# load_dotenv()
# BOT_TOKEN = os.getenv("BROAGENT_BOT_TOKEN")
#
# # ----------------------------------------------------------------
# # 🔐 Redact sensitive token from all log messages (including httpx)
# # ----------------------------------------------------------------
# class RedactTokenFilter(logging.Filter):
#     def filter(self, record):
#         if BOT_TOKEN and isinstance(record.msg, str):
#             record.msg = record.msg.replace(BOT_TOKEN, "***REDACTED_TOKEN***")
#         return True
#
# # Setup logging
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)
# logger.addFilter(RedactTokenFilter())
#
# logging.basicConfig(
#     level=logging.DEBUG,  # This sets root logger level
#     format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
# )
#
# logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)
#
# # 📉 Reduce verbosity of httpx (prevents token URL leak)
# logging.getLogger("httpx").setLevel(logging.WARNING)
#
# # ----------------------------------------------------------------
# # 🧾 /start menu
# # ----------------------------------------------------------------
# async def broagent_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     buttons = [
#         [InlineKeyboardButton("🤖 LLM-based GovTech Submission", callback_data="govtech_llm")],
#         [InlineKeyboardButton("👆 Touch-based GovTech Submission", callback_data="govtech_touch")],
#         [InlineKeyboardButton("⏳ Napta Submission (Coming Soon)", callback_data="napta_comingsoon")]
#     ]
#     reply_markup = InlineKeyboardMarkup(buttons)
#
#     await update.message.reply_text(
#         "🧾 Choose your timesheet submission method:",
#         reply_markup=reply_markup
#     )
#
# # 🚦 Option selector
# async def handle_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     query = update.callback_query
#     await query.answer()
#     choice = query.data
#
#     # broagent_main.py (within handle_option)
#
#     if choice == "govtech_llm":
#         context.user_data.clear()  # clear stale state
#         context.user_data["mode"] = "llm"
#         await query.message.reply_text(
#             "📝 Please describe your leave/work in plain English (e.g., 'I took sick leave Aug 2-4')."
#         )
#
#     elif choice == "govtech_touch":
#         await query.message.reply_text("🧮 Launching touch-based timesheet flow...")
#         from atTimesheetBot.bot import start
#         return await start(update, context)
#
#     elif choice == "napta_comingsoon":
#         await query.message.reply_text("⏳ Napta integration is under construction.")
#
#
# # 🚧 LLM Handler
# async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     # ✅ Intercept confirmation before hitting LLM
#     if context.user_data.get("awaiting_confirmation"):
#         confirmation = update.message.text.strip().lower()
#         if confirmation in ("yes", "y", "yeah", "yep", "sure"):
#             logger.info("[LLM] User confirmed one-day leave.")
#
#             leave = context.user_data.get("pending_leave", {})
#             leave_details = context.user_data.get("leave_details", [])
#             leave_details.append((
#                 leave.get("start_date"),
#                 leave.get("end_date") or leave.get("start_date"),
#                 leave.get("leave_type")
#             ))
#             context.user_data["leave_details"] = leave_details
#
#             # Clear confirmation state
#             context.user_data.pop("awaiting_confirmation", None)
#             context.user_data.pop("pending_leave", None)
#
#             await update.message.reply_text(
#                 "✅ Thanks! Your one-day leave has been recorded.\n"
#                 "📌 Do you want to *add more leaves* or *generate timesheet* now?",
#                 parse_mode="Markdown"
#             )
#             return
#
#         else:
#             context.user_data.pop("awaiting_confirmation", None)
#             context.user_data.pop("pending_leave", None)
#             await update.message.reply_text("❌ Got it. Leave request cancelled.")
#             return
#
#     # ▶️ Proceed with regular flow
#     if context.user_data.get("mode") == "llm":
#         return await handle_llm_input(update, context)
#     else:
#         return await handle_text_input(update, context)
#
#
# async def route_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     mode = context.user_data.get("mode")
#
#     if mode == "llm":
#         return await handle_text(update, context)
#     else:
#         from atTimesheetBot.bot import handle_text_input
#         return await handle_text_input(update, context)
#
# async def handle_llm_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     user_input = update.message.text.strip()
#
#     #  Intercept yes/no response to correction
#     if "pending_correction" in context.user_data:
#         confirmation = user_input.strip().lower()
#         if confirmation in ("yes", "y", "yeah"):
#             correction = context.user_data.pop("pending_correction")
#             leave_details = context.user_data.get("leave_details", [])
#             leave_details.append((
#                 correction["start_date"],
#                 correction["end_date"] or correction["start_date"],
#                 correction["suggested_type"]
#             ))
#             context.user_data["leave_details"] = leave_details
#
#             await update.message.reply_text(
#                 f"✅ Recorded *{correction['suggested_type']}* on *{correction['start_date']}*.",
#                 parse_mode="Markdown"
#             )
#             await update.message.reply_text(
#                 "📌 Do you want to *add more leaves* or *generate timesheet* now?",
#                 parse_mode="Markdown"
#             )
#             return
#
#         elif confirmation in ("no", "n"):
#             context.user_data.pop("pending_correction")
#             await update.message.reply_text(
#                 "❌ Okay, please rephrase your leave request more clearly.",
#                 parse_mode="Markdown"
#             )
#             return
#
#     # 🧠 Handle confirmation of one-day leave
#     if context.user_data.get("awaiting_confirmation") and user_input.lower() in ["yes", "yeah", "yup"]:
#         pending = context.user_data.pop("pending_leave", None)
#         if pending:
#             context.user_data["awaiting_confirmation"] = False
#             leave_details = context.user_data.get("leave_details", [])
#             leave_details.append((
#                 pending["start_date"],
#                 pending["end_date"],
#                 pending["leave_type"]
#             ))
#             context.user_data["leave_details"] = leave_details
#             logger.info("[LLM] User confirmed one-day leave.")
#
#             await update.message.reply_text(
#                 "✅ Noted your leave for *{}* on *{}*.".format(
#                     pending["leave_type"], pending["start_date"]
#                 ),
#                 parse_mode="Markdown"
#             )
#             await update.message.reply_text(
#                 "📌 Do you want to *add more leaves* or *generate your timesheet now*?\n"
#                 "Reply with:\n"
#                 "- more leaves\n"
#                 "- generate timesheet",
#                 parse_mode="Markdown"
#             )
#             return
#
#
#     # 📝 Log the raw user message
#     logger.debug(f"[LLM] Received user input: {user_input}")
#
#     # 🧠 Inform the user what’s happening
#     await update.message.reply_text(
#         "🤖 Using *Ollama (llama3)* to understand your message...",
#         parse_mode="Markdown"
#     )
#
#     try:
#         # 🔍 Log before calling the chain
#         logger.debug(f"[LLM] Invoking LangChain chain with input: {user_input}")
#
#         # ✅ FIXED: Pass input as dictionary
#         result = await chain.ainvoke({"input": user_input})
#
#         # 📦 Log the full structured output
#         logger.debug(f"[LLM] Chain returned: {result}")
#         logger.debug(f"[LLM] Action: {result.action}, Leave Type: {result.leave_type}, "
#                      f"Start: {result.start_date}, End: {result.end_date}")
#
#         # ✅ Step: Validate and correct leave type (post-parser)
#         if result.action == "add_leave" and result.leave_type:
#             corrected_type = get_closest_leave_type(result.leave_type)
#             if corrected_type and corrected_type != result.leave_type:
#                 context.user_data["pending_correction"] = {
#                     "suggested_type": corrected_type,
#                     "start_date": result.start_date,
#                     "end_date": result.end_date
#                 }
#
#                 await update.message.reply_text(
#                     f"🤔 Did you mean *{corrected_type}* instead of *{result.leave_type}*?",
#                     parse_mode="Markdown"
#                 )
#                 return
#             elif not corrected_type:
#                 await update.message.reply_text(
#                     f"❌ I couldn't understand the leave type: *{result.leave_type}*.\n"
#                     f"Please try again using types like *Sick Leave*, *Annual Leave*, etc.",
#                     parse_mode="Markdown"
#                 )
#                 return
#
#         action = result.action
#
#         if action == "add_leave":
#             context.user_data["leave_type"] = result.leave_type
#             context.user_data["start_date"] = result.start_date
#             context.user_data["end_date"] = result.end_date
#
#             logger.info(f"[LLM] Parsed leave: {result.leave_type} from {result.start_date} to {result.end_date}")
#
#             if result.end_date:
#                 await update.message.reply_text(
#                     f"📅 Adding *{result.leave_type}* from *{result.start_date}* to *{result.end_date}*.\n➡️ Processing...",
#                     parse_mode="Markdown"
#                 )
#             else:
#                 # Store for confirmation
#                 context.user_data["awaiting_confirmation"] = True
#                 context.user_data["pending_leave"] = {
#                     "leave_type": result.leave_type,
#                     "start_date": result.start_date,
#                     "end_date": result.end_date
#                 }
#
#                 await update.message.reply_text(
#                     f"🧐 Just to confirm, did you mean *{result.leave_type}* only for *{result.start_date}*?",
#                     parse_mode="Markdown"
#                 )
#
#         elif action == "generate_timesheet":
#             context.user_data["month"] = result.month  # ✅ STORE MONTH
#             logger.info(f"[LLM] User requested timesheet generation.")
#
#             # ✅ Pull in any previously confirmed single-day leave before generating
#             pending = context.user_data.pop("pending_leave", None)
#             awaiting = context.user_data.pop("awaiting_confirmation", False)
#             if pending and awaiting is False:
#                 leave_details = context.user_data.get("leave_details", [])
#                 leave_details.append((
#                     pending["start_date"],
#                     pending["end_date"],
#                     pending["leave_type"]
#                 ))
#                 context.user_data["leave_details"] = leave_details
#
#             await update.message.reply_text("📊 Generating your timesheet...")
#             if not result.month:
#                 await update.message.reply_text(
#                     "⚠️ I couldn't detect the month. Please try again like:\n"
#                     "`generate timesheet for August`",
#                     parse_mode="Markdown"
#                 )
#                 return
#             from atTimesheetBot.timesheet_generator import generate_and_send_timesheet
#             await generate_and_send_timesheet(update, context)
#
#
#         elif action == "reset_user":
#             logger.info(f"[LLM] Resetting user profile on request.")
#             context.user_data.clear()
#             await update.message.reply_text("♻️ Your profile has been reset.")
#
#         else:
#             logger.warning(f"[LLM] Unknown action returned: {action}")
#             await update.message.reply_text(f"⚠️ Unrecognized action: `{action}`", parse_mode="Markdown")
#
#     except Exception as e:
#         logger.error(f"[LLM] Exception: {e}")
#         logger.error(traceback.format_exc())  # Show full trace for debug
#
#         await update.message.reply_text(
#             f"⚠️ Sorry, I couldn't understand that.\n"
#             f"Please rephrase your message like:\n"
#             f"`I took childcare leave Aug 14-16`",
#             parse_mode="Markdown"
#         )
#
#
#
# # 🧠 Main app launcher
# def main():
#     if not BOT_TOKEN:
#         raise ValueError("BROAGENT_BOT_TOKEN missing in .env")
#
#     app = Application.builder().token(BOT_TOKEN).build()
#
#     app.add_handler(CommandHandler("start", broagent_start))
#     app.add_handler(CallbackQueryHandler(handle_option, pattern="^(govtech_llm|govtech_touch|napta_comingsoon)$"))
#     # app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
#     # 💡 Core Handlers from atTimesheetBot
#     app.add_handler(CommandHandler("register", register_new_user))
#     # app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
#     app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, route_text_input))
#
#     app.add_handler(CallbackQueryHandler(handle_registration_buttons,
#                                          pattern="^(timesheet_preference|skill_level|role_specialization|contractor)_.+"))
#     app.add_handler(CallbackQueryHandler(month_handler, pattern=r"^month_.*"))
#     app.add_handler(CallbackQueryHandler(apply_leave, pattern="^apply_leave$"))
#     app.add_handler(CallbackQueryHandler(special_efforts_handler, pattern="^special_efforts$"))
#     app.add_handler(CallbackQueryHandler(ns_leave_handler, pattern="^ns_leave$"))
#     app.add_handler(CallbackQueryHandler(weekend_efforts_handler, pattern="^weekend_efforts$"))
#     app.add_handler(CallbackQueryHandler(half_day_handler, pattern="^half_day$"))
#     app.add_handler(CallbackQueryHandler(action_completed, pattern="^(ns_leave_|weekend_efforts_|half_day_)"))
#     app.add_handler(CallbackQueryHandler(leave_type_handler, pattern="^leave_"))
#     app.add_handler(CallbackQueryHandler(start_date_handler, pattern="^start_date_"))
#     app.add_handler(CallbackQueryHandler(end_date_handler, pattern="^end_date_"))
#     app.add_handler(
#         CallbackQueryHandler(generate_timesheet, pattern="^(generate_timesheet_now|generate_timesheet_after_leave)$"))
#     app.add_handler(CallbackQueryHandler(restart_handler, pattern="^restart_timesheet$"))
#     app.add_handler(CommandHandler("reset", confirm_deregistration))
#     app.add_handler(CommandHandler("deregister", confirm_deregistration))
#     app.add_handler(CallbackQueryHandler(handle_deregistration_buttons, pattern="^deregister_"))
#
#     logger.info("✅ BroAgent is running...")
#     app.run_polling()
#
# if __name__ == "__main__":
#     main()
