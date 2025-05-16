# filename: config.py
import os
# Recommended: Use python-dotenv for environment variables (pip install python-dotenv)
# from dotenv import load_dotenv
# load_dotenv()

# ==============================================================================
# !!! CRITICAL SECURITY WARNING !!!
# ==============================================================================
# DO NOT commit sensitive information like OTP secrets or passwords directly
# into your source code repository (like Git).
# PREFERRED METHODS:
# 1. Environment Variables: Set OTP_SECRET, DEFAULT_PASSWORD etc. in your
#    operating system's environment. The code below will use them if found.
# 2. Secrets Management Tools: Use tools like HashiCorp Vault, AWS Secrets Manager,
#    Azure Key Vault, or Doppler for production environments.
# 3. .env Files (for local development ONLY): Store secrets in a `.env` file
#    in your project root (ensure `.env` is listed in your `.gitignore` file)
#    and use `python-dotenv` to load them.
#
# Storing secrets directly in code is a major security risk.
# The hardcoded values below are **EXAMPLES ONLY** and **MUST** be replaced
# with a secure method before deployment or sharing.
# ==============================================================================

# --- Required Configuration ---
# Load from environment variables first, then fallback to hardcoded (unsafe) example
OTP_SECRET = 'TAPHLYTABSKHTZWM' # <-- REPLACE or set ENV VAR
DRIVER_PATH = 'chromedriver.exe' # Verify path or set ENV VAR
DOWNLOAD_BASE_PATH = os.path.abspath(r"D:\OneDrive\KT\Checking") # Verify path or set ENV VAR

# --- Optional Configuration (UI Defaults) ---
DEFAULT_EMAIL = os.getenv('DEFAULT_EMAIL', 'user')
# Set DEFAULT_PASSWORD environment variable or leave empty for UI input (recommended)
DEFAULT_PASSWORD = os.getenv('DEFAULT_PASSWORD', 'pass') # <-- REMOVE or set ENV VAR, avoid hardcoding password

# --- Other Configuration ---
# List of report URLs that require region selection
REGION_REQUIRED_REPORT_URLS = [
    'https://bi.nhathuoclongchau.com.vn/MIS/PHAR/PHARFAF030.aspx'
    # Add other report URLs here if they need region selection
]


# --- Validation and Warnings ---
if not OTP_SECRET or OTP_SECRET == 'TAPHLYTABSKHTZWM': # Check against the example value
    print("\n" + "="*60)
    print("== WARNING: OTP_SECRET is using the default example value or is empty! ==")
    print("== Please configure it securely via Environment Variables or other methods. ==")
    print("="*60 + "\n")

if DEFAULT_PASSWORD and DEFAULT_PASSWORD != '': # Check if password is hardcoded
    print("\n" + "="*60)
    print("== WARNING: DEFAULT_PASSWORD is set in config.py! ==")
    print("== It's highly recommended to use Environment Variables or leave it empty ==")
    print("== for the user to input it in the UI. ==")
    print("="*60 + "\n")

if not os.path.exists(DRIVER_PATH):
     print(f"\nWARNING: ChromeDriver path does not exist: {DRIVER_PATH}. Automation will likely fail. Check the path or set the CHROMEDRIVER_PATH environment variable.\n")

if not os.path.exists(DOWNLOAD_BASE_PATH):
     print(f"\nWARNING: Download base path does not exist: {DOWNLOAD_BASE_PATH}. The application will attempt to create it, but please verify the configuration.\n")

REPORTS = [
    {
        "name": "FAF030",
        "url": "https://bi.nhathuoclongchau.com.vn/MIS/PHAR/PHARFAF030.aspx"
    }
]

# --- Email Module Defaults ---
DEFAULT_SENDER = DEFAULT_EMAIL
EMAIL_BATCH_SIZE = int(os.getenv('EMAIL_BATCH_SIZE', '50'))
EMAIL_PAUSE_SECONDS = int(os.getenv('EMAIL_PAUSE_SECONDS', '5'))
EMAIL_LOG_PATH = os.getenv('EMAIL_LOG_PATH', os.path.abspath('email_log.csv'))
