
import logging

from langchain_core.prompts import ChatPromptTemplate


from Utilities.templates import html_instruction_template, html_system_template
from Utilities.Utils import get_llm

# Configure module-level logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# ────────────────────────────────────────────────────────────────────────────────
# Main function with retry logic
# ────────────────────────────────────────────────────────────────────────────────

def generate_html_chart_configs(user_data: str,user_instruction: str) :


    model = get_llm("gpt-4o")
    """Return sanitized, validated chart-config JSON via an LLM, retrying on parse/validation errors."""
    base_prompt = ChatPromptTemplate.from_messages([
        ("system", html_system_template),
        ("user", html_instruction_template)
    ])


    prompt_input = {"user_data": user_data, "user_instruction": user_instruction}

    

    prompt = base_prompt.invoke(prompt_input)
    raw_response = model.invoke(prompt).content

    logger.debug("[Attempt %d] Raw LLM response: %s", raw_response)
    return raw_response

      
    
Data="""Monthly DP Volume Share for BAT in KSA (National)
Filtered by the last 6 months, BAT manufacturer, KSA market, and national city.

Assumption:

Only BAT manufacturer, KSA market, and national city are included.
Results:

2024-10-01: 27.27
2024-11-01: 27.42
2024-12-01: 27.28
2025-01-01: 27.14
2025-02-01: 26.96
2025-03-01: 26.88
Each row shows the month and the corresponding DP volume share for BAT."""

instructions=" I need a line chart and bar chart "

print(f"the generate html chart configs are: \n {generate_html_chart_configs(Data,instructions)}")
