# llm_agent/utils/llm_output_validator.py

from rapidfuzz import process

ACCEPTED_LEAVE_TYPES = {
    "Sick Leave",
    "Childcare Leave",
    "Annual Leave",
    "NS Leave",
    "National Service Leave",
    "Weekend Efforts",
    "Public Holiday Efforts",
    "Half Day"
}

SIMILARITY_THRESHOLD = 85


def get_closest_leave_type(input_type: str) -> str | None:
    if not input_type:
        return None

    # Use RapidFuzz to get best match
    result = process.extractOne(input_type, ACCEPTED_LEAVE_TYPES, score_cutoff=SIMILARITY_THRESHOLD)

    if result is None:
        return None

    suggestion, score, _ = result
    return suggestion
