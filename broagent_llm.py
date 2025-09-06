# broagent_llm.py
import re
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

# ----------------- Config / Regex helpers -----------------

# IMPORTANT: "and" is NOT a range separator (it's for discrete lists).
RANGE_SEP = r"(?:-|–|—|−|~|to|until|till|through|thru)"

_MONTHS = {
    "jan": "January", "feb": "February", "mar": "March", "apr": "April",
    "may": "May", "jun": "June", "jul": "July", "aug": "August",
    "sep": "September", "sept": "September", "oct": "October",
    "nov": "November", "dec": "December",
}

_LEAVE_SYNONYMS = {
    "sick": "Sick Leave",
    "mc": "Sick Leave",
    "medical": "Sick Leave",
    "annual": "Annual Leave",
    "vacation": "Annual Leave",
    "al": "Annual Leave",  # shortcut
    "childcare": "Childcare Leave",
    "cc": "Childcare Leave",
    "ns": "NS Leave",
    "national service": "NS Leave",
    "weekend efforts": "Weekend Efforts",
    "public holiday efforts": "Public Holiday Efforts",
    "half day": "Half Day",
    "halfday": "Half Day",
}

_ALLOWED_TYPES = {
    "Sick Leave",
    "Annual Leave",
    "Childcare Leave",
    "NS Leave",
    "Weekend Efforts",
    "Public Holiday Efforts",
    "Half Day",
}

# ----------------- Normalizers & Validators -----------------

def _std_month_name(token: str) -> str | None:
    return _MONTHS.get(token.strip().lower())

def _full_month_name(token: str) -> str | None:
    t = token.strip()
    if len(t) <= 3:
        return _std_month_name(t)
    cap = t.capitalize()
    if cap in _MONTHS.values():
        return cap
    return _std_month_name(t[:3])

def _month_from_text(text: str) -> str | None:
    # “for August”, “in Aug”, “August timesheet”, “timesheet for Sept”
    m = re.search(r"\b(for|in)\s+([A-Za-z]{3,9})\b", text, flags=re.I)
    if m:
        return _full_month_name(m.group(2))
    m2 = re.search(r"\b([A-Za-z]{3,9})\s+(timesheet|sheet)\b", text, flags=re.I)
    if m2:
        return _full_month_name(m2.group(1))
    # plain month when combined with generate/submit/create
    m3 = re.search(r"\b([A-Za-z]{3,9})\b", text, flags=re.I)
    if m3 and re.search(r"\b(generate|submit|create)\b", text, flags=re.I):
        return _full_month_name(m3.group(1))
    return None

def _standardize_day(day_token: str) -> int | None:
    d = re.sub(r"(st|nd|rd|th)$", "", day_token.strip(), flags=re.I)
    if d.isdigit():
        v = int(d)
        if 1 <= v <= 31:
            return v
    return None

def _fmt_dB(day: int, month_name: str) -> str:
    return f"{day:02d}-{month_name}"

def _split_dB(date_str: str) -> tuple[int, str]:
    d, m = date_str.split("-", 1)
    return int(d), m

def _validate_date(day: int, month_name: str) -> bool:
    """True if day is valid for the given full month name (e.g., 'June')."""
    try:
        month_num = datetime.strptime(month_name, "%B").month
        datetime(2025, month_num, day)  # year only for validation
        return True
    except ValueError:
        return False

# ----------------- Date parsers -----------------

