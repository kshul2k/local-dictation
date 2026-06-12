# Local Dictation Cleanup

This is a local second-stage cleanup utility for clipboard-only dictation.

Flow:

```text
dictation app -> clipboard -> Foundry Local WinML cleanup server -> cleaned text pasted into active textbox
```

## Current Local Status

This machine is a Snapdragon X system. The global `python` command still points at Python 3.14 through `C:\Users\kjshu\AppData\Local\Python\bin\python.exe`, but this project has its own ARM64 Python 3.12 virtual environment at:

```text
C:\dev\local-dictation\.venv
```

Verified local state:

- Python 3.12.10 ARM64 is installed at `C:\Users\kjshu\AppData\Local\Programs\Python\Python312-arm64\python.exe`.
- The project venv reports `platform.machine() == "ARM64"`.
- `foundry-local-sdk-winml==1.2.1` and `foundry-local-core-winml==1.2.1` are installed.
- Native Foundry WinML DLLs are installed and verified inside the venv.
- `QNNExecutionProvider` can be downloaded/registered successfully.
- In the same process after QNN registration, `qwen2.5-0.5b` resolves to `qwen2.5-0.5b-instruct-qnn-npu:1`.
- A fresh process may still show QNN as unregistered until registration is called again, so `src\cleanup_server.py` registers QNN during startup.
- Scripts use a local model cache at `C:\dev\local-dictation\.foundry-model-cache` by default.

You can re-check from PowerShell:

```powershell
cd C:\dev\local-dictation
.\.venv\Scripts\python.exe .\tools\check_environment.py
.\.venv\Scripts\python.exe .\tools\probe_foundry.py --register-qnn
```

## Setup

From this folder:

```powershell
cd C:\dev\local-dictation
```

If you need to recreate the venv, create it with a Windows ARM64 Python 3.11, 3.12, or 3.13 interpreter. If the `py` launcher works and has ARM64 Python registered:

```powershell
py -3.12 -m venv .venv
```

If needed, call the ARM64 interpreter directly instead, adjusting the path to wherever Python is installed:

```powershell
& "$env:LocalAppData\Programs\Python\Python312-arm64\python.exe" -m venv .venv
```

