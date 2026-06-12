import argparse
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import signal
import sys
import time

import pyautogui
import pyperclip

from clean_clipboard_and_paste import cleanup_text
from runtime_paths import log_path, run_path


LOG_PATH = log_path("clipboard_watcher.log")
STOP_PATH = run_path("clipboard_watcher.stop")


def log_event(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(f"{timestamp} {message}\n")


def read_clipboard() -> str:
    try:
        return pyperclip.paste()
    except pyperclip.PyperclipException as exc:
        log_event(f"clipboard_read_error error={exc!r}")
        return ""


def clipboard_owner_process_name() -> tuple[int | None, str]:
    if os.name != "nt":
        return None, ""

    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        hwnd = user32.GetClipboardOwner()
        if not hwnd:
            return None, ""

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
        if not pid.value:
            return None, ""

        process_query_limited_information = 0x1000
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid.value)
        if not handle:
            return pid.value, ""

        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buffer))
            ok = kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size))
            if not ok:
                return pid.value, ""
            return pid.value, Path(buffer.value).name
        finally:
            kernel32.CloseHandle(handle)
    except Exception as exc:
        log_event(f"clipboard_owner_error error={exc!r}")
        return None, ""


def looks_like_text_to_clean(text: str, min_chars: int) -> bool:
    stripped = text.strip()
    if len(stripped) < min_chars:
        return False
    if "\n" in stripped and len(stripped) < 80:
        return False
    return any(ch.isalpha() for ch in stripped)


def main() -> int:
    parser = argparse.ArgumentParser(description="Watch clipboard and clean/paste dictation output.")
    parser.add_argument("--poll-ms", type=int, default=100)
    parser.add_argument("--stable-ms", type=int, default=900)
    parser.add_argument("--min-chars", type=int, default=8)
    parser.add_argument("--no-paste", action="store_true")
    parser.add_argument(
        "--source-process",
        default="",
        help="only clean clipboard changes owned by this process name, for example OpenWhispr.exe",
    )
    args = parser.parse_args()

    running = True

    def stop_handler(_signum: int, _frame: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)

    if STOP_PATH.exists():
        STOP_PATH.unlink()

    poll_seconds = max(args.poll_ms, 25) / 1000
    stable_seconds = max(args.stable_ms, 100) / 1000

    last_seen = read_clipboard()
    candidate = ""
    candidate_owner_pid: int | None = None
    candidate_owner_name = ""
    candidate_since = 0.0
    suppress_text = ""
    processing = False

    log_event(
        "watcher_start "
        f"poll_ms={args.poll_ms} stable_ms={args.stable_ms} "
        f"min_chars={args.min_chars} no_paste={args.no_paste}"
    )

    while running and not STOP_PATH.exists():
        current = read_clipboard()
        now = time.perf_counter()

        if current == suppress_text:
            time.sleep(poll_seconds)
            continue

        if current != last_seen:
            last_seen = current
            candidate = current
            candidate_owner_pid, candidate_owner_name = clipboard_owner_process_name()
            candidate_since = now
            log_event(
                "clipboard_changed "
                f"len={len(current.strip())} "
                f"owner_pid={candidate_owner_pid} owner={candidate_owner_name}"
            )
            time.sleep(poll_seconds)
            continue

        source_process = args.source_process.strip().lower()
        if candidate and source_process and candidate_owner_name.lower() != source_process:
            if now - candidate_since >= stable_seconds:
                log_event(
                    "skip_source_mismatch "
                    f"wanted={args.source_process} "
                    f"owner_pid={candidate_owner_pid} owner={candidate_owner_name} "
                    f"len={len(candidate.strip())}"
                )
                candidate = ""
            time.sleep(poll_seconds)
            continue

        if (
            candidate
            and not processing
            and now - candidate_since >= stable_seconds
            and looks_like_text_to_clean(candidate, args.min_chars)
        ):
            raw_text = candidate.strip()
            candidate = ""
            processing = True
            log_event(f"cleanup_start raw_len={len(raw_text)}")
            try:
                data = cleanup_text(raw_text)
                if not data.get("ok"):
                    log_event(f"cleanup_failed response={data!r}")
                    continue
                cleaned = str(data.get("cleaned", "")).strip()
                if not cleaned:
                    log_event("cleanup_empty_result")
                    continue
                suppress_text = cleaned
                pyperclip.copy(cleaned)
                if not args.no_paste:
                    time.sleep(0.05)
                    pyautogui.hotkey("ctrl", "v")
                log_event(
                    "cleanup_ok "
                    f"raw_len={len(raw_text)} cleaned_len={len(cleaned)} "
                    f"model_elapsed={data.get('elapsed_seconds')} pasted={not args.no_paste}"
                )
            except Exception as exc:
                log_event(f"cleanup_exception error={exc!r}")
            finally:
                processing = False
                last_seen = read_clipboard()

        time.sleep(poll_seconds)

    log_event("watcher_stop")
    if STOP_PATH.exists():
        STOP_PATH.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
