import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Global config lives here — survives across repos and venv recreations.
GLOBAL_CONFIG_DIR = Path.home() / ".config" / "tech-team"
GLOBAL_CONFIG_FILE = GLOBAL_CONFIG_DIR / "config"


def _resolve_env_files() -> list[str]:
    """
    Resolution order (later files win):
      1. Global config (~/.config/tech-team/config)
      2. Local .env in cwd (lets per-project overrides still work)
    """
    files = []
    if GLOBAL_CONFIG_FILE.exists():
        files.append(str(GLOBAL_CONFIG_FILE))
    if Path(".env").exists():
        files.append(".env")
    return files or [".env"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_resolve_env_files(),
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


def read_global_key() -> str | None:
    """Return the API key from global config if present."""
    if not GLOBAL_CONFIG_FILE.exists():
        return None
    for line in GLOBAL_CONFIG_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("ANTHROPIC_API_KEY="):
            return line.split("=", 1)[1].strip()
    return None


def write_global_key(api_key: str) -> None:
    """Write (or replace) the API key in the global config file."""
    GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    GLOBAL_CONFIG_FILE.chmod(0o600) if GLOBAL_CONFIG_FILE.exists() else None

    existing: list[str] = []
    if GLOBAL_CONFIG_FILE.exists():
        existing = [
            line for line in GLOBAL_CONFIG_FILE.read_text(encoding="utf-8").splitlines()
            if not line.startswith("ANTHROPIC_API_KEY=")
        ]

    existing.append(f"ANTHROPIC_API_KEY={api_key}")
    GLOBAL_CONFIG_FILE.write_text("\n".join(existing) + "\n", encoding="utf-8")
    GLOBAL_CONFIG_FILE.chmod(0o600)


def find_repo_root(start: Path = Path(".")) -> Path:
    """Walk up from start until we find a .git directory or hit filesystem root."""
    current = start.resolve()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return start.resolve()
