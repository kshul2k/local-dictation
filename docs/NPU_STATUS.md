# NPU Status

## Current Result

Foundry Local WinML can discover and register `QNNExecutionProvider`, and the Snapdragon NPU device is present:

```text
Snapdragon(R) X Elite - X1E78100 - Qualcomm(R) Hexagon(TM) NPU
DriverVersion: 30.0.140.1000
Status: OK
```

Microsoft's Foundry Local CLI reference lists `QNNExecutionProvider` for Snapdragon X Elite/Plus Hexagon NPU with minimum driver version `30.0.140.0`, so this machine meets the documented minimum.

## Failure

Every tested QNN/NPU model downloads and caches, but fails at model load with:

```text
QNN_COMMON_ERROR_MEM_ALLOC: Memory allocation related error.
```

Tested QNN model IDs:

```text
qwen2.5-0.5b-instruct-qnn-npu:1
qwen2.5-1.5b-instruct-qnn-npu:3
qwen2.5-coder-0.5b-instruct-qnn-npu:1
phi-3-mini-4k-instruct-qnn-npu:4
```

This is likely a QNN runtime, service, driver, or device-state issue rather than a single model issue.

## Manual CLI Diagnostic

The Foundry Local CLI is installed:

```text
Microsoft.FoundryLocal 0.8.119.102
```

Inside Codex's managed PowerShell, the WindowsApps alias fails to launch with:

```text
A specified logon session does not exist. It may already have been terminated
```

Run the commands below manually in a normal PowerShell window. Prefer "Run as administrator" if the non-admin terminal has service permission issues.

The first manual run confirmed the CLI starts and registers QNN, but it uses a different default cache:

```text
CLI cache: C:\Users\kjshu\.foundry\cache\models
SDK/project cache: C:\dev\local-dictation\.foundry-model-cache
```

Because of that mismatch, this command:

```powershell
foundry model load qwen2.5-0.5b-instruct-qnn-npu:1
```

failed with:

```text
Model was not found locally. Please run 'foundry model download <model name>'.
```

Pointing the CLI at the SDK/project cache caused `foundry cache list` to return HTTP 500, so the CLI and SDK cache paths should be treated as separate.

The CLI then downloaded `qwen2.5-0.5b-instruct-qnn-npu:1` into its own default cache successfully:

```text
CLI cache: C:\Users\kjshu\.foundry\cache\models
qwen2.5-0.5b-instruct-qnn-npu:1 cached successfully
```

The CLI load reached the real QNN path and failed:

```text
Failed to load from EpContext model.
qnn_backend_manager.cc:1138 onnxruntime::qnn::QnnBackendManager::LoadCachedQnnContextFromBuffer
Failed to create context from binary.
Error code: 14001
```

The CLI-downloaded and SDK-downloaded `context_ctx_qnn.bin` files are byte-identical by SHA256:

```text
335B9AD3F5D74ED00A426BBCE409C37D6401BC54F679D2C7D5DDC85C94BF89D1
```

So the current working diagnosis is a QNN runtime/NPU driver/device-state failure when loading the precompiled QNN context, not a missing model or corrupt cache.

## Foundry CLI 0.10 Result

The direct GitHub preview CLI was installed and the older winget app was removed. `foundry --version` now reports:

```text
0.10.0+174be11ea7aeacd8d0d67b0ba1daebec615284b1
```

The new CLI sees the machine and model correctly:

```text
OS: Microsoft Windows 10.0.26200
Architecture: Arm64
NPU: Snapdragon X Elite - X1E78100 - Qualcomm Hexagon NPU
RAM: about 15 GB available / 31.6 GB total
Service: Ready
Models cached: qwen2.5-0.5b, 442 MB, Device NPU
```

The QNN model load still fails below the CLI layer:

```text
IPC error 'op_handler_failed': Error loading model qwen2.5-0.5b-instruct-qnn-npu:1
Microsoft.ML.OnnxRuntimeGenAI.OnnxRuntimeGenAIException:
Failed to load from EpContext model. Failed to create context from binary.
Error: QNN_COMMON_ERROR_MEM_ALLOC: Memory allocation related error.
```

The new daemon log has the same failure in `model.load`, so CLI `0.10.0` fixed the command surface/catalog behavior but not this QNN context-load failure.

The CLI suggests one service reset:

```powershell
foundry server stop
foundry server start
foundry model load qwen2.5-0.5b-instruct-qnn-npu:1
```

If that still returns `QNN_COMMON_ERROR_MEM_ALLOC`, stop retrying model loads until the Qualcomm/ASUS NPU driver or Windows platform stack changes.

## ASUS Qualcomm Board Support Package Check

ASUS lists a critical `Qualcomm Board Support Package` version `V1.3677800.0` dated `2025/09/05`. The locally installed component versions match the important entries from that package:

```text
BIOS: S5507QAD.367
Audio Driver: 1.0.4166.1200
Audio DSP Driver: 2.0.4237.8400
Bluetooth Driver: 1.0.4237.8400
Camera Driver: 4815.110.0.1
Core/System drivers: 1.0.4160.6000
Graphic Driver: 31.0.96.0
NPU Driver: 30.0.140.1000
Sensor Driver: 1.0.4160.6000
Wireless LAN Driver: 1.0.4237.8400
```

