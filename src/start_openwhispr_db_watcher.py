from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from runtime_paths import ROOT_DIR

SRC_DIR = Path(__file__).resolve().parent
ROOT = ROOT_DIR
PYTHONW = (
    Path.home()
    / "AppData"
    / "Local"
    / "Programs"
    / "Python"
    / "Python312-arm64"
    / "pythonw.exe"
)
RUNNER = SRC_DIR / "run_openwhispr_db_watcher.py"


def main() -> int:
    parser = argparse.ArgumentParser(description="Start the OpenWhispr DB cleanup watcher.")
    parser.add_argument("--no-paste", action="store_true")
    parser.add_argument(
        "--replace-raw-paste",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="undo OpenWhispr's raw auto-paste before pasting cleaned text",
    )
    args = parser.parse_args()

    if not PYTHONW.exists():
        print(f"Expected pythonw.exe was not found: {PYTHONW}", file=sys.stderr)
        return 1

    command = [str(PYTHONW), str(RUNNER)]
    if args.no_paste:
        command.append("--no-paste")
    if args.replace_raw_paste:
        command.append("--replace-raw-paste")

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

    env = os.environ.copy()
    env["PYTHONPYCACHEPREFIX"] = str(ROOT / "cache" / "pycache")

    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        creationflags=creationflags,
    )
    print(f"OpenWhispr DB cleanup watcher launch requested. PID {process.pid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
