from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Agentic Code Reviewer API"
    frontend_origin: str = "http://localhost:5173"
    storage_dir: Path = Path("storage")
    upload_dir: Path = Path("storage/uploads")
    extracted_dir: Path = Path("storage/extracted")
    database_path: Path = Path("storage/code_reviews.sqlite3")
    max_zip_mb: int = 80
    max_file_kb: int = 900
    llm_provider: str = "offline"
    deepseek_api_key: str | None = None
    deepseek_model: str = "deepseek-chat"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-1.5-flash"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
settings.storage_dir.mkdir(parents=True, exist_ok=True)
settings.upload_dir.mkdir(parents=True, exist_ok=True)
settings.extracted_dir.mkdir(parents=True, exist_ok=True)
