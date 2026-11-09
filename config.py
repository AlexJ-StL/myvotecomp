"""Central application configuration using pydantic-settings.

Secures all database credentials, Census API keys, and OpenRouter settings
without hardcoding values or leaking secrets in logs/exceptions.
"""

from typing import Any

from openai import OpenAI
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


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
    POSTGRES_HOST: str = Field(..., description="PostgreSQL host")
    POSTGRES_PORT: int = Field(
        ...,
        ge=1,
        le=65535,
        description="PostgreSQL port",
    )

    # API Keys & Third-Party Configuration
    CENSUS_API_KEY: SecretStr = Field(..., description="U.S. Census API Key")
    OPENROUTER_API_KEY: SecretStr = Field(..., description="OpenRouter API Key")
    OPENROUTER_MODEL: str = Field(
        ...,
        description="Default model identifier on OpenRouter",
    )

    @property
    def database_url(self) -> URL:
        """Construct PostgreSQL connection string securely."""
        return URL.create(
            drivername="postgresql+psycopg2",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD.get_secret_value(),
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        )

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


def get_settings() -> Settings:
    """Load settings when an application entry point actually needs them."""
    return Settings()