def _parse_date_bits(text: str) -> list[tuple[int, str]]:
    """
    Return list of (day, MonthName):
      - 11 Aug / 11-Aug / 11–Aug
      - Aug 11 / August 11th
    """
    pairs = []

    # Case A: <day> <mon> or <day>-<mon>
    for m in re.finditer(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?(?:\s+|[-–—])([A-Za-z]{{3,9}})\b", text, flags=re.I):
        day = _standardize_day(m.group(1))
        month = _full_month_name(m.group(2))
        if day and month:
            pairs.append((day, month))

    # Case B: <mon> <day>
    for m in re.finditer(r"\b([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?\b", text, flags=re.I):
        month = _full_month_name(m.group(1))
        day = _standardize_day(m.group(2))
        if day and month:
            pairs.append((day, month))

    return pairs

def _parse_date_range(text: str) -> tuple[tuple[int, str], tuple[int, str]] | None:
    """
    Detect ranges with a month:
      - 11–13 Aug / 11 to 13 Aug / between 11 and 13 Aug
      - Aug 11–13 / Aug 11 to 13
      - 1st to 3rd September (month appears once, after the second day)
    """

    # Case A: MONTH AFTER SECOND DAY (e.g., "1st to 3rd Sept", "between 5–7 Aug")
    mA = re.search(
        rf"\b(?:between\s+)?(\d{{1,2}})(?:st|nd|rd|th)?\s*{RANGE_SEP}\s*(\d{{1,2}})(?:st|nd|rd|th)?\s+([A-Za-z]{{3,9}})\b",
        text, flags=re.I
    )
    if mA:
        d1 = _standardize_day(mA.group(1))
        d2 = _standardize_day(mA.group(2))
        mon = _full_month_name(mA.group(3))
        if d1 and d2 and mon:
            logger.debug(f"[parse_range] CaseA matched: {d1}-{d2} {mon}")
            return (d1, mon), (d2, mon)

    # Case B: MONTH FIRST (e.g., "Sept 1–3", "August 11 to 13")
    mB = re.search(
        rf"\b([A-Za-z]{{3,9}})\s+(\d{{1,2}})(?:st|nd|rd|th)?\s*{RANGE_SEP}\s*(\d{{1,2}})(?:st|nd|rd|th)?\b",
        text, flags=re.I
    )
    if mB:
        mon = _full_month_name(mB.group(1))
        d1 = _standardize_day(mB.group(2))
        d2 = _standardize_day(mB.group(3))
        if d1 and d2 and mon:
            logger.debug(f"[parse_range] CaseB matched: {mon} {d1}-{d2}")
            return (d1, mon), (d2, mon)

    return None

def _parse_range_no_month(text: str) -> tuple[int, int] | None:
    """Detect ranges like '11-14' without a month."""
    m = re.search(
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s*{RANGE_SEP}\s*(\d{{1,2}})(?:st|nd|rd|th)?\b(?!\s*[A-Za-z])",
        text, flags=re.I
    )
    if not m:
        return None
    d1, d2 = _standardize_day(m.group(1)), _standardize_day(m.group(2))
    if d1 and d2:
        logger.debug(f"[parse_range_no_month] matched: {d1}-{d2}")
        return (min(d1, d2), max(d1, d2))
    return None

def _parse_single_day_no_month(text: str) -> int | None:
    """Detect a single day without month (e.g., 'on 10th', or bare '10')."""
    m = re.search(r"\bon\s+(\d{1,2})(?:st|nd|rd|th)?\b(?!\s*[A-Za-z])", text, flags=re.I)
    if m:
        d = _standardize_day(m.group(1))
        logger.debug(f"[single_no_month] 'on {d}' detected")
        return d
    month_keys = "|".join(_MONTHS.keys())
    m2 = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\b(?!\s*(?:{month_keys}))", text, flags=re.I)
    if m2 and not _parse_date_range(text):
        d = _standardize_day(m2.group(1))
        logger.debug(f"[single_no_month] bare day {d} detected")
        return d
    return None

# ----- Multi-day lists (NOT ranges) -----

def _extract_days_list(days_blob: str) -> list[int]:
    """Split '1, 3 and 7' / '1 & 2' into [1,3,7]."""
    parts = re.split(r"(?:\s*,\s*|\s+and\s+|\s*&\s*)", days_blob.strip(), flags=re.I)
    out = []
    for p in parts:
        d = _standardize_day(p)
        if d:
            out.append(d)
    return out

def _parse_multi_days_with_month(text: str) -> tuple[list[int], str] | None:
    """'3rd and 5th June' / '1, 3 & 7 Aug' / '1,2,3 Sep'."""
    m = re.search(
        r"\b((?:\d{1,2}(?:st|nd|rd|th)?(?:\s*,\s*|\s+and\s+|\s*&\s*)?)+)\s+([A-Za-z]{3,9})\b",
        text, flags=re.I
    )
    if not m:
        return None
    days_blob, mon = m.group(1), _full_month_name(m.group(2))
    if not mon:
        return None
    days = _extract_days_list(days_blob)
    if days:
        logger.debug(f"[multi_days_with_month] {days} {mon}")
        return days, mon
    return None

def _parse_multi_days_no_month(text: str) -> list[int] | None:
    """Detect '1, 3 and 5' with no month after."""
    m = re.search(
        r"\b((?:\d{1,2}(?:st|nd|rd|th)?(?:\s*,\s*|\s+and\s+|\s*&\s*)?)+)\b(?!\s*[A-Za-z])",
        text, flags=re.I
    )
    if not m:
        return None
    days = _extract_days_list(m.group(1))
    if days:
        logger.debug(f"[multi_days_no_month] {days} (no month)")
    return days or None

# ----------------- Overlap detection -----------------

def _ranges_overlap(new_start: str, new_end: str, old_start: str, old_end: str) -> bool:
    ns, nm = _split_dB(new_start)
    ne, nem = _split_dB(new_end)
    os, om = _split_dB(old_start)
    oe, oem = _split_dB(old_end)
    if nm != om or nem != oem:
        return False
    return not (ne < os or ns > oe)

def _find_overlap(leave_details, start: str, end: str):
    for i, (s, e, t) in enumerate(leave_details):
        if _ranges_overlap(start, end, s, e):
            return i, (s, e, t)
    return None, None

# ----------------- Main entry -----------------

async def handle_llm_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    logger.info(f"[LLM] raw: {text}")

    # 0) Pending overlap resolution
    if "pending_overlap" in context.user_data:
        ans = text.lower().strip()
        overlap = context.user_data["pending_overlap"]
        leave_details = context.user_data.setdefault("leave_details", [])
        if ans in ("yes", "y", "yeah", "yep", "sure"):
            leave_details[overlap["idx"]] = overlap["new"]
            context.user_data["leave_details"] = leave_details
            _, new_month = _split_dB(overlap["new"][0])
            context.user_data["recent_leave_month"] = new_month
            context.user_data["month"] = new_month
            context.user_data.pop("pending_overlap")
            logger.info(f"[LLM] overlap: replaced {overlap['old']} -> {overlap['new']}")
            await update.message.reply_text(
                f"🔄 Replaced *{overlap['old'][2]}* on *{overlap['old'][0]}–{overlap['old'][1]}* "
                f"with *{overlap['new'][2]}*.",
                parse_mode="Markdown",
            )
            await update.message.reply_text("📌 You can add more leaves or say `generate timesheet`.", parse_mode="Markdown")
            return
        elif ans in ("no", "n", "nope"):
            context.user_data.pop("pending_overlap")
            logger.info("[LLM] overlap: kept original, discarded new")
            await update.message.reply_text("❌ Okay, kept your original leave. Discarded the new one.")
            return

    # 1) Generation intent
    wants_generate = bool(re.search(r"\b(generate|submit|create)\b.*\b(timesheet|sheet)\b", text, flags=re.I)) \
                     or bool(re.search(r"\b(generate|submit|create)\b", text, flags=re.I))

    month_mentioned = _month_from_text(text)
    if month_mentioned:
        context.user_data["month"] = month_mentioned
        logger.debug(f"[LLM] explicit month: {month_mentioned}")

    # 2) Leave type
    leave_type = None
    for key, canonical in _LEAVE_SYNONYMS.items():
        if re.search(rf"\b{re.escape(key)}\b", text, flags=re.I):
            leave_type = canonical
            break
    if not leave_type:
        for allowed in _ALLOWED_TYPES:
            if re.search(rf"\b{re.escape(allowed)}\b", text, flags=re.I):
                leave_type = allowed
                break
    if leave_type:
        logger.debug(f"[LLM] leave_type: {leave_type}")

    # Always have a list to append to
    leave_details = context.user_data.setdefault("leave_details", [])

    # 3) Dates (full support)
    # First priority: check for explicit range
    date_range = _parse_date_range(text)

    # If no range, then try other formats
    date_pairs = None
    multi_days_with_month = None
    if not date_range:
        date_pairs = _parse_date_bits(text)
        multi_days_with_month = _parse_multi_days_with_month(text)

    # Ranges without month → use fallback month if known
    if not date_range:
        no_mon_range = _parse_range_no_month(text)
        fallback_month = context.user_data.get("recent_leave_month") or context.user_data.get("month")
        if no_mon_range and fallback_month:
            d1, d2 = no_mon_range
            date_range = ((d1, fallback_month), (d2, fallback_month))
            logger.debug(f"[LLM] range w/o month -> using {fallback_month}: {d1}-{d2}")
        elif no_mon_range and not fallback_month:
            await update.message.reply_text(
                "⚠️ I see a date range but no month. Please include the month (e.g., `5–7 August`).",
                parse_mode="Markdown"
            )
            return

    single_no_mon = None
    multi_days_no_month = None
    if not date_range and not date_pairs and not multi_days_with_month:
        single_no_mon = _parse_single_day_no_month(text)
        if not single_no_mon:
            multi_days_no_month = _parse_multi_days_no_month(text)

    # ---- Multi-day list with month (e.g., "5th and 7th August mc")
    if leave_type and multi_days_with_month:
        days, mon = multi_days_with_month
        logger.info(f"[LLM] multi-day list with month: {days} {mon} ({leave_type})")
        # Validate all first
        for d in days:
            if not _validate_date(d, mon):
                await update.message.reply_text(
                    f"⚠️ {d}-{mon} is not a valid date. Please correct it.",
                    parse_mode="Markdown"
                )
                return
        recorded = []
        for d in days:
            start = _fmt_dB(d, mon)
            idx, existing = _find_overlap(leave_details, start, start)
            if existing and existing[2] != leave_type:
                context.user_data["pending_overlap"] = {
                    "new": (start, start, leave_type), "old": existing, "idx": idx
                }
                context.user_data["recent_leave_month"] = mon
                context.user_data["month"] = mon
                await update.message.reply_text(
                    f"⚠️ *{start}* already has *{existing[2]}*.\n"
                    f"Replace with *{leave_type}*? (yes/no)",
                    parse_mode="Markdown",
                )
                return
            leave_details.append((start, start, leave_type))
            recorded.append(start)

        context.user_data["leave_details"] = leave_details
        context.user_data["recent_leave_month"] = mon
        context.user_data["month"] = mon
        nice = ", ".join(recorded)
        await update.message.reply_text(
            f"✅ Recorded *{leave_type}* on *{nice}*.",
            parse_mode="Markdown"
        )
        await update.message.reply_text("📌 You can add more leaves or say `generate timesheet`.", parse_mode="Markdown")
        return

    # ---- Range path (e.g., "5th to 7th mc") → considered a continuous range
    if leave_type and date_range:
        (d1, m1), (d2, m2) = date_range
        logger.info(f"[LLM] range detected: {d1}-{d2} {m1} ({leave_type})")
        if not _validate_date(d1, m1):
            await update.message.reply_text(
                f"⚠️ {d1}-{m1} is not a valid date. Please re-enter with a valid day and month.",
                parse_mode="Markdown"
            )
            return
        if not _validate_date(d2, m2):
            await update.message.reply_text(
                f"⚠️ {d2}-{m2} is not a valid date. Please re-enter with a valid day and month.",
                parse_mode="Markdown"
            )
            return
        start = _fmt_dB(d1, m1)
        end   = _fmt_dB(d2, m2)
        idx, existing = _find_overlap(leave_details, start, end)
        if existing:
            context.user_data["pending_overlap"] = {"new": (start, end, leave_type), "old": existing, "idx": idx}
            await update.message.reply_text(
                f"⚠️ *{start}–{end}* already has *{existing[2]}*.\n"
                f"Do you want to replace it with *{leave_type}*? (yes/no)",
                parse_mode="Markdown",
            )
            return
        leave_details.append((start, end, leave_type))
        context.user_data["leave_details"] = leave_details
        context.user_data["recent_leave_month"] = m1
        context.user_data["month"] = m1
        await update.message.reply_text(
            f"✅ Recorded *{leave_type}* from *{start}* to *{end}*.",
            parse_mode="Markdown"
        )
        return

    # ---- Single day with explicit month
    elif leave_type and date_pairs:
        day, mon = date_pairs[0]
        logger.info(f"[LLM] single day w/ month: {day}-{mon} ({leave_type})")
        if not _validate_date(day, mon):
            await update.message.reply_text(
                f"⚠️ {day}-{mon} is not a valid date. Please re-enter with a valid day and month.",
                parse_mode="Markdown"
            )
            return
        start = _fmt_dB(day, mon)
        idx, existing = _find_overlap(leave_details, start, start)
        if existing and existing[2] != leave_type:
            context.user_data["pending_overlap"] = {"new": (start, start, leave_type), "old": existing, "idx": idx}
            context.user_data["recent_leave_month"] = mon
            context.user_data["month"] = mon
            await update.message.reply_text(
                f"⚠️ *{start}* already has *{existing[2]}*.\n"
                f"Did you mean to replace it with *{leave_type}*? (yes/no)",
                parse_mode="Markdown",
            )
            return
        context.user_data["pending_leave"] = {"leave_type": leave_type, "start_date": start, "end_date": None}
        context.user_data["awaiting_confirmation"] = True
        context.user_data["recent_leave_month"] = mon
        context.user_data["month"] = mon
        await update.message.reply_text(
            f"🧐 Just to confirm, did you mean *{leave_type}* only for *{start}*? (yes/no)",
            parse_mode="Markdown"
        )
        return

    # ---- Multiple single days WITHOUT month (e.g., "5 and 7 mc")
    elif leave_type and multi_days_no_month:
        fallback_month = context.user_data.get("recent_leave_month") or context.user_data.get("month")
        if not fallback_month:
            await update.message.reply_text(
                "⚠️ I saw multiple days but no month. Please include a month (e.g., `5 and 7 August`).",
                parse_mode="Markdown"
            )
            return
        logger.info(f"[LLM] multi-day list no month: {multi_days_no_month} -> {fallback_month} ({leave_type})")
        for d in multi_days_no_month:
            if not _validate_date(d, fallback_month):
                await update.message.reply_text(
                    f"⚠️ {d}-{fallback_month} is not a valid date. Please correct it.",
                    parse_mode="Markdown"
                )
                return
        recorded = []
        for d in multi_days_no_month:
            start = _fmt_dB(d, fallback_month)
            idx, existing = _find_overlap(leave_details, start, start)
            if existing and existing[2] != leave_type:
                context.user_data["pending_overlap"] = {
                    "new": (start, start, leave_type), "old": existing, "idx": idx
                }
                context.user_data["recent_leave_month"] = fallback_month
                context.user_data["month"] = fallback_month
                await update.message.reply_text(
                    f"⚠️ *{start}* already has *{existing[2]}*.\n"
                    f"Replace with *{leave_type}*? (yes/no)",
                    parse_mode="Markdown",
                )
                return
            leave_details.append((start, start, leave_type))
            recorded.append(start)

        context.user_data["leave_details"] = leave_details
        context.user_data["recent_leave_month"] = fallback_month
        context.user_data["month"] = fallback_month
        nice = ", ".join(recorded)
        await update.message.reply_text(
            f"✅ Recorded *{leave_type}* on *{nice}*.",
            parse_mode="Markdown"
        )
        await update.message.reply_text("📌 You can add more leaves or say `generate timesheet`.", parse_mode="Markdown")
        return

    # 4) Generate if asked
    if wants_generate:
        month = month_mentioned or context.user_data.get("recent_leave_month") or context.user_data.get("month")
        if not month:
            await update.message.reply_text(
                "⚠️ I couldn't detect the month. Try: `generate timesheet for September`",
                parse_mode="Markdown"
            )
            return
        context.user_data["month"] = month

        pending = context.user_data.pop("pending_leave", None)
        awaiting = context.user_data.pop("awaiting_confirmation", False)
        if pending and awaiting is False:
            leave_details.append((pending["start_date"], pending["start_date"], pending["leave_type"]))
            context.user_data["leave_details"] = leave_details

        await update.message.reply_text("📊 Generating your timesheet...")
        from atTimesheetBot.timesheet_generator import generate_and_send_timesheet
        await generate_and_send_timesheet(update, context)

        # Show the start menu again for convenience
        try:
            from broagent_main import broagent_start
            await broagent_start(update, context)
        except Exception:
            pass
        return

    # 5) Pending yes/no for one-day confirmation
    if context.user_data.get("awaiting_confirmation"):
        ans = text.lower().strip()
        if ans in ("yes", "y", "yeah", "yep", "sure"):
            pending = context.user_data.pop("pending_leave", None)
            context.user_data["awaiting_confirmation"] = False
            if pending:
                idx, existing = _find_overlap(leave_details, pending["start_date"], pending["start_date"])
                if existing and existing[2] != pending["leave_type"]:
                    context.user_data["pending_overlap"] = {
                        "new": (pending["start_date"], pending["start_date"], pending["leave_type"]),
                        "old": existing,
                        "idx": idx,
                    }
                    _, mon = _split_dB(pending["start_date"])
                    context.user_data["recent_leave_month"] = mon
                    context.user_data["month"] = mon
                    await update.message.reply_text(
                        f"⚠️ *{pending['start_date']}* already has *{existing[2]}*.\n"
                        f"Replace with *{pending['leave_type']}*? (yes/no)",
                        parse_mode="Markdown",
                    )
                    return
                leave_details.append((pending["start_date"], pending["start_date"], pending["leave_type"]))
                context.user_data["leave_details"] = leave_details
                _, mon = _split_dB(pending["start_date"])
                context.user_data["recent_leave_month"] = mon
                context.user_data["month"] = mon
                await update.message.reply_text(
                    f"✅ Recorded *{pending['leave_type']}* on *{pending['start_date']}*.",
                    parse_mode="Markdown"
                )
                await update.message.reply_text("📌 You can add more leaves or say `generate timesheet`.", parse_mode="Markdown")
                return
        elif ans in ("no", "n", "nope"):
            context.user_data.pop("pending_leave", None)
            context.user_data.pop("awaiting_confirmation", None)
            await update.message.reply_text("❌ Okay, cancelled. Please rephrase your leave request.")
            return

    # 6) Friendly nudge (dynamic)
    current_month = context.user_data.get("month") or context.user_data.get("recent_leave_month")
    if current_month:
        examples = (
            f"Tell me something like:\n"
            f"- `generate timesheet for {current_month}`\n"
            f"- `annual leave 11–13 {current_month[:3]}`\n"
            f"- `sick leave on 10 {current_month[:3]}`"
        )
    else:
        examples = (
            "Tell me something like:\n"
            "- `generate timesheet for September`\n"
            "- `annual leave 11–13 Sep`\n"
            "- `sick leave on 10 Sep`\n\n"
            "⚠️ Please mention the month along with the date (e.g., `10th June`)."
        )
    await update.message.reply_text(examples, parse_mode="Markdown")
