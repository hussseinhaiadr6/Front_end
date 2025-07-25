from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

import json5
from typing import List, Dict

import re
_KEY_RE = re.compile(
    r"(?P<prefix>(?<=\{|,))"
    r"(?P<ws>\s*)"
    r"([\"\'])"
    r"(?P<key>[A-Za-z_]\w*)"
    r"\3"
    r"(?P<post>\s*:)",
)




def _unquote_keys(src: str) -> str:
    """Remove quotes around valid JS identifier keys."""
    return _KEY_RE.sub(r"\g<prefix>\g<ws>\g<key>\g<post>", src)




def _sanitize_json_like(src: str) -> str:
    """Convert Python-style literals to JSON equivalents."""
    return (
        src
        .replace('True', 'true')
        .replace('False', 'false')
        .replace('None', 'null')
    )


def _preprocess(raw: str) -> str:
    """Apply all cleaning steps to enable JSON5 parsing."""
    return _sanitize_json_like(_unquote_keys(raw))





def load_chart_configs(
    raw: str
) -> List[Dict]:
    """
    Parses the string output from generate_validated_chart_configs
    back into a real list of dicts.
    """
    # We can re‑use your existing _preprocess logic to clean it up
    cleaned = _preprocess(raw)
    return json5.loads(cleaned)


def fetch_secret_from_keyvault( secret_name: str,key_vault_name= "batkv-ne-bee-dev-01") -> str:


    # Construct the Key Vault URL
    key_vault_url = f"https://{key_vault_name}.vault.azure.net"

    # Authenticate using DefaultAzureCredential
    credential = DefaultAzureCredential()

    # Create a SecretClient
    client = SecretClient(vault_url=key_vault_url, credential=credential)

    # Retrieve the secret
    retrieved_secret = client.get_secret(secret_name)

    return retrieved_secret.value  # Return the secret value


def get_llm(deployment_name):
   load_dotenv()
   KV_NAME="batkv-ne-bee-dev-01"
   AZURE_OPENAI_API_KEY_SECRET="Azure-OpenAI-API-Key"
   api_version = "2024-12-01-preview"
   llm = AzureChatOpenAI(
      api_key= "536b4db1fc1b4fee94c0e6a9094ccd51",
    #   api_key= fetch_secret_from_keyvault(AZURE_OPENAI_API_KEY_SECRET, KV_NAME),
      azure_deployment=deployment_name,  # or whatever model you're using
      api_version=api_version,
      temperature=0,
      azure_endpoint="https://batopenai-we-bee-prod-01.openai.azure.com/"

      
)
   return llm