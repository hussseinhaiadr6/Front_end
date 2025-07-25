import re
import json5
import logging
from typing import List, Dict, Optional
from pydantic import ValidationError
from langchain_core.prompts import ChatPromptTemplate

from Utilities.schema import validate_chart_config
from Utilities.templates import system_template, Instructions_tempate
from Utilities.Utils import get_llm,_preprocess,load_chart_configs

# Configure module-level logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# ────────────────────────────────────────────────────────────────────────────────
# Main function with retry logic
# ────────────────────────────────────────────────────────────────────────────────

def generate_validated_chart_configs(
    user_data: str,
    user_instruction: str,
    *,
    deployment_name: str = "gpt-4o",
    max_attempts: int = 4,
) -> str:
    model = get_llm(deployment_name)
    """Return sanitized, validated chart-config JSON via an LLM, retrying on parse/validation errors."""
    base_prompt = ChatPromptTemplate.from_messages([
        ("system", system_template),
        ("user", Instructions_tempate)
    ])

    error_context: Optional[str] = None
    last_exception: Optional[Exception] = None

    for attempt in range(1, max_attempts + 1):
        prompt_input = {"user_data": user_data, "user_instruction": user_instruction}
        if error_context:
            prompt_input["user_instruction"] += (
                f"\n\nPrevious LLM error on attempt {attempt - 1}: {error_context}"
                "\nPlease adjust your output to fix this."
            )

        prompt = base_prompt.invoke(prompt_input)
        raw_response = model.invoke(prompt).content
        print(f"LLM Raw repsonse: {raw_response}")
        logger.debug("[Attempt %d] Raw LLM response: %s", attempt, raw_response)

        # Preprocess & parse JSON5
        cleaned = _preprocess(raw_response)
        try:
            configs: List[Dict] = json5.loads(cleaned)
            logger.info("[Attempt %d] Parsed JSON5 successfully.", attempt)
        except Exception as exc:
            error_context = f"JSON5 parse error: {exc}"
            logger.warning("[Attempt %d] %s", attempt, error_context)
            last_exception = exc
            continue

        # Schema validation (handle possible tuple response)
        validated: List[Dict] = []
        validation_failed = False
        for cfg in configs:
            try:
                result = validate_chart_config(cfg)
                if isinstance(result, tuple):
                    ok, err = result
                    if not ok:
                        raise ValueError(err)
                # assume no exception or True means valid
                validated.append(cfg)
            except Exception as exc:
                if attempt ==4:
                    return " Error: Could not genrate chart"
                error_context = f"Validation error: {exc}"
                logger.warning("[Attempt %d] %s", attempt, error_context)
                last_exception = exc
                validation_failed = True
                break
        if validation_failed:
            continue
        logger.info("[Attempt %d] Schema validation passed.", attempt)

        # Success: serialize and return
        return _preprocess(str(validated))

    # All attempts failed
    logger.error("Failed to generate valid chart configs after %d attempts.", max_attempts)
    raise ValueError(
        f"Could not generate valid chart configs after {max_attempts} attempts: {last_exception}"
    )
# ────────────────────────────────────────────────────────────────────────────────
# Example usage
# ────────────────────────────────────────────────────────────────────────────────


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

print(f"the generate html chart configs are: \n {generate_validated_chart_configs(Data,instructions)}")