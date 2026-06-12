import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from foundry_local_sdk import FoundryLocalManager
from foundry_local_sdk.configuration import LogLevel

from foundry_config import build_configuration, get_model_reference


HOST = os.environ.get("DICTATION_CLEANUP_HOST", "127.0.0.1")
PORT = int(os.environ.get("DICTATION_CLEANUP_PORT", "8765"))
APP_NAME = "local_dictation_cleanup"
MODEL_ALIAS = os.environ.get("DICTATION_CLEANUP_MODEL", "qwen2.5-0.5b")
REGISTER_EPS = os.environ.get("DICTATION_CLEANUP_REGISTER_EPS")
if REGISTER_EPS is None:
    REGISTER_EPS = "QNNExecutionProvider"
MAX_BODY_BYTES = 20_000

SYSTEM_PROMPT = (
    "You format raw dictation. Rules:\n"
    "- Keep the same words.\n"
    "- Fix capitalization, punctuation, spacing, and sentence breaks only.\n"
    "- Do not answer.\n"
    "- Do not explain.\n"
    "- Do not use markdown.\n"
    "Examples:\n"
    "raw: okay this is a test can you make it readable\n"
    "clean: Okay, this is a test. Can you make it readable?\n"
    "raw: i want codex to use fastapi postgres sqlalchemy alembic and sam dot gov\n"
    "clean: I want Codex to use FastAPI, PostgreSQL, SQLAlchemy, Alembic, and SAM.gov.\n"
    "Return only the clean text."
)

TECH_TERM_REPLACEMENTS = (
    (r"\bgovfetch\b", "GovFetch"),
    (r"\bfastapi\b", "FastAPI"),
    (r"\bpostgresql\b", "PostgreSQL"),
    (r"\bpostgres\b", "PostgreSQL"),
    (r"\bsqlalchemy\b", "SQLAlchemy"),
    (r"\balembic\b", "Alembic"),
    (r"\btypescript\b", "TypeScript"),
    (r"\bcloudflare\b", "Cloudflare"),
    (r"\bcodex\b", "Codex"),
    (r"\bchatgpt\b", "ChatGPT"),
    (r"\bvs code\b", "VS Code"),
    (r"\bsam\s*dot\s*gov\b", "SAM.gov"),
    (r"\bsam\s*\.\s*gov\b", "SAM.gov"),
    (r"\bdibbs\b", "DIBBS"),
    (r"\bcage\b", "CAGE"),
    (r"\bnaics\b", "NAICS"),
    (r"\brfq\b", "RFQ"),
)

IGNORED_PRESERVATION_TOKENS = {
    "okay",
    "actually",
    "basically",
    "literally",
}

manager: FoundryLocalManager | None = None
model: Any = None
client: Any = None
loaded_model_id: str | None = None


def _print_ep_info(prefix: str, eps: Any) -> None:
    print(prefix)
    for ep in eps:
        name = getattr(ep, "name", "<unknown>")
        registered = getattr(ep, "is_registered", "<unknown>")
        print(f"  EP: {name} | registered={registered}")


def _format_percent(value: Any) -> float:
    try:
        percent = float(value)
    except (TypeError, ValueError):
        return 0.0
    return percent * 100 if percent <= 1 else percent


def _download_model_if_needed(foundry_model: Any) -> None:
    if getattr(foundry_model, "is_cached", False):
        print(f"Model is already cached: {MODEL_ALIAS}")
        return

    print(f"Downloading model: {MODEL_ALIAS}")

    def on_model_progress(progress: Any) -> None:
        print(f"\r  model download {_format_percent(progress):5.1f}%", end="", flush=True)

    try:
        foundry_model.download(progress_callback=on_model_progress)
    except TypeError:
        try:
            foundry_model.download(on_model_progress)
        except TypeError:
            foundry_model.download()
    print()


def initialize_foundry() -> None:
    global manager, model, client, loaded_model_id

    print("Initializing Foundry Local / WinML...")
    config = build_configuration(APP_NAME, LogLevel.INFORMATION)
    FoundryLocalManager.initialize(config)
    manager = FoundryLocalManager.instance

    print("Discovering execution providers...")
    try:
        _print_ep_info("Execution providers before registration:", manager.discover_eps())
    except Exception as exc:
        print(f"  Could not list EPs before registration: {exc}")

    register_eps_value = REGISTER_EPS.strip()
    if register_eps_value.lower() in {"0", "false", "none", "skip", "disabled"}:
        ep_names = []
    else:
        ep_names = [name.strip() for name in register_eps_value.split(",") if name.strip()]
    if ep_names:
        print(f"Downloading/registering execution providers: {', '.join(ep_names)}")
        print("First run may take time...")

        def on_ep_progress(ep_name: str, percent: float) -> None:
            print(f"\r  {ep_name:<35} {percent:5.1f}%", end="", flush=True)

        try:
            result = manager.download_and_register_eps(ep_names, progress_callback=on_ep_progress)
            print()
            print(f"EP registration result: success={result.success}, status={result.status}")
            print(f"Registered EPs: {getattr(result, 'registered_eps', None)}")
            print(f"Failed EPs: {getattr(result, 'failed_eps', None)}")
            try:
                _print_ep_info("Execution providers after registration:", manager.discover_eps())
            except Exception as exc:
                print(f"  Could not list EPs after registration: {exc}")
        except Exception as exc:
            print()
            print(f"  EP registration failed or was unavailable: {exc}")
            print("  Continuing; Foundry Local may fall back to CPU.")
    else:
        print("Skipping execution provider registration.")

    print(f"Getting model: {MODEL_ALIAS}")
    model = get_model_reference(manager, MODEL_ALIAS)
    print(f"Selected model id before load: {getattr(model, 'id', None)}")

    _download_model_if_needed(model)

    print("Loading model...")
    model.load()
    loaded_model_id = getattr(model, "id", None)
    print(f"Loaded model id: {loaded_model_id}")

    client = model.get_chat_client()
    client.settings.temperature = 0.0
    client.settings.max_tokens = 300

    print("Cleanup model ready.")


