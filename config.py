import os
from pathlib import Path

from dotenv import load_dotenv

# Загружаем .env из корня проекта
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


# === FastAPI/Flask ===
SECRET_KEY = os.environ["SECRET_KEY"]

# === Steam API ===
STEAM_API_KEY = os.environ["STEAM_API_KEY"]

# === URL приложения ===
BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000")

# === База данных ===
DB_USER = os.environ["DB_USER"]
DB_PASSWORD = os.environ["DB_PASSWORD"]
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_NAME = os.environ["DB_NAME"]

# === Режим разработки ===
DEBUG = _get_bool("DEBUG", default=False)