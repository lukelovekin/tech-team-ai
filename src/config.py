from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="TECH_TEAM_",
        populate_by_name=True,
        extra="ignore",
    )

    anthropic_api_key: str = Field(alias="ANTHROPIC_API_KEY")
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 8192
    shell_timeout: int = 120


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def find_repo_root(start: Path = Path(".")) -> Path:
    """Walk up from start until we find a .git directory or hit filesystem root."""
    current = start.resolve()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return start.resolve()