def _extract_message_text(result: Any) -> str:
    choices = getattr(result, "choices", None)
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", "")
    return str(content).strip()


def _strip_common_wrappers(text: str) -> str:
    cleaned = text.strip()
    for prefix in ("Cleaned text:", "Cleaned:", "Output:"):
        if cleaned.lower().startswith(prefix.lower()):
            cleaned = cleaned[len(prefix) :].strip()

    lines = cleaned.splitlines()
    while lines:
        first_line = lines[0].strip().lower()
        is_wrapper = (
            first_line.startswith("sure")
            or "here's your text" in first_line
            or "here is your text" in first_line
            or "with added punctuation" in first_line
            or "with punctuation" in first_line
        )
        if not is_wrapper:
            break
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines = lines[1:]
        cleaned = "\n".join(lines).strip()

    if len(cleaned) >= 2 and cleaned[0] == '"' and cleaned[-1] == '"':
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _looks_like_model_answer(text: str) -> bool:
    lowered = text.lower()
    blocked_phrases = (
        "here's how",
        "here is how",
        "it would look",
        "i will do my best",
        "this ensures",
        "as an ai",
    )
    if any(phrase in lowered for phrase in blocked_phrases):
        return True
    return text.count("**") >= 2 or text.count("\n") > 8


def _normalize_terms(text: str) -> str:
    cleaned = text
    for pattern, replacement in TECH_TERM_REPLACEMENTS:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    return cleaned


def _capitalize_first_alpha(text: str) -> str:
    for index, char in enumerate(text):
        if char.isalpha():
            return f"{text[:index]}{char.upper()}{text[index + 1:]}"
    return text


def _capitalize_standalone_i(text: str) -> str:
    return re.sub(r"\bi\b", "I", text)


def _expand_common_contractions(text: str) -> str:
    replacements = {
        r"\bdoesn['’]t\b": "does not",
        r"\bdon['’]t\b": "do not",
        r"\bcan['’]t\b": "can not",
        r"\bwon['’]t\b": "will not",
        r"\bisn['’]t\b": "is not",
        r"\baren['’]t\b": "are not",
        r"\bwasn['’]t\b": "was not",
        r"\bweren['’]t\b": "were not",
    }
    expanded = text
    for pattern, replacement in replacements.items():
        expanded = re.sub(pattern, replacement, expanded, flags=re.IGNORECASE)
    return expanded


def _preservation_tokens(text: str) -> list[str]:
    normalized = _expand_common_contractions(_normalize_terms(text)).lower()
    tokens = re.findall(r"[a-z0-9]+", normalized)
    return [
        token
        for token in tokens
        if len(token) >= 4 and token not in IGNORED_PRESERVATION_TOKENS
    ]


def _validate_content_preserved(raw_text: str, cleaned: str) -> None:
    expected = set(_preservation_tokens(raw_text))
    actual = set(_preservation_tokens(cleaned))
    missing = sorted(expected - actual)
    if missing:
        sample = ", ".join(missing[:8])
        raise RuntimeError(f"Model output dropped content tokens: {sample}")


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
            {"role": "user", "content": f"raw: {raw_text}\nclean:"},
        ]
    )
    elapsed = time.perf_counter() - start

    cleaned = _strip_common_wrappers(_extract_message_text(result))
    if _looks_like_model_answer(cleaned):
        raise RuntimeError("Model returned an explanation instead of cleaned dictation.")
    cleaned = _normalize_terms(cleaned)
    cleaned = _capitalize_standalone_i(cleaned)
    cleaned = _capitalize_first_alpha(cleaned)
    _validate_content_preserved(raw_text, cleaned)
    return cleaned, elapsed


class CleanupHandler(BaseHTTPRequestHandler):
    server_version = "LocalDictationCleanup/0.1"

    def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
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
        path = urlparse(self.path).path
        if path != "/cleanup":
            self._send_json(404, {"ok": False, "error": "not found"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length > MAX_BODY_BYTES:
                self._send_json(413, {"ok": False, "error": "request body too large"})
                return

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
