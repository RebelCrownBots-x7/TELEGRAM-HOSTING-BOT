"""
REBEL CROWN BOT HOSTING - Configuration Module
Loads settings from .env and provides defaults + runtime customization.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Base paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STORAGE_DIR = BASE_DIR / "storage"
RUNTIME_DIR = BASE_DIR / "runtime"
LOGS_DIR = BASE_DIR / "logs"
UPLOADS_DIR = STORAGE_DIR / "uploads"
BOTS_DIR = STORAGE_DIR / "bots"
EXPORTS_DIR = STORAGE_DIR / "exports"
USERS_DIR = STORAGE_DIR / "users"
BACKUPS_DIR = STORAGE_DIR / "backups"

# Ensure directories exist
for d in [DATA_DIR, STORAGE_DIR, RUNTIME_DIR, LOGS_DIR, UPLOADS_DIR,
          BOTS_DIR, EXPORTS_DIR, USERS_DIR, BACKUPS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Load .env
load_dotenv(BASE_DIR / ".env")

# Required secrets
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Admin IDs — supports both the newer plural ADMIN_IDS (comma-separated,
# e.g. "111111,222222") and the original singular ADMIN_ID for backward
# compatibility with existing deployments. Both are honoured together.
_admin_ids_raw = os.getenv("ADMIN_IDS", "").strip()
_admin_id_raw = os.getenv("ADMIN_ID", "").strip()
ADMIN_IDS = {p.strip() for p in _admin_ids_raw.split(",") if p.strip()}
if _admin_id_raw:
    ADMIN_IDS.add(_admin_id_raw)
# ADMIN_ID kept as the first configured admin for any code/messages that
# still expect a single "primary admin" id (e.g. notifications).
ADMIN_ID = _admin_id_raw or (sorted(ADMIN_IDS)[0] if ADMIN_IDS else "")

# Support (defaults, overridable via settings table)
WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER", "79522385503").strip()
TELEGRAM_SUPPORT = os.getenv("TELEGRAM_SUPPORT", "RebelCrownX7").strip()

# Paths
DATABASE_PATH = os.getenv("DATABASE_PATH", str(DATA_DIR / "rebel_crown.db"))
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "5"))
MAX_UPLOAD_SIZE = MAX_UPLOAD_SIZE_MB * 1024 * 1024

# ZIP hosting limits (kept separate from the .py limit — projects are bigger)
MAX_ZIP_SIZE_MB = int(os.getenv("MAX_ZIP_SIZE_MB", "25"))
MAX_ZIP_SIZE = MAX_ZIP_SIZE_MB * 1024 * 1024
# Guard against zip-bombs: caps on extracted content
MAX_ZIP_EXTRACTED_SIZE_MB = int(os.getenv("MAX_ZIP_EXTRACTED_SIZE_MB", "100"))
MAX_ZIP_EXTRACTED_SIZE = MAX_ZIP_EXTRACTED_SIZE_MB * 1024 * 1024
MAX_ZIP_FILE_COUNT = int(os.getenv("MAX_ZIP_FILE_COUNT", "2000"))

# Branding defaults
BRAND_NAME = os.getenv("BRAND_NAME", "REBEL CROWN 👑 BOT HOSTING").strip()
BRAND_SHORT = "REBEL CROWN"

# Default settings (stored in DB, these are fallbacks — only used to SEED
# the settings table on first run; an existing database is never overwritten)
DEFAULT_SETTINGS = {
    # Free hosting
    "free_hosting_enabled": "1",
    "free_bot_limit": os.getenv("FREE_BOT_LIMIT", "1"),
    "free_hosting_days": os.getenv("FREE_HOSTING_DAYS", "10"),

    # Credits
    "starting_credits": os.getenv("STARTING_CREDITS", "0"),
    "referral_reward_credits": os.getenv("REFERRAL_REWARD_CREDITS", "5"),
    "hosting_cost_credits_per_day": "1",

    # Referral
    "referral_enabled": "1",
    "referral_min_referrals": "0",

    # Hosting
    "default_hosting_days": os.getenv("DEFAULT_HOSTING_DAYS", "10"),
    "max_hosting_days": os.getenv("MAX_HOSTING_DAYS", "365"),
    "auto_restart": "1",
    # 0 = every request needs manual admin approval, 1 = auto-approved.
    # Admin ALWAYS still receives the uploaded file either way (see deploy handler).
    "auto_accept_hosting": os.getenv("AUTO_ACCEPT_HOSTING", "0"),
    "expiry_reminder_days": "3,1",
    "expiry_reminder_hours": "24,1",

    # Support
    "whatsapp_number": WHATSAPP_NUMBER,
    "telegram_support": TELEGRAM_SUPPORT,
    "support_text": "Contact our support team for help.",

    # UI / Messages (can be customized)
    "welcome_extra": "",
    "brand_name": BRAND_NAME,
}

def is_admin(user_id) -> bool:
    """Check if user_id is one of the configured admins (ADMIN_IDS / ADMIN_ID)."""
    if not ADMIN_IDS:
        return False
    return str(user_id) in ADMIN_IDS

def validate_config():
    """Validate essential configuration. Returns (ok, message)."""
    if not BOT_TOKEN or BOT_TOKEN == "PASTE_YOUR_BOT_TOKEN_HERE":
        return False, "BOT_TOKEN is not set in .env"
    if not ADMIN_IDS:
        return False, "ADMIN_IDS (or ADMIN_ID) is not set in .env"
    for a in ADMIN_IDS:
        try:
            int(a)
        except ValueError:
            return False, f"ADMIN_IDS must be numeric Telegram user IDs (got '{a}')"
    return True, "OK"

def get_whatsapp_link(number: str = None) -> str:
    num = (number or WHATSAPP_NUMBER).replace("+", "").replace(" ", "").replace("-", "")
    return f"https://wa.me/{num}"

def mask_token(token: str) -> str:
    """Mask bot token for safe display."""
    if not token or len(token) < 10:
        return "***"
    return token[:6] + "..." + token[-4:]
