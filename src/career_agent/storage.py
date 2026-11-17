"""Private local data storage helpers."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def home_dir(override: str | None = None) -> Path:
    return Path(override or os.environ.get("CAREER_AGENT_HOME", Path.home() / ".career-agent")).expanduser().resolve()


def load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def save(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        temp.chmod(0o600)
    except OSError:
        pass
    temp.replace(path)


def candidate_path(home: Path) -> Path:
    return home / "candidate.json"


def jobs_path(home: Path) -> Path:
    return home / "jobs.json"


def feeds_path(home: Path) -> Path:
    return home / "feeds.json"
