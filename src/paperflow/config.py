import os
from dataclasses import dataclass

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    """PaperFlow configuration error."""


@dataclass(frozen=True)
class Settings:
    elsevier_api_key: str | None
    springer_oa_api_key: str | None
    springer_meta_api_key: str | None
    http_timeout: float = 60.0
    mineru_executable: str | None = None
    mineru_tier: str = "advanced"


def load_settings() -> Settings:
    load_dotenv()

    return Settings(
        elsevier_api_key=os.getenv("ELSEVIER_API_KEY"),
        springer_oa_api_key=os.getenv("SPRINGER_OA_API_KEY"),
        springer_meta_api_key=os.getenv("SPRINGER_META_API_KEY"),
        http_timeout=60.0,
        mineru_executable=os.getenv("MINERU_EXECUTABLE"),
        mineru_tier=os.getenv(
            "MINERU_TIER",
            "advanced",
        ),
    )


def require_elsevier_api_key(
    settings: Settings,
) -> str:
    if not settings.elsevier_api_key:
        raise ConfigError("ELSEVIER_API_KEY is not configured.")

    return settings.elsevier_api_key


def require_springer_oa_api_key(
    settings: Settings,
) -> str:
    if not settings.springer_oa_api_key:
        raise ConfigError("SPRINGER_OA_API_KEY is not configured.")

    return settings.springer_oa_api_key


def require_springer_meta_api_key(
    settings: Settings,
) -> str:
    if not settings.springer_meta_api_key:
        raise ConfigError("SPRINGER_META_API_KEY is not configured.")

    return settings.springer_meta_api_key


def require_mineru_executable(
    settings: Settings,
) -> str:
    if not settings.mineru_executable:
        raise ConfigError("MINERU_EXECUTABLE is not configured.")

    return settings.mineru_executable
