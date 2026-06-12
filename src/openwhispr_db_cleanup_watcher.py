from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import os
import signal
import sqlite3
import sys
import time
from pathlib import Path

import pyautogui
import pyperclip

from clean_clipboard_and_paste import cleanup_text
from runtime_paths import log_path, run_path


DEFAULT_DB_PATH = (
    Path.home() / "AppData" / "Roaming" / "open-whispr" / "transcriptions.db"
)
LOG_PATH = log_path("openwhispr_db_watcher.log")
STOP_PATH = run_path("openwhispr_db_watcher.stop")
MUTEX_NAME = "Local\\LocalDictationOpenWhisprDbWatcher"


def log_event(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(f"{timestamp} {message}\n")


def connect_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=2)
    conn.row_factory = sqlite3.Row
    return conn


def current_max_id(db_path: Path) -> int:
    with connect_readonly(db_path) as conn:
        row = conn.execute("select coalesce(max(id), 0) as max_id from transcriptions").fetchone()
        return int(row["max_id"] or 0)


def fetch_rows_after(db_path: Path, start_id: int) -> list[sqlite3.Row]:
    with connect_readonly(db_path) as conn:
        return conn.execute(
            """
            select id, text, raw_text, status, provider, model, created_at, timestamp,
                   audio_duration_ms
            from transcriptions
            where id > ?
            order by id asc
            limit 100
            """,
            (start_id,),
        ).fetchall()


def paste_cleaned_text(
    text: str,
    no_paste: bool,
    paste_delay: float,
    replace_raw_paste: bool,
    undo_delay: float,
) -> None:
    if not no_paste and replace_raw_paste:
        time.sleep(max(undo_delay, 0))
        pyautogui.hotkey("ctrl", "z")
        time.sleep(0.05)

    pyperclip.copy(text)
    if not no_paste:
        time.sleep(max(paste_delay, 0))
        pyautogui.hotkey("ctrl", "v")


def clean_and_paste_row(
    row: sqlite3.Row,
    no_paste: bool,
    paste_delay: float,
    replace_raw_paste: bool,
    undo_delay: float,
) -> bool:
    row_id = int(row["id"])
    raw_text = (row["text"] or "").strip()
    if not raw_text:
        log_event(f"skip_empty id={row_id}")
        return False

    log_event(
        "cleanup_start "
        f"id={row_id} raw_len={len(raw_text)} "
        f"status={row['status']} provider={row['provider']} model={row['model']}"
    )
    try:
        data = cleanup_text(raw_text)
        if not data.get("ok"):
            log_event(f"cleanup_failed id={row_id} response={data!r}")
            return False

        cleaned = str(data.get("cleaned", "")).strip()
        if not cleaned:
            log_event(f"cleanup_empty_result id={row_id}")
            return False

        paste_cleaned_text(
            cleaned,
            no_paste=no_paste,
            paste_delay=paste_delay,
            replace_raw_paste=replace_raw_paste,
            undo_delay=undo_delay,
        )
        log_event(
            "cleanup_ok "
            f"id={row_id} raw_len={len(raw_text)} cleaned_len={len(cleaned)} "
            f"model_elapsed={data.get('elapsed_seconds')} "
            f"mode={data.get('cleanup_mode')} pasted={not no_paste} "
            f"replace_raw_paste={replace_raw_paste}"
        )
        return True
    except Exception as exc:
        log_event(f"cleanup_exception id={row_id} error={exc!r}")
        return False


def acquire_single_instance() -> int | None:
    if os.name != "nt":
        return 1

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    ctypes.set_last_error(0)
    handle = kernel32.CreateMutexW(None, True, MUTEX_NAME)
    if not handle:
        log_event(f"mutex_error error={ctypes.get_last_error()}")
        return None

    error_already_exists = 183
    if ctypes.get_last_error() == error_already_exists:
        kernel32.CloseHandle(handle)
        log_event("watcher_already_running")
        return None

    return int(handle)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Watch OpenWhispr's transcription DB and clean/paste completed dictation."
    )
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--poll-ms", type=int, default=250)
    parser.add_argument("--no-paste", action="store_true")
    parser.add_argument("--paste-delay", type=float, default=0.15)
    parser.add_argument(
        "--replace-raw-paste",
        action="store_true",
        help="send Ctrl+Z before pasting cleaned text; use when OpenWhispr auto-paste is enabled",
    )
    parser.add_argument(
        "--undo-delay",
        type=float,
        default=0.25,
        help="seconds to wait before Ctrl+Z in replace-raw-paste mode",
    )
    parser.add_argument(
        "--process-existing-latest",
        action="store_true",
        help="process the current latest row once on startup; normally disabled",
    )
    args = parser.parse_args()

    db_path = args.db_path
    if not db_path.exists():
        log_event(f"db_missing path={db_path}")
        print(f"OpenWhispr database not found: {db_path}", file=sys.stderr)
        return 1

    mutex_handle = acquire_single_instance()
    if mutex_handle is None:
        return 0

    running = True

    def stop_handler(_signum: int, _frame: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)

    if STOP_PATH.exists():
        STOP_PATH.unlink()

    poll_seconds = max(args.poll_ms, 100) / 1000
    processed_ids: set[int] = set()
    pending_ids: set[int] = set()
    start_id = current_max_id(db_path)
    if args.process_existing_latest and start_id > 0:
        start_id -= 1

    log_event(
        "watcher_start "
        f"db={db_path} start_id={start_id} poll_ms={args.poll_ms} "
        f"no_paste={args.no_paste} replace_raw_paste={args.replace_raw_paste}"
    )

    while running and not STOP_PATH.exists():
        try:
            rows = fetch_rows_after(db_path, start_id)
        except sqlite3.Error as exc:
            log_event(f"db_read_error error={exc!r}")
            time.sleep(poll_seconds)
            continue

        for row in rows:
            row_id = int(row["id"])
            if row_id in processed_ids:
                continue

            status = (row["status"] or "").lower()
            text_len = len((row["text"] or "").strip())
            if status != "completed":
                if row_id not in pending_ids:
                    pending_ids.add(row_id)
                    log_event(f"pending id={row_id} status={row['status']} text_len={text_len}")
                continue

            if text_len == 0:
                processed_ids.add(row_id)
                log_event(f"skip_completed_empty id={row_id}")
                continue

            clean_and_paste_row(
                row,
                no_paste=args.no_paste,
                paste_delay=args.paste_delay,
                replace_raw_paste=args.replace_raw_paste,
                undo_delay=args.undo_delay,
            )
            processed_ids.add(row_id)

        time.sleep(poll_seconds)

    log_event("watcher_stop")
    if STOP_PATH.exists():
        STOP_PATH.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