That means the critical ASUS package does not appear to contain a newer NPU driver than the one already installed. Reinstalling it might repair a broken driver stack, but it is not an upgrade path for the NPU driver version.

## Foundry Catalog Size Check

The current Foundry Python SDK catalog exposes four text/chat NPU variants on this machine:

```text
442 MB  qwen2.5-0.5b-instruct-qnn-npu:1
442 MB  qwen2.5-coder-0.5b-instruct-qnn-npu:1
1086 MB qwen2.5-1.5b-instruct-qnn-npu:3
3623 MB phi-3-mini-4k-instruct-qnn-npu:4
```

So `qwen2.5-0.5b-instruct-qnn-npu:1` is already tied for the smallest text/chat NPU model available through Foundry on this machine. If testing the "model type/package" theory, the only rational smaller-model probe is the other 442 MB variant:

```powershell
.\tools\probe_smallest_npu_cli.ps1
```

If both 442 MB variants fail with the same QNN memory allocation error, model size is very unlikely to be the root cause.

## Runtime Memory Theory

The 442 MB package size is not the same as runtime memory. The cached Qwen 0.5B NPU config uses:

```text
context_length: 32768
search.max_length: 32768
hidden_size: 896
num_hidden_layers: 24
num_key_value_heads: 2
head_size: 64
```

That means runtime allocations include the precompiled QNN context, graph scratch buffers, activations, and KV/cache buffers. It is plausible for `QNN_COMMON_ERROR_MEM_ALLOC` to happen even when the package is small and normal system RAM is available, especially if QNN needs a constrained or contiguous NPU/driver allocation.

A bounded experiment can reduce the cached QNN model config to a shorter context length:

```powershell
.\tools\experiment_qnn_context_length.ps1 -ContextLength 4096
foundry server stop
foundry server start
foundry model load qwen2.5-0.5b-instruct-qnn-npu:1
.\tools\experiment_qnn_context_length.ps1 -Restore
```

This may not help if the QNN context binary was compiled for fixed memory requirements, but it directly tests whether Foundry/ORT GenAI honors the shorter config at model creation.

Note: Windows PowerShell `Set-Content -Encoding UTF8` writes a BOM that ORT GenAI rejects in `genai_config.json`. The experiment script must write UTF-8 without BOM.

Result: after restoring and patching the CLI cache to `ContextLength=4096` with UTF-8 no BOM, Foundry reached QNN model creation and still failed with:

```text
Failed to load from EpContext model.
Failed to create context from binary.
Error: QNN_COMMON_ERROR_MEM_ALLOC: Memory allocation related error.
```

So reducing `genai_config.json`/`config.json` context length does not resolve the load failure. The memory failure is likely tied to the precompiled QNN context binary or lower QNN runtime allocation behavior, not a tunable Foundry max context setting.

## Next Targeted Attempts

Do not keep rerunning `foundry model load qwen2.5-0.5b-instruct-qnn-npu:1` until one of these has changed:

1. Qualcomm/ASUS NPU driver package updated.
2. Windows Update or MyASUS installs a firmware/platform update.
3. Microsoft/Foundry support asks for a fresh reproduction with logs.

Microsoft's current Foundry troubleshooting guidance treats Qualcomm NPU `qnn_backend_manager` load failures as either outdated Qualcomm NPU driver or NPU resource conflicts, with reboot as the resource-conflict reset. Since reboot did not fix this machine, the next practical move is a driver/runtime update or a support report with logs.

Collect a support bundle without retrying the load:

```powershell
cd C:\dev\local-dictation
.\tools\collect_npu_diagnostics.ps1
```

After a driver or CLI update, collect the same bundle and do one explicit load retry:

```powershell
cd C:\dev\local-dictation
.\tools\collect_npu_diagnostics.ps1 -RetryQnnLoad
```

The generated folder under `diagnostics\npu_diagnostics\` includes Foundry status/cache/diagnostic output, NPU driver metadata, and recent Foundry logs.

Useful CLI sequence for the current Foundry CLI `0.10.0`:

```powershell
cd C:\dev\local-dictation
foundry server stop
foundry server start
foundry status
foundry cache ls
foundry model load qwen2.5-0.5b-instruct-qnn-npu:1
```

If `foundry model load` fails, keep the full error text and the newest folder under `diagnostics\npu_diagnostics\`.

If `foundry model load` succeeds manually, the next step is to compare the CLI service path against the Python SDK path.

## Current CPU Baseline

The best current CPU baseline is:

```text
qwen2.5-1.5b-instruct-generic-cpu:4
```

Benchmark through `tools\benchmark_server.py`:

```text
short:    ~0.88s model time, passed
meaning:  ~1.04s model time, passed
technical:~1.19s model time, passed
medium:   ~1.48s model time, passed
```

The 7B CPU model is downloaded and load-verified, but benchmarking it is intentionally deferred until the NPU issue is resolved.
