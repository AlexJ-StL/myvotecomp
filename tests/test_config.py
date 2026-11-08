import pytest
from pydantic import ValidationError

from config import Settings

DATABASE_ENV = (
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
)
REQUIRED_ENV = (
    *DATABASE_ENV,
    "CENSUS_API_KEY",
    "OPENROUTER_API_KEY",
    "OPENROUTER_MODEL",
)


def clear_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in REQUIRED_ENV:
        monkeypatch.delenv(name, raising=False)


def set_valid_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "POSTGRES_DB": "election_db",
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": "safe-test-password",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "CENSUS_API_KEY": "safe-test-census-key",
        "OPENROUTER_API_KEY": "safe-test-openrouter-key",
        "OPENROUTER_MODEL": "test/provider-model",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_settings_load_required_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_settings_env(monkeypatch)
    set_valid_settings_env(monkeypatch)

    # Disable disk .env loading during monkeypatch testing
    settings = Settings(_env_file=None)

    assert settings.POSTGRES_DB == "election_db"
    assert settings.POSTGRES_USER == "postgres"
    assert settings.POSTGRES_HOST == "localhost"
    assert settings.POSTGRES_PORT == 5432
    assert settings.POSTGRES_PASSWORD.get_secret_value() == "safe-test-password"
    assert settings.CENSUS_API_KEY.get_secret_value() == "safe-test-census-key"
    assert settings.OPENROUTER_API_KEY.get_secret_value() == "safe-test-openrouter-key"
    assert settings.OPENROUTER_MODEL == "test/provider-model"


def test_settings_reject_missing_required_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_settings_env(monkeypatch)
    set_valid_settings_env(monkeypatch)

    for missing_name in REQUIRED_ENV:
        monkeypatch.delenv(missing_name)
        with pytest.raises(ValidationError):
            Settings(_env_file=None)
        monkeypatch.setenv(missing_name, "restored-test-value")


def test_settings_reject_malformed_postgres_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_settings_env(monkeypatch)
    set_valid_settings_env(monkeypatch)
    monkeypatch.setenv("POSTGRES_PORT", "not-a-port")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_validation_error_does_not_expose_configured_secrets(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    clear_settings_env(monkeypatch)
    set_valid_settings_env(monkeypatch)
    secret = "sensitive-openrouter-key-for-redaction-test"
    monkeypatch.setenv("OPENROUTER_API_KEY", secret)
    monkeypatch.setenv("POSTGRES_PORT", "not-a-port")

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    assert secret not in str(exc_info.value)
    assert secret not in caplog.text
