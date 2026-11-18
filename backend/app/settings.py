"""Runtime settings, read from environment variables (and a .env file if present)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=False)


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


@dataclass
class Settings:
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "anthropic").lower())
    anthropic_api_key: str | None = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY") or None)
    openai_api_key: str | None = field(default_factory=lambda: os.getenv("OPENAI_API_KEY") or None)
    coach_model: str = field(default_factory=lambda: os.getenv("COACH_MODEL", "claude-opus-5-5"))
    persona_model: str = field(default_factory=lambda: os.getenv("PERSONA_MODEL", "claude-sonnet-5-5"))
    # Safety classifier and LLM judge default to the coach model unless overridden.
    safety_model: str = field(default_factory=lambda: os.getenv("SAFETY_MODEL") or os.getenv("COACH_MODEL", "claude-opus-5-5"))
    judge_model: str = field(default_factory=lambda: os.getenv("JUDGE_MODEL") or os.getenv("COACH_MODEL", "claude-opus-5-5"))
    coach_temperature: float = field(default_factory=lambda: _f("COACH_TEMPERATURE", 0.7))
    persona_temperature: float = field(default_factory=lambda: _f("PERSONA_TEMPERATURE", 0.9))
    # Anthropic only: reasoning effort (current Claude models do not accept temperature).
    coach_effort: str = field(default_factory=lambda: os.getenv("COACH_EFFORT", "medium"))
    persona_effort: str = field(default_factory=lambda: os.getenv("PERSONA_EFFORT", "low"))
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'study.db'}"))
    admin_password: str | None = field(default_factory=lambda: os.getenv("ADMIN_PASSWORD") or None)
    survey_path: Path = field(default_factory=lambda: Path(os.getenv("SURVEY_CONFIG", ROOT / "backend" / "config" / "survey.json")))
    prompts_dir: Path = field(default_factory=lambda: Path(os.getenv("PROMPTS_DIR", ROOT / "backend" / "prompts")))
    frontend_dist: Path = field(default_factory=lambda: Path(os.getenv("FRONTEND_DIST", ROOT / "frontend" / "dist")))
    llm_timeout: float = field(default_factory=lambda: _f("LLM_TIMEOUT_SECONDS", 90))


settings = Settings()


def reload_settings() -> Settings:
    global settings
    load_dotenv(ROOT / ".env", override=False)
    settings = Settings()
    return settings
