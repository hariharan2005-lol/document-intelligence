"""Application configuration management using Pydantic Settings."""
from pathlib import Path
from typing import Set, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for Document Intelligence service."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    APP_NAME: str = "Document Intelligence Pipeline"
    DEBUG: bool = False
    
    # Storage and DB
    DATABASE_URL: str = "sqlite:///./documents.db"
    STORAGE_DIR: Path = Path("./storage/documents")
    
    # Upload constraints
    MAX_UPLOAD_SIZE_BYTES: int = 15 * 1024 * 1024  # 15 MB
    ALLOWED_EXTENSIONS: Set[str] = {".pdf", ".docx", ".png", ".jpg", ".jpeg"}
    
    # LLM configurations
    LLM_PROVIDER: str = "openai"  # "openai", "anthropic", "gemini", "mock"
    
    # OpenAI Configuration
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_BASE_URL: Optional[str] = None
    
    # Anthropic Configuration
    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_MODEL: str = "claude-3-5-sonnet-20241022"
    
    # Gemini Configuration
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-1.5-flash"
    
    # Fallback to heuristic if LLM API call fails or API key is not configured
    ENABLE_HEURISTIC_FALLBACK: bool = True
    
    # OCR configurations
    TESSERACT_CMD: Optional[str] = None


settings = Settings()

# Ensure storage directory exists
settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
