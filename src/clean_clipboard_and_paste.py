import argparse
import json
import sys
import time
from urllib import error, request

import pyautogui
import pyperclip

from runtime_paths import log_path


SERVER_URL = "http://127.0.0.1:8765/cleanup"
TIMEOUT_SECONDS = 30
LOG_PATH = log_path("cleanup_client.log")


def _format_seconds(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.3f}s"
    return "unknown"


def log_event(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with LOG_PATH.open("a", encoding="utf-8") as log_file:
            log_file.write(f"{timestamp} {message}\n")
    except OSError:
        pass


def read_clipboard() -> str:
    try:
        return pyperclip.paste()
    except pyperclip.PyperclipException as exc:
        log_event(f"clipboard_read_error error={exc!r}")
        return ""


def wait_for_clipboard_change(initial_text: str, timeout_seconds: float, stable_ms: int) -> str:
    deadline = time.perf_counter() + timeout_seconds
    candidate = ""
    candidate_seen_at = 0.0
    stable_seconds = stable_ms / 1000

    while time.perf_counter() < deadline:
        current = read_clipboard()
        if current.strip() and current != initial_text:
            now = time.perf_counter()
            if current != candidate:
                candidate = current
                candidate_seen_at = now
            elif now - candidate_seen_at >= stable_seconds:
                return candidate
        time.sleep(0.05)

    return ""


def cleanup_text(raw_text: str) -> dict[str, object]:
    payload = json.dumps({"text": raw_text}).encode("utf-8")
    req = request.Request(
        SERVER_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean clipboard text and paste it.")
    parser.add_argument("--no-paste", action="store_true", help="copy cleaned text but do not paste")
    parser.add_argument(
        "--wait-for-clipboard-change",
        action="store_true",
        help="wait until the clipboard changes before reading text",
    )
    parser.add_argument("--wait-timeout", type=float, default=15.0, help="seconds to wait for clipboard text")
    parser.add_argument("--stable-ms", type=int, default=350, help="clipboard must be unchanged this long")
    parser.add_argument("--paste-delay", type=float, default=0.05, help="seconds to wait before Ctrl+V")
    args = parser.parse_args()

    initial_clipboard = read_clipboard()
    if args.wait_for_clipboard_change:
        log_event(f"wait_for_clipboard_change initial_len={len(initial_clipboard)} timeout={args.wait_timeout}")
        raw_text = wait_for_clipboard_change(initial_clipboard, args.wait_timeout, args.stable_ms)
        if not raw_text:
            log_event("no_clipboard_change")
            return 2
    else:
        raw_text = initial_clipboard

    raw_text = raw_text.strip()
    if not raw_text:
        log_event("empty_clipboard")
        return 0

    log_event(f"cleanup_start raw_len={len(raw_text)} no_paste={args.no_paste}")
    start = time.perf_counter()
    try:
        data = cleanup_text(raw_text)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        log_event(f"http_error status={exc.code} detail={detail[:500]!r}")
        print(f"Cleanup server returned HTTP {exc.code}: {detail}", file=sys.stderr)
        return 1
    except error.URLError as exc:
        log_event(f"url_error error={exc!r}")
        print(f"Could not reach cleanup server: {exc}", file=sys.stderr)
        return 1

    elapsed_total = time.perf_counter() - start

    if not data.get("ok"):
        log_event(f"cleanup_failed response={data!r}")
        print(f"Cleanup failed: {data}", file=sys.stderr)
        return 1

    cleaned = str(data.get("cleaned", "")).strip()
    if not cleaned:
        log_event("empty_cleaned_text")
        return 0

    pyperclip.copy(cleaned)
    if not args.no_paste:
        time.sleep(args.paste_delay)
        pyautogui.hotkey("ctrl", "v")

    log_event(
        "cleanup_ok "
        f"raw_len={len(raw_text)} cleaned_len={len(cleaned)} "
        f"model_elapsed={_format_seconds(data.get('elapsed_seconds'))} "
        f"total_elapsed={elapsed_total:.3f}s pasted={not args.no_paste}"
    )
    print(
        "Cleaned clipboard. "
        f"model_elapsed={_format_seconds(data.get('elapsed_seconds'))} "
        f"total_elapsed={elapsed_total:.3f}s "
        f"model={data.get('loaded_model_id')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
