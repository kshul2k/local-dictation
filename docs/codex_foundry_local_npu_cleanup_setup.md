# Codex Instructions: Local Dictation Cleanup with Foundry Local / WinML on Snapdragon X

## Goal

Set up a local dictation cleanup pipeline on a Windows Snapdragon X laptop.

Current state:

- WhisperKey/OpenWhispr-style dictation is already working.
- The dictation app is set to **clipboard-only** output.
- Transcription is currently using the **base** Whisper model.
- Built-in local LLM cleanup was too slow and unreliable:
  - Qwen cleanup took too long.
  - Llama 3.2 1B / “MetaLlama” produced unusable output.
- The desired architecture is:

```text
Dictation app transcription-only → clipboard → Foundry Local WinML cleanup server → cleaned text pasted into active textbox
```

The main purpose is to test whether Microsoft Foundry Local + WinML can use the Snapdragon X NPU or other hardware acceleration for the cleanup model.

This is an experiment. Do not assume NPU acceleration is guaranteed. Build the setup so the user can verify NPU usage in Task Manager.

---

## Operating Rules for Codex

1. Default to **instructing the user manually** rather than running commands automatically.
2. You may run commands yourself only if the user explicitly asks or approves.
3. Use **PowerShell on Windows**, not WSL.
4. Do not modify any existing GovFetch / production project repo.
5. Create this as a standalone local utility under:

```powershell
C:\dev\local-dictation-cleanup
```

6. Keep the implementation simple and inspectable.
7. Prefer a persistent cleanup server so the model is loaded once and hotkey calls are fast.
8. If a command fails, stop and explain the failure before trying broad changes.
9. Do not install large models unless the user approves.
10. Use `qwen2.5-0.5b` first because dictation cleanup only needs punctuation, capitalization, sentence boundaries, and light filler removal.

---

## Relevant Official References

Use these only for verification if needed:

- Foundry Local Python SDK: https://github.com/microsoft/Foundry-Local/blob/main/sdk/python/README.md
- Foundry Local CLI reference: https://learn.microsoft.com/en-us/azure/foundry-local/reference/reference-cli
- Foundry Local architecture: https://learn.microsoft.com/en-us/azure/foundry-local/concepts/foundry-local-architecture

Important details from current docs:

- Python WinML package: `foundry-local-sdk-winml`
- Python import path: `from foundry_local_sdk import Configuration, FoundryLocalManager`
- Windows WinML package is the intended Windows hardware-acceleration path.
- Foundry Local uses model aliases such as `qwen2.5-0.5b`.
- Aliases should select the best matching model variant for available hardware when possible.
- Foundry Local can discover/register execution providers.
- Foundry Local may still fall back to CPU.

---

## Phase 0: Confirm Manual Preconditions

Ask the user to confirm these before continuing:

- Windows on Snapdragon X laptop.
- Python 3.11 or 3.12 is installed for Windows ARM64, not only inside WSL.
- Dictation app outputs transcription to clipboard only.
- Built-in cleanup is disabled.
- User can open Task Manager → Performance → NPU to watch usage.
- User is okay with installing Python packages into a local virtual environment.

Useful manual checks:

```powershell
python --version
py --version
where python
```

If Python is not found, instruct the user to install Python 3.11 or 3.12 from python.org or the Microsoft Store, then restart PowerShell.

---

## Phase 1: Create Project Folder and Virtual Environment

Have the user run these manually in PowerShell:

```powershell
mkdir C:\dev\local-dictation-cleanup
cd C:\dev\local-dictation-cleanup
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

If `py -3.11` fails, try:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

If PowerShell blocks activation, instruct the user to run:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Then retry:

```powershell
.\.venv\Scripts\Activate.ps1
```

---

## Phase 2: Add `requirements.txt`

Create this file:

```text
C:\dev\local-dictation-cleanup\requirements.txt
```

Contents:

```text
foundry-local-sdk-winml
pyperclip
pyautogui
requests
```

Then have the user install:

```powershell
pip install -r requirements.txt
```

If `foundry-local-sdk-winml` fails to install, capture the full error and stop. Do not switch to the standard `foundry-local-sdk` unless the user approves, because the goal is Windows/WinML hardware acceleration.

---

## Phase 3: Create Persistent Cleanup Server

Create this file:

```text
C:\dev\local-dictation-cleanup\cleanup_server.py
```

Contents:

```python
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from foundry_local_sdk import Configuration, FoundryLocalManager
from foundry_local_sdk.configuration import LogLevel