Then install dependencies:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python .\tools\check_environment.py
```

Do not continue if `check_environment.py` warns that Python is not ARM64.

## Run

Start the persistent cleanup server:

```powershell
.\.venv\Scripts\Activate.ps1
python .\tools\download_model.py
python .\src\cleanup_server.py
```

To force the CPU variant for fallback testing:

```powershell
.\start_cpu_server.ps1
```

To run a larger CPU model:

```powershell
.\start_cpu_server.ps1 -Model "qwen2.5-1.5b-instruct-generic-cpu:4"
.\.venv\Scripts\python.exe .\tools\benchmark_server.py
```

Equivalent manual environment:

```powershell
$env:DICTATION_CLEANUP_MODEL = "qwen2.5-0.5b-instruct-generic-cpu:4"
$env:DICTATION_CLEANUP_REGISTER_EPS = "skip"
python .\src\cleanup_server.py
```

To retry the NPU path after a reboot or driver update:

```powershell
.\start_npu_server.ps1
```

To collect Foundry/NPU diagnostics without retrying the failing model load:

```powershell
.\tools\collect_npu_diagnostics.ps1
```

To list the current Foundry model variants from the Python SDK catalog:

```powershell
.\.venv\Scripts\python.exe .\tools\list_foundry_variants.py
```

To run one bounded CLI probe of the two smallest text/chat NPU variants:

```powershell
.\tools\probe_smallest_npu_cli.ps1
```

To experimentally reduce the cached QNN model context length and test whether the QNN memory error is context-size related:

```powershell
.\tools\experiment_qnn_context_length.ps1 -ContextLength 4096
foundry server stop
foundry server start
foundry model load qwen2.5-0.5b-instruct-qnn-npu:1
.\tools\experiment_qnn_context_length.ps1 -Restore
```

To stop whichever cleanup server was started from this folder:

```powershell
.\stop_cleanup_server.ps1
```

## Current Test Results

- NPU model `qwen2.5-0.5b-instruct-qnn-npu:1` downloaded into `.foundry-model-cache`.
- QNN/NPU load currently fails with `QNN_COMMON_ERROR_MEM_ALLOC`.
- CPU fallback model `qwen2.5-0.5b-instruct-generic-cpu:4` downloaded, loads successfully, and is running through `start_cpu_server.ps1`.
- Simple cleanup test is around 0.35-0.50 seconds on CPU fallback.
- The 0.5B model is not consistently safe for longer or technical text; the server rejects outputs that drop content tokens instead of pasting unsafe rewrites.

See `docs\NPU_STATUS.md` for the current NPU failure details and manual Foundry CLI diagnostic commands.

The first run may download execution providers and the `qwen2.5-0.5b` model. Keep Task Manager open at Performance -> NPU while testing. Foundry can fall back to CPU, so do not treat a successful response as proof of NPU acceleration.

In a second PowerShell window:

```powershell
cd C:\dev\local-dictation
.\.venv\Scripts\Activate.ps1
python .\tools\smoke_test_cleanup.py
```

If that works, copy some raw dictation text to the clipboard and test:

```powershell
python .\src\clean_clipboard_and_paste.py --no-paste
```

Remove `--no-paste` once you are ready to paste into the active textbox.

## Hotkey

Install AutoHotkey v2, then run:

```text
hotkeys\dictation_cleanup_hotkey.ahk
```

Hotkey:

```text
Ctrl+Alt+V
```

If the cleanup key is the same key used by OpenWhispr/WhisperFlow, use this pass-through version instead:

```text
hotkeys\dictation_cleanup_passthrough_hotkey.ahk
```

It waits for the dictation app to update the clipboard before calling the cleanup server. Client attempts are logged to:

```text
logs\cleanup_client.log
```

The preferred OpenWhispr integration watches OpenWhispr's local transcription database instead of the clipboard. Keep OpenWhispr auto-paste enabled. The watcher only reacts to new completed rows in OpenWhispr's `transcriptions` table, then uses Ctrl+Z to remove OpenWhispr's raw auto-paste and replaces it with cleaned text. Random clipboard changes do not trigger cleanup:

```powershell
powershell -ExecutionPolicy Bypass -File .\start_openwhispr_db_watcher.ps1
```

Stop it with:

```powershell
powershell -ExecutionPolicy Bypass -File .\stop_openwhispr_db_watcher.ps1
```

Watcher attempts are logged to:

```text
logs\openwhispr_db_watcher.log
```

## Windows Startup

Install the per-user Windows startup task:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_startup_task.ps1
```

The task runs at logon, starts the OpenWhispr DB watcher, and starts the CPU cleanup server if port `8765` is not already listening. Startup logs are written to:

```text
logs\local_dictation_startup.log
logs\cleanup_server.startup.log
```

Remove it with:

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall_startup_task.ps1
```

If Task Scheduler access is denied, use the per-user Startup folder shortcut instead:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_startup_shortcut.ps1
```

Remove the shortcut with:

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall_startup_shortcut.ps1
```

If you prefer clipboard-based behavior, run the clipboard watcher instead. It lets OpenWhispr keep its own hotkey and cleans/pastes after OpenWhispr writes final text to the clipboard:

```powershell
powershell -ExecutionPolicy Bypass -File .\start_clipboard_watcher.ps1
```

Stop it with:

```powershell
powershell -ExecutionPolicy Bypass -File .\stop_clipboard_watcher.ps1
```

Watcher attempts are logged to:

```text
logs\clipboard_watcher.log
```

Keep this as a separate second-stage hotkey until speed and NPU behavior are proven.
