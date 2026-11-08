"""Central application configuration using pydantic-settings.

Secures all database credentials, Census API keys, and OpenRouter settings
without hardcoding values or leaking secrets in logs/exceptions.
"""

from typing import Any

from openai import OpenAI
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # PostgreSQL Database Settings
    POSTGRES_DB: str = Field(..., description="PostgreSQL database name")
    POSTGRES_USER: str = Field(..., description="PostgreSQL user name")
    POSTGRES_PASSWORD: SecretStr = Field(..., description="PostgreSQL password")
    POSTGRES_HOST: str = Field(default="localhost", description="PostgreSQL host")
    POSTGRES_PORT: int = Field(default=5432, description="PostgreSQL port")

    # API Keys & Third-Party Configuration
    CENSUS_API_KEY: SecretStr = Field(..., description="U.S. Census API Key")
    OPENROUTER_API_KEY: SecretStr = Field(..., description="OpenRouter API Key")
    OPENROUTER_MODEL: str = Field(
        default="anthropic/claude-3.5-sonnet",
        description="Default model identifier on OpenRouter",
    )

    @property
    def database_url(self) -> str:
        """Construct PostgreSQL connection string securely."""
        password = self.POSTGRES_PASSWORD.get_secret_value()
        return f"postgresql://{self.POSTGRES_USER}:{password}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    def get_openrouter_client(self, **kwargs: Any) -> OpenAI:
        """Construct an OpenAI SDK client pre-configured for OpenRouter API routing."""
        return OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self.OPENROUTER_API_KEY.get_secret_value(),
            default_headers={
                "HTTP-Referer": "https://github.com/local-election-pipeline",
                "X-Title": "Election Data Pipeline",
            },
            **kwargs,
        )


# Singleton settings instance for execution imports
settings = Settings()
