"""
Uygulama ayarları - tüm konfigürasyonları merkezi olarak yönetir.
"""
import os
from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()

class Settings(BaseSettings):
    """Uygulama ayarları."""

    # LLM Providers
    google_api_key: Optional[str] = Field(default=None, alias="GOOGLE_API_KEY")
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")

    # Primary LLM
    # Desteklenen değerler: "gemini", "claude", "ollama_qwen"
    primary_llm_provider: str = Field(default="ollama_qwen", alias="PRIMARY_LLM_PROVIDER")
    gemini_model: str = Field(default="gemini-2.0-flash", alias="GEMINI_MODEL")
    claude_model: str = Field(default="claude-sonnet-4-20250514", alias="CLAUDE_MODEL")
    # Ollama üzerinden local Qwen
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_qwen_model: str = Field(default="qwen2.5:latest", alias="OLLAMA_QWEN_MODEL")

    # Redis
    redis_host: str = Field(default="localhost", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")
    redis_db: int = Field(default=0, alias="REDIS_DB")
    use_redis: bool = Field(default=False, alias="USE_REDIS")

    # Server
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    debug: bool = Field(default=True, alias="DEBUG")

    # Embedding
    embedding_model: str = Field(
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        alias="EMBEDDING_MODEL"
    )

    # Database
    database_url: str = Field(default="sqlite:///./university.db", alias="DATABASE_URL")

    # Paths
    base_dir: Path = Path(__file__).parent.parent
    data_dir: Path = base_dir / "data"
    chroma_dir: Path = base_dir / "chroma_db"

    class Config:
        env_file = ".env"
        extra = "ignore"

    def get_llm_config(self) -> dict:
        """Aktif LLM provider konfigürasyonunu döndürür."""
        if self.primary_llm_provider == "gemini" and self.google_api_key:
            return {
                "provider": "gemini",
                "api_key": self.google_api_key,
                "model": self.gemini_model
            }
        elif self.primary_llm_provider == "claude" and self.anthropic_api_key:
            return {
                "provider": "claude",
                "api_key": self.anthropic_api_key,
                "model": self.claude_model
            }
        elif self.primary_llm_provider == "ollama_qwen":
            return {
                "provider": "ollama_qwen",
                "api_key": None,
                "model": self.ollama_qwen_model,
                "base_url": self.ollama_base_url,
            }
        # Fallback
        if self.google_api_key:
            return {
                "provider": "gemini",
                "api_key": self.google_api_key,
                "model": self.gemini_model
            }
        if self.anthropic_api_key:
            return {
                "provider": "claude",
                "api_key": self.anthropic_api_key,
                "model": self.claude_model
            }
        return {"provider": "mock", "api_key": None, "model": None}


# Singleton instance
settings = Settings()
