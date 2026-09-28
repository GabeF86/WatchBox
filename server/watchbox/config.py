"""Settings loaded from server/.env (see .env.example)."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    ebay_client_id: str
    ebay_client_secret: str
    refresh_hours: float
    db_path: str


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        ebay_client_id=os.getenv("EBAY_CLIENT_ID", ""),
        ebay_client_secret=os.getenv("EBAY_CLIENT_SECRET", ""),
        refresh_hours=float(os.getenv("REFRESH_HOURS", "6")),
        db_path=os.getenv("DB_PATH", "watchbox.db"),
    )
