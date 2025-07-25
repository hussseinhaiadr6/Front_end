# import os
# from dotenv import load_dotenv
# from langchain_openai import AzureChatOpenAI
# from langchain_core.prompts import ChatPromptTemplate
# from azure.identity import DefaultAzureCredential
# from azure.keyvault.secrets import SecretClient

from langchain_core.output_parsers import PydanticOutputParser

from pydantic import BaseModel, ConfigDict, ValidationError
from typing import List, Optional, Union, Dict, Any, Literal, Tuple # Added Tuple

# --- Pydantic Models (Copied from your example) ---

# Define common chart types supported by Chart.js
ChartType = Literal['bar','line','scatter','bubble','pie','doughnut','polarArea','radar']

# Define a model for data points used in scatter and bubble charts
class PointData(BaseModel):
    x: Union[float, int, str, None]
    y: Union[float, int, str, None]
    r: Optional[Union[float, int]] = None
    model_config = ConfigDict(
        extra='allow' # Allow additional properties in point objects
    )

# Define a base dataset model with common properties
class BaseDataset(BaseModel):
    label: str
    backgroundColor: Optional[Union[str, List[str]]] = None
    borderColor: Optional[Union[str, List[str]]] = None
    borderWidth: Optional[Union[int, float, List[Union[int, float]]]] = None
    # Pydantic v2 uses model_config instead of Config class
    # By default, Pydantic V2 forbids extra fields unless specified.
    # If you want to allow extra fields for styling etc. ONLY at this level:
    # model_config = ConfigDict(extra='allow')


# Define the main Dataset model
class Dataset(BaseDataset):
    data: List[Union[Optional[Union[float, int]], PointData]]
    # Again, inherits default behaviour (no extra fields) unless BaseDataset changes it
    # or you override it here:
    # model_config = ConfigDict(extra='allow')


# Define the structure for the 'data' part of the Chart.js config
class ChartData(BaseModel):
    labels: Optional[List[Union[str, List[str]]]] = None
    datasets: List[Dataset] = []
    # model_config = ConfigDict(extra='allow') # Uncomment if needed


# Define the main Chart.js configuration model
class ChartConfig(BaseModel):
    type: ChartType
    data: ChartData
    options: Optional[Dict[str, Any]] = None
    plugins: Optional[List[Any]] = None
    # model_config = ConfigDict(extra='allow') # Uncomment if needed

# --- Validation Function ---

def validate_chart_config(
    config_dict: Dict[str, Any],
) -> Tuple[bool, Union[ChartConfig, ValidationError]]:
    try:
        validated = ChartConfig.model_validate(config_dict,strict=True)
        return True, validated
    except ValidationError as e:
        return False, e



# # --- Example Usage ---

# # Example 1: Your Valid Bar Chart Config
# bar_chart_config_dict ={'type': 'bar', 'data': {'labels': ['LUCKY STRIKE', 'LD', 'PHILIP MORRIS', 'CAMEL', 'BUSINESS ROYALS'], 'datasets': [{'label': 'DP Volume Share in 2023', 'data': [3.71, 3.0, 2.84, 0.98, None], 'backgroundColor': 'rgba(75, 192, 192, 0.6)'}, {'label': 'DP Volume Share in 2024', 'data': [7.45, 5.09, 4.81, 1.22, 1.95], 'backgroundColor': 'rgba(153, 102, 255, 0.6)'}]}, 'options': {'maintainAspectRatio': True}}

# print("--- Testing Valid Config ---")
# print(f" type of bar_chart_config_dict: {type(bar_chart_config_dict)}")
# is_valid_bar, result_bar = validate_chart_config(bar_chart_config_dict)
# print(f"Is Valid: {is_valid_bar}, Result: {result_bar}")
# if not is_valid_bar:
#   print("Validation Errors:\n", result_bar)
# # else:
#   print("Validated Config Object:", result_bar) # The actual Pydantic object
#   print("\nValidated Config JSON:\n", result_bar.model_dump_json(indent=2)) # Output as JSON

