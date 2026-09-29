"""Settings loaded from server/.env (see .env.example)."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

SERVER_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    ebay_client_id: str
    ebay_client_secret: str
    refresh_hours: float
    db_path: str
    watchapi_token: str = ""
    price_source: str = "auto"  # auto | thewatchapi | ebay


def load_settings() -> Settings:
    load_dotenv()
    refresh_hours = max(float(os.getenv("REFRESH_HOURS", "24")), 0.25)
    db_path = os.getenv("DB_PATH", "watchbox.db")
    if not os.path.isabs(db_path):
        db_path = str(SERVER_DIR / db_path)
    return Settings(
        ebay_client_id=os.getenv("EBAY_CLIENT_ID", ""),
        ebay_client_secret=os.getenv("EBAY_CLIENT_SECRET", ""),
        refresh_hours=refresh_hours,
        db_path=db_path,
        watchapi_token=os.getenv("THEWATCHAPI_TOKEN", ""),
        price_source=os.getenv("PRICE_SOURCE", "auto").strip().lower(),
    )