HOST = "127.0.0.1"
PORT = 8765
APP_NAME = "local_dictation_cleanup"
MODEL_ALIAS = "qwen2.5-0.5b"

SYSTEM_PROMPT = (
    "You clean up raw voice dictation. "
    "Add punctuation, capitalization, and sentence breaks. "
    "Remove only obvious filler words. "
    "Preserve the user's meaning and technical terms. "
    "Do not answer the text. "
    "Do not add new information. "
    "Return only the cleaned text."
)

manager: FoundryLocalManager | None = None
model: Any = None
client: Any = None
loaded_model_id: str | None = None


def initialize_foundry() -> None:
    global manager, model, client, loaded_model_id

    print("Initializing Foundry Local / WinML...")
    config = Configuration(
        app_name=APP_NAME,
        log_level=LogLevel.INFORMATION,
    )
    FoundryLocalManager.initialize(config)
    manager = FoundryLocalManager.instance

    print("Discovering execution providers...")
    try:
        eps = manager.discover_eps()
        for ep in eps:
            print(f"  EP: {ep.name} | registered={ep.is_registered}")
    except Exception as exc:
        print(f"  Could not list EPs before registration: {exc}")

    print("Downloading/registering execution providers. First run may take time...")

    def on_ep_progress(ep_name: str, percent: float) -> None:
        print(f"\r  {ep_name:<35} {percent:5.1f}%", end="", flush=True)

    try:
        result = manager.download_and_register_eps(progress_callback=on_ep_progress)
        print()
        print(f"EP registration result: success={result.success}, status={result.status}")
        print(f"Registered EPs: {getattr(result, 'registered_eps', None)}")
        print(f"Failed EPs: {getattr(result, 'failed_eps', None)}")
    except Exception as exc:
        print()
        print(f"  EP registration failed or was unavailable: {exc}")
        print("  Continuing anyway; Foundry Local may fall back to CPU.")

    print(f"Getting model alias: {MODEL_ALIAS}")
    model = manager.catalog.get_model(MODEL_ALIAS)

    if not model.is_cached:
        print(f"Downloading model: {MODEL_ALIAS}")
        model.download(lambda progress: print(f"\r  model download {progress:5.1f}%", end="", flush=True))
        print()

    print("Loading model...")
    model.load()
    loaded_model_id = model.id
    print(f"Loaded model id: {loaded_model_id}")

    client = model.get_chat_client()
    client.settings.temperature = 0.0
    client.settings.max_tokens = 400

    print("Cleanup model ready.")


def clean_text(raw_text: str) -> tuple[str, float]:
    if client is None:
        raise RuntimeError("Cleanup client is not initialized.")

    raw_text = raw_text.strip()
    if not raw_text:
        return "", 0.0

    start = time.perf_counter()
    result = client.complete_chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": raw_text},
        ]
    )
    elapsed = time.perf_counter() - start

    cleaned = result.choices[0].message.content.strip()

    # Avoid common wrapper artifacts.
    if cleaned.startswith('"') and cleaned.endswith('"'):
        cleaned = cleaned[1:-1].strip()

    return cleaned, elapsed


class CleanupHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(
                200,
                {
                    "ok": True,
                    "model_alias": MODEL_ALIAS,
                    "loaded_model_id": loaded_model_id,
                },
            )
            return

        self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/cleanup":
            self._send_json(404, {"ok": False, "error": "not found"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length).decode("utf-8")
            payload = json.loads(raw_body)
            raw_text = str(payload.get("text", ""))

            cleaned, elapsed = clean_text(raw_text)

            self._send_json(
                200,
                {
                    "ok": True,
                    "cleaned": cleaned,
                    "elapsed_seconds": elapsed,
                    "model_alias": MODEL_ALIAS,
                    "loaded_model_id": loaded_model_id,
                },
            )
        except Exception as exc:
            self._send_json(500, {"ok": False, "error": str(exc)})

    def log_message(self, format: str, *args: Any) -> None:
        # Keep the console quiet except for explicit logs.
        return


def main() -> None:
    initialize_foundry()
    server = ThreadingHTTPServer((HOST, PORT), CleanupHandler)
    print(f"Listening on http://{HOST}:{PORT}")
    print("Keep this PowerShell window open while testing.")
    print("Use Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping cleanup server...")
    finally:
        server.server_close()
        try:
            if model is not None:
                model.unload()
        except Exception:
            pass


if __name__ == "__main__":
    main()
```

---

## Phase 4: Create Clipboard Cleanup Client

Create this file:

```text
C:\dev\local-dictation-cleanup\clean_clipboard_and_paste.py
```

Contents:

```python
import json
import sys
import time
from urllib import request, error

import pyautogui
import pyperclip

SERVER_URL = "http://127.0.0.1:8765/cleanup"
TIMEOUT_SECONDS = 30


def main() -> int:
    raw_text = pyperclip.paste().strip()
    if not raw_text:
        return 0

    payload = json.dumps({"text": raw_text}).encode("utf-8")
    req = request.Request(
        SERVER_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    start = time.perf_counter()
    try:
        with request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
    except error.URLError as exc:
        print(f"Could not reach cleanup server: {exc}", file=sys.stderr)
        return 1

    elapsed_total = time.perf_counter() - start
    data = json.loads(body)

    if not data.get("ok"):
        print(f"Cleanup failed: {data}", file=sys.stderr)
        return 1

    cleaned = str(data.get("cleaned", "")).strip()
    model_elapsed = data.get("elapsed_seconds")
    model_id = data.get("loaded_model_id")

    if not cleaned:
        return 0

    pyperclip.copy(cleaned)
    pyautogui.hotkey("ctrl", "v")

    print(f"Cleaned and pasted. model_elapsed={model_elapsed:.3f}s total_elapsed={elapsed_total:.3f}s model={model_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Note: This imports `requests` in requirements only in case Codex decides to switch to requests later. The current client uses Python stdlib `urllib` to keep the script simple.

---

## Phase 5: Create Smoke Test Script

Create this file:

```text
C:\dev\local-dictation-cleanup\smoke_test_cleanup.py
```

Contents:

```python
import json
from urllib import request

payload = json.dumps(
    {
        "text": "okay this is a test of local dictation cleanup i want it to add punctuation and capitalization without changing what i mean"
    }
).encode("utf-8")

req = request.Request(
    "http://127.0.0.1:8765/cleanup",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)

with request.urlopen(req, timeout=30) as response:
    print(response.read().decode("utf-8"))
```

---

## Phase 6: Run the Server and Test

Have the user open PowerShell and run:

```powershell
cd C:\dev\local-dictation-cleanup
.\.venv\Scripts\Activate.ps1
python .\src\cleanup_server.py
```

Expected behavior:

- First run may download execution providers.
- First run may download `qwen2.5-0.5b`.
- The script should print discovered/registered EPs.
- It should print the loaded model id.
- It should end with:

```text
Listening on http://127.0.0.1:8765
```

Then in a second PowerShell window:

```powershell
cd C:\dev\local-dictation-cleanup
.\.venv\Scripts\Activate.ps1
python .\tools\smoke_test_cleanup.py
```

Acceptance criteria:

- Output returns JSON with `ok: true`.
- `cleaned` text has punctuation/capitalization.
- `elapsed_seconds` is visible.
- During the request, the user can watch Task Manager → Performance → NPU.

Important: If NPU usage stays flat, this may still be using CPU/GPU fallback. Record this clearly. Do not claim success unless Task Manager or Foundry logs indicate acceleration.

---

## Phase 7: Create AutoHotkey Hotkey

If the smoke test works, install AutoHotkey v2 if needed.

Create:

```text
C:\dev\local-dictation\hotkeys\dictation_cleanup_hotkey.ahk
```

Contents:

```ahk
^!v::{
    RunWait('"' A_UserProfile '\dev\local-dictation-cleanup\.venv\Scripts\python.exe" "' A_UserProfile '\dev\local-dictation-cleanup\clean_clipboard_and_paste.py"', , "Hide")
}
```

This creates:

```text
Ctrl + Alt + V = clean clipboard text and paste cleaned result
```

Manual workflow:

1. Click into any textbox.
2. Use the dictation app hotkey.
3. Dictation app places raw transcript on clipboard.
4. Press `Ctrl + Alt + V`.
5. Cleanup server cleans text and pastes it.

Do not combine this into the dictation hotkey yet. Keep the two-stage workflow until performance is proven.

---

## Phase 8: Performance Testing Matrix

Have the user test these snippets and record elapsed time from the client printout:

### Short text

```text
okay this is a quick test can you add punctuation and make it readable
```

Target: under 2 seconds.

### Medium text

```text
okay i want to test this for dictating messages into chatgpt and codex the transcription is accurate enough but it usually does not add punctuation so i need a small local model to clean it up without changing what i mean
```

Target: under 5 seconds.

### Technical text

```text
i want codex to work on the govfetch scoring profile catch up logic using fastapi postgres sqlalchemy alembic and the sam dot gov ingestion pipeline
```

Target: preserves terms like GovFetch, FastAPI, PostgreSQL, SQLAlchemy, Alembic, and SAM.gov as well as possible.

If the model mangles technical terms, update `SYSTEM_PROMPT` in `cleanup_server.py` to include:

```python
"Preserve these terms when they appear: GovFetch, SAM.gov, DIBBS, CAGE, NAICS, RFQ, FastAPI, PostgreSQL, SQLAlchemy, Alembic, React, TypeScript, Vite, Codex, VS Code, Cloudflare. "
```

Restart the server after editing the prompt.

---

## Phase 9: Troubleshooting

### Problem: Install fails for `foundry-local-sdk-winml`

Action:

- Capture full pip error.
- Confirm Python is Windows-native and not WSL.
- Confirm Python architecture if possible:

```powershell
python -c "import platform; print(platform.platform()); print(platform.machine())"
```

Do not switch packages without user approval.

### Problem: Server starts but model download fails

Action:

- Check internet connection.
- Retry once.
- If still failing, ask user before trying a different model alias.

### Problem: Cleanup works but NPU does not move

Action:

- Run or instruct user to run:

```powershell
foundry model list --filter device=NPU
foundry model list --filter provider=QNNExecutionProvider
foundry model list --filter alias=qwen2.5-0.5b
```

If the `foundry` CLI is not installed, do not force CLI installation yet. The Python SDK can still work.

If only CPU variants are available, explain that Foundry Local is falling back and the current model may not have an NPU variant on this device.

### Problem: Hotkey works but nothing pastes

Action:

- Test the client directly:

```powershell
python .\src\clean_clipboard_and_paste.py
```

- Confirm clipboard has text before running.
- Try pasting into Notepad first.
- If Notepad works but VS Code/Codex does not, the issue is app focus or paste handling.

### Problem: Cleanup is still too slow

Action:

- Confirm server is already running before pressing hotkey.
- Confirm the model is not reloading for every request.
- Keep `qwen2.5-0.5b`; do not increase model size.
- Reduce `client.settings.max_tokens` from `400` to `200`.
- Shorten the system prompt.
- If still too slow, recommend no cleanup for short dictation and cleanup only for longer prompts.

### Problem: Cleanup changes meaning or answers the prompt

Action:

Tighten `SYSTEM_PROMPT`:

```python
SYSTEM_PROMPT = (
    "Add punctuation and capitalization to this dictation. "
    "Do not answer it. Do not rewrite it creatively. "
    "Do not add facts. Preserve the original meaning. "
    "Return only the cleaned text."
)
```

Restart the server.

---

## Final Acceptance Criteria

The setup is successful if all are true:

- Dictation app still handles speech-to-text and outputs to clipboard.
- Built-in cleanup is disabled.
- `cleanup_server.py` stays running with the model loaded.
- `smoke_test_cleanup.py` returns cleaned text.
- `Ctrl + Alt + V` cleans clipboard text and pastes into Notepad.
- Cleanup is meaningfully faster than the prior 30–60 second built-in local cleanup.
- The user has checked Task Manager NPU during cleanup and knows whether NPU is actually being used.

Minimum acceptable performance:

- Short cleanup: under 3 seconds.
- Medium cleanup: under 6 seconds.

If performance is worse than that, do not keep this enabled as a daily-driver hotkey.

---

## Notes for the User

This does not replace the dictation app. It only adds a second-stage local cleanup path.

The intended daily-driver flow is:

```text
Dictate → raw transcript copied to clipboard → Ctrl+Alt+V → cleaned text pasted
```

Later, after performance is proven, this can be turned into a cleaner tray utility or combined hotkey.
