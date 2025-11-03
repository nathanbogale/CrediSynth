import os
from dotenv import load_dotenv

# Load local .env if present so dev and Docker can share config patterns
load_dotenv()


class Settings:
    APP_NAME: str = os.getenv("APP_NAME", "CrediSynth QAA")
    APP_VERSION: str = os.getenv("APP_VERSION", "1.0.0")

    GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")

    # Default to disabling mock mode unless explicitly enabled
    MOCK_MODE: bool = os.getenv("MOCK_MODE", "false").lower() in ("1", "true", "yes")

    REQUEST_TIMEOUT_SECONDS: float = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "12.0"))


settings = Settings()