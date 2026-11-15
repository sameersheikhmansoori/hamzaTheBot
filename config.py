"""
Configuration settings for the Telegram Link Distributor Bot.
"""

import os
from typing import List

# Try importing dotenv for local development with .env files
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()

# Comma-separated admin Telegram user IDs (e.g., "12345678,87654321")
raw_admin_ids = os.getenv("ADMIN_IDS", "").strip()
ADMIN_IDS: List[int] = []
if raw_admin_ids:
    for item in raw_admin_ids.split(","):
        cleaned = item.strip()
        if cleaned.isdigit():
            ADMIN_IDS.append(int(cleaned))


def is_admin(user_id: int) -> bool:
    """Check if a given user ID is in the admin list."""
    # If no admin IDs are configured, all users can be allowed in demo mode or restricted
    return user_id in ADMIN_IDS
