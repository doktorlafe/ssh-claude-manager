from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "ccm" / "config.toml"
LOCAL = "local"


@dataclass
class Config:
    hosts: list[str] = field(default_factory=lambda: [LOCAL])
    poll_seconds: float = 3.0
    default_dir: str = "~"
    history: int = 30


def load(path: Path = CONFIG_PATH) -> Config:
    cfg = Config()
    if path.exists():
        data = tomllib.loads(path.read_text())
        for key in ("hosts", "poll_seconds", "default_dir", "history"):
            if key in data:
                setattr(cfg, key, data[key])
    bad = [h for h in cfg.hosts if not isinstance(h, str) or not h or h.startswith("-")]
    if bad or not cfg.hosts:
        raise SystemExit(f"ccm: invalid hosts in config: {bad or 'empty list'}")
    return cfg
