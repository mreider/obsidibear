"""Configuration file management for .obsidibear.json in vault root."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


CONFIG_FILENAME = ".obsidibear.json"


@dataclass
class Config:
    vault_path: Path
    bear_db_path: Optional[str] = None  # Override default Bear DB location
    exclude_tags: list = field(default_factory=list)
    push_delay: float = 0.5  # Seconds between push operations


def load_config(vault_path: Path) -> Config:
    """Load config from vault root, creating defaults if missing."""
    config_file = vault_path / CONFIG_FILENAME
    if config_file.exists():
        data = json.loads(config_file.read_text(encoding="utf-8"))
        return Config(
            vault_path=vault_path,
            bear_db_path=data.get("bear_db_path"),
            exclude_tags=data.get("exclude_tags", []),
            push_delay=data.get("push_delay", 0.5),
        )
    return Config(vault_path=vault_path)


def save_config(config: Config):
    """Save config to vault root."""
    config_file = config.vault_path / CONFIG_FILENAME
    data = {
        "vault_path": str(config.vault_path),
    }
    if config.bear_db_path:
        data["bear_db_path"] = config.bear_db_path
    if config.exclude_tags:
        data["exclude_tags"] = config.exclude_tags
    if config.push_delay != 0.5:
        data["push_delay"] = config.push_delay

    config_file.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
