from pydantic import BaseModel, field_validator, ValidationInfo
from datetime import datetime
from typing import Optional


class TimesheetAction(BaseModel):
    action: str
    leave_type: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    month: Optional[str] = None

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def standardize_date(cls, v: str, info: ValidationInfo) -> str:
        """
        Normalize date to 'dd-MMMM' format (e.g., 02-August).
        Accepts input like 'aug 2', '2 Aug', '2nd august' etc.
        """
        if not v:
            return v

        # 🧹 Clean input
        raw = str(v).strip().replace("–", "-").replace("—", "-").replace("  ", " ")

        # If user mistakenly returns a list, extract first
        if isinstance(v, list) and v:
            raw = str(v[0]).strip()

        # Handle patterns like '2 Aug', '2nd August', 'Aug 2', etc.
        date_formats = ["%d %b", "%d %B", "%b %d", "%B %d", "%d-%b", "%d-%B", "%b-%d", "%B-%d"]
        raw = raw.replace("st", "").replace("nd", "").replace("rd", "").replace("th", "")
        raw = raw.title()

        for fmt in date_formats:
            try:
                dt = datetime.strptime(raw, fmt)
                return dt.strftime("%d-%B")  # ✅ Consistent format
            except ValueError:
                continue

        return raw  # Fallback if parsing fails
