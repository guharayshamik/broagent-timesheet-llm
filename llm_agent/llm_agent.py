import logging
import re
from dateutil import parser
from llm_agent.llm_prompt import PROMPT
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda
from langchain_community.llms import Ollama
from llm_agent.schemas import TimesheetAction

logger = logging.getLogger(__name__)

# 1. Setup LLM
llm = Ollama(model="llama3")

# 2. Define Output Parser
parser = PydanticOutputParser(pydantic_object=TimesheetAction)

# 3. Define Prompt Template (with escaped braces!)
prompt = PromptTemplate(
    template=(
        "You are a smart assistant helping users generate timesheet entries.\n"
        "Interpret the user's message and extract all relevant leave actions.\n\n"
        "Respond ONLY in valid JSON. Do not add explanation or commentary.\n\n"
        "If the action is 'add_leave', return multiple entries like this:\n"
        "{{\n"
        "  \"action\": \"add_leave\",\n"
        "  \"entries\": [\n"
        "    {{\"leave_type\": \"Sick Leave\", \"start_date\": \"06-August\"}},\n"
        "    {{\"leave_type\": \"Annual Leave\", \"start_date\": \"11-August\", \"end_date\": \"12-August\"}}\n"
        "  ]\n"
        "}}\n\n"
        "📅 Date Format Rules:\n"
        "- Format as: `dd-MMMM` (e.g., `02-August`, `14-September`).\n"
        "- Capitalize full month names.\n"
        "- Pad single-digit days with zero (e.g., `05-August`).\n"
        "- If end_date is not mentioned, assume it's a one-day leave.\n\n"
        "🧾 If action is 'generate_timesheet', return only the month field like this:\n"
        "{{ \"action\": \"generate_timesheet\", \"month\": \"August\" }}\n\n"
        "User Input: {input}\n\n"
        "Return JSON:\n"
        "{format_instructions}"
    ),
    input_variables=["input"],
    partial_variables={"format_instructions": parser.get_format_instructions()}
)

# 4. Build the chain
chain = (
    {"input": RunnableLambda(lambda x: x["input"])}
    | prompt
    | llm
    | parser
)

class LLMChain:
    def __init__(self, llm):
        self.llm = llm

    def parse_input(self, user_input):
        # Load the prompt from the external file
        prompt = PROMPT + f"\nUser Input: {user_input}\nOutput:"
        logger.debug(f"[LLM] Sending prompt to LLM: {prompt}")

        # Call the LLM with the prompt
        response = self.llm(prompt)
        logger.debug(f"[LLM] Raw response from LLM: {response}")

        # Parse the response
        return self._parse_response(response, user_input)

    def _parse_response(self, response, user_input):
        try:
            # Parse the LLM response
            parsed = eval(response)  # Replace with `json.loads` if response is valid JSON
            action = parsed.get("action")
            leave_type = parsed.get("leave_type")
            start_date = parsed.get("start_date")
            end_date = parsed.get("end_date")

            # Parse dates if they are strings
            if start_date:
                start_date = parser.parse(start_date).date()
            if end_date:
                end_date = parser.parse(end_date).date()

            # If fields are missing, use manual fallback
            if not leave_type or not start_date or not end_date:
                logger.debug("[LLM] Falling back to manual parsing.")
                fallback = self.manual_fallback(user_input)
                leave_type = leave_type or fallback["leave_type"]
                start_date = start_date or fallback["start_date"]
                end_date = end_date or fallback["end_date"]

            return {
                "action": action,
                "leave_type": leave_type,
                "start_date": start_date,
                "end_date": end_date,
            }
        except Exception as e:
            logger.error(f"[LLM] Failed to parse response: {e}")
            return self.manual_fallback(user_input)

    def manual_fallback(self, user_input):
        # Extract leave type (basic example, can be extended)
        leave_types = ["sick leave", "annual leave", "casual leave"]
        leave_type = next((lt for lt in leave_types if lt in user_input.lower()), None)

        # Extract dates using regex
        date_pattern = r"(\b[A-Za-z]+\s\d{1,2})[-–](\d{1,2})"
        match = re.search(date_pattern, user_input)
        start_date, end_date = None, None
        if match:
            try:
                start_date = parser.parse(match.group(1)).date()
                end_date = parser.parse(f"{match.group(1).split()[0]} {match.group(2)}").date()
            except ValueError:
                pass

        return {
            "action": "add_leave",
            "leave_type": leave_type,
            "start_date": start_date,
            "end_date": end_date,
        }
