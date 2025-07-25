from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

help_text=f"""
🛍️ **Retail Audit Assistant**  
Hi! I’m your **APMEA West Retail Audit AI Assistant**, here to help you analyze retail audit data with ease. Below is a quick overview of the data I can access and how you can get the most out of me.

📊 **Available Markets**  
I currently cover data for the following markets:  
- **UZB** - Uzbekistan  
- **IRQ** - Iraq  
- **ALG** - Algeria  
- **KSA** - Saudi Arabia  
- **KAZ** - Kazakhstan  
- **PAK** - Pakistan  

🗂️ **Key Data Fields**  

### 🕒 **Time & Location**  
- **Retail_audit_month**: Month of the audit  
- **Market**: Market codes and names  
- **CITY**: City-level data per market  

### 📦 **Product Classification**  
- **Category**: Product categories per market  
- **Manufacturer**: Manufacturers by market  

### 🏷️ **Product Hierarchy**  
- **Brand House**: Manufacturer-level brands  
- **Brand Range Core**: Core product families within brands  
- **SKU**: Specific product variant names  

### 🔬 **Product Attributes**  
- **TAR_LEVEL**  
- **FLAVOR**  
- **BLEND**  
- **PRICE_SEGMENT**  

### 📈 **Performance Metrics**  
- **DP / DNP**: Duty Paid / Duty Not Paid status  
- **DP_value_share_% / DNP_value_share_%**: Value share %  
- **DP_vol_share_% / DNP_vol_share_%**: Volume share %  
- **Val_Sales**: Sales value (local currency)  
- **Vol_Sales**: Sales volume  
- **Price_per_Unit**: Retail selling price per unit  
- **Wtd_Selling_Dist**: Weighted distribution  
- **Num_Selling_Dist**: Numeric distribution  

💡 **How to Ask Me Questions**  
To get the best results, be specific! Here are some example prompts you can try:

- **“List all the markets you have.”**  
- **“Give me a list of all Kent SKUs in market KSA.”**  
- **“What is the DP Volume Share for the top 5 Brands in Algeria (National) for 2023–2024, including absolute gain?”**  
  - *Follow-up*: **“For each of these brands, show the top 3 SKUs with the highest DP volume share increase over the same period.”**  
- **“What is the weighted average unit price for PREMIUM SKUs of the brand MARLBORO in Algeria national city (year 2024)? Use SKU-level volume and price data.”**  
- **“City-wise sales volume growth for MARLBORO & DUNHILL in KSA from 2023 to 2024.”**  
  - For each city, show:  
    - **2023 Vol_Sales**  
    - **2024 Vol_Sales**  
    - **% growth for MARLBORO and DUNHILL**  
        """



def fetch_secret_from_keyvault( secret_name: str,key_vault_name= "batkv-ne-bee-prod-01") -> str:


    # Construct the Key Vault URL
    key_vault_url = f"https://{key_vault_name}.vault.azure.net"
    # print(f"Key vault URL {key_vault_name}")

    # Authenticate using DefaultAzureCredential
    credential = DefaultAzureCredential()

    # Create a SecretClient
    client = SecretClient(vault_url=key_vault_url, credential=credential)

    # Retrieve the secret
    retrieved_secret = client.get_secret(secret_name)

    return retrieved_secret.value  # Return the secret value
