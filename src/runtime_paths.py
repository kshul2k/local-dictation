from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
LOG_DIR = ROOT_DIR / "logs"
RUN_DIR = ROOT_DIR / "run"
CACHE_DIR = ROOT_DIR / "cache"
DIAGNOSTICS_DIR = ROOT_DIR / "diagnostics"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_path(name: str) -> Path:
    return ensure_dir(LOG_DIR) / name


def run_path(name: str) -> Path:
    return ensure_dir(RUN_DIR) / name
