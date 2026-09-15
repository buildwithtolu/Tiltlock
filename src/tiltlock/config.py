"""Configuration loader for TiltLock."""

from pathlib import Path
from typing import Optional
import yaml
from pydantic import BaseModel, Field


class DetectionConfig(BaseModel):
    loss_streak_n: int = 3
    loss_streak_window_sec: int = 1200
    reentry_after_stop_sec: int = 60
    size_escalation_ratio: float = 2.0
    sl_tamper_while_drawdown: bool = True


class CooldownConfig(BaseModel):
    min_minutes: int = 15
    max_minutes: int = 120
    default_minutes: int = 45


class PolicyConfig(BaseModel):
    flatten_on_lock: bool = False
    demo_auto_accept_seconds: int = 3
    qwen_api_url: str = "https://hackathon.bitgetops.com/v1"
    qwen_model: str = "qwen3.8-max"


class PaperConfig(BaseModel):
    poll_interval_sec: int = 5
    max_polls: int = 60


class AppConfig(BaseModel):
    detection: DetectionConfig = Field(default_factory=DetectionConfig)
    cooldown: CooldownConfig = Field(default_factory=CooldownConfig)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)
    paper: PaperConfig = Field(default_factory=PaperConfig)

    @classmethod
    def find_repo_root(cls) -> Path:
        """Locates the tiltlock repository root directory."""
        current = Path(__file__).resolve().parent
        for p in [current, current.parent, current.parent.parent]:
            if (p / "config.yaml").exists() or (p / "pyproject.toml").exists():
                return p
        return current.parent.parent

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "AppConfig":
        if config_path is None:
            root = cls.find_repo_root()
            config_path = root / "config.yaml"

        if not config_path.exists():
            return cls()

        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        return cls(**data)


# Global singleton
_CONFIG: Optional[AppConfig] = None


def get_config() -> AppConfig:
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = AppConfig.load()
    return _CONFIG
