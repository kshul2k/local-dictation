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
    "You clean raw voice dictation into a clear, compact prompt for an AI assistant.\n"
    "Rules:\n"
    "- Preserve the user's intended request, constraints, and technical terms.\n"
    "- Preserve each distinct task, preference, constraint, and reason that affects the request.\n"
    "- Remove filler, false starts, repeated wording, and thinking-out-loud phrases.\n"
    "- You may lightly reorganize the text so the request is clearer.\n"
    "- Do not collapse a multi-part request into a generic summary.\n"
    "- For long or multi-part dictation, use 2-4 compact sentences instead of one over-compressed sentence.\n"
    "- Keep examples of what is wrong and what should change when they clarify the task.\n"
    "- Shorten wording by removing wasted words, not by deleting requested behavior.\n"
    "- Write the result as a direct request or instruction, not as a question about what the user might want.\n"
    "- If the user considers options and then decides, keep the final decision and remove the earlier uncertainty.\n"
    "- Keep the user's original point of view; do not change 'my' into 'your' or 'I' into 'you'.\n"
    "- Do not add new facts, requirements, names, or conclusions.\n"
    "- Do not ask the user to confirm or clarify something they already decided.\n"
    "- If a phrase might be important, keep it.\n"
    "- Do not answer the request.\n"
    "- Do not explain the cleanup.\n"
    "- Do not use markdown.\n"
    "Return only the cleaned prompt."
)

RETRY_SYSTEM_PROMPT = (
    SYSTEM_PROMPT
    + "\nThe previous cleanup was rejected because it dropped too much content. "
    "Clean the same raw dictation again. Keep every distinct requested change, "
    "preference, and constraint. For long dictation, prefer a complete 2-4 sentence "
    "prompt over an over-compressed one-liner."
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

FALLBACK_FILLER_PATTERNS = (
    r"\bokay\b",
    r"\bum+\b",
    r"\buh+\b",
    r"\ber+\b",
    r"\bah+\b",
    r"\byou know\b",
    r"\bi mean\b",
    r"\bi guess\b",
    r"\bactually\b",
    r"\bbasically\b",
    r"\bkind of\b",
    r"\bsort of\b",
)

FALLBACK_PHRASE_REPLACEMENTS = (
    (r"\bbased on that last dictation\b,?\s*", ""),
    (
        r"\bi was trying to figure out if maybe we should keep this cleanup thing on and (?:like )?actually i think yes but\b",
        "keep cleanup on, but",
    ),
    (r"\bwhat i want is\s+", ""),
    (r"\bcleanup thing\b", "cleanup"),
    (r"\bbut can you make it better\b", "but make it better"),
    (r"\bcan you make it better\b", "make it better"),
    (r"\bi think i do actually want to\b", "I want to"),
    (r"\bi do actually want to\b", "I want to"),
    (r"\bi think i want to\b", "I want to"),
    (
        r"\bas i am talking,? i am (?:kind of )?figuring out what i want to say,?\s*(?:and\s*)?",
        "",
    ),
    (r"\bthe part that i wanted to say\b", "the intended request"),
    (r"\bdelete the figuring it out part\b", "remove the thinking-out-loud part"),
    (r"\bfiguring it out part\b", "thinking-out-loud part"),
    (r"\bdoes not do anything other than add punctuation\b", "only adds punctuation"),
    (r"\bdoes not delete any words\b", "preserves every word"),
    (
        r"\bmost of the dictation i am doing is meant to be prompts for ai\b",
        "most of my dictation is meant as AI prompts",
    ),
    (r"\bcleanest set of tokens for the ai\b", "cleanest useful prompt tokens for the AI"),
)

EXAMPLE_TECH_TERMS = (
    "FastAPI",
    "PostgreSQL",
    "SQLAlchemy",
    "Alembic",
    "SAM.gov",
)

CONTENT_STOPWORDS = {
    "about",
    "actually",
    "again",
    "because",
    "being",
    "could",
    "does",
    "doing",
    "every",
    "guess",
    "maybe",
    "really",
    "should",
    "some",
    "that",
    "thing",
    "things",
    "think",
    "trying",
    "want",
    "wanted",
    "where",
    "with",
    "would",
}

ALLOWED_MODEL_NEW_TOKENS = {
    "assistant",
    "cleaned",
    "clearer",
    "compact",
    "concise",
    "keep",
    "loud",
    "prompt",
    "prompts",
    "section",
    "sections",
    "thinking",
}

manager: FoundryLocalManager | None = None
model: Any = None
client: Any = None
loaded_model_id: str | None = None


class RejectedCleanupError(RuntimeError):
    pass


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
    client.settings.max_tokens = 500

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
        "i can't",
        "i cannot",
    )
    if any(phrase in lowered for phrase in blocked_phrases):
        return True
    return text.count("**") >= 2 or text.count("\n") > 8


def _looks_undercomplete(raw_text: str, cleaned: str) -> bool:
    raw_tokens = re.findall(r"[a-z0-9]+", raw_text.lower())
    cleaned_tokens = re.findall(r"[a-z0-9]+", cleaned.lower())
    if len(raw_tokens) >= 20 and len(cleaned_tokens) < 6:
        return True
    if len(raw_tokens) >= 40 and len(cleaned_tokens) < max(12, len(raw_tokens) // 4):
        return True
    if len(raw_text.strip()) >= 200 and len(cleaned.strip()) < 40:
        return True
    return False


def _content_tokens(text: str) -> set[str]:
    normalized = _normalize_terms(text).lower()
    return {
        token
        for token in re.findall(r"[a-z0-9]+", normalized)
        if len(token) >= 4 and token not in CONTENT_STOPWORDS
    }


def _introduces_example_terms(raw_text: str, cleaned: str) -> bool:
    raw_normalized = _normalize_terms(raw_text).lower()
    cleaned_normalized = _normalize_terms(cleaned).lower()
    return any(
        term.lower() in cleaned_normalized and term.lower() not in raw_normalized
        for term in EXAMPLE_TECH_TERMS
    )


def _introduces_unsupported_issue_language(raw_text: str, cleaned: str) -> bool:
    raw_lower = raw_text.lower()
    cleaned_lower = cleaned.lower()
    raw_mentions_return_issue = (
        "sometimes" in raw_lower
        or "intermittent" in raw_lower
        or "does not return" in raw_lower
        or "doesn't return" in raw_lower
    )
    cleaned_mentions_return_issue = (
        "intermittent" in cleaned_lower
        or "returning cleaned text" in cleaned_lower
        or "return the cleaned text" in cleaned_lower
    )
    return cleaned_mentions_return_issue and not raw_mentions_return_issue


def _has_low_content_overlap(raw_text: str, cleaned: str) -> bool:
    raw_tokens = _content_tokens(raw_text)
    if len(raw_tokens) < 6:
        return False
    cleaned_tokens = _content_tokens(cleaned)
    overlap_count = len(raw_tokens & cleaned_tokens)
    return overlap_count < max(2, len(raw_tokens) // 3)


def _introduces_too_much_new_content(raw_text: str, cleaned: str) -> bool:
    raw_tokens = _content_tokens(raw_text)
    if len(raw_tokens) < 6:
        return False
    cleaned_tokens = _content_tokens(cleaned)
    overlap_count = len(raw_tokens & cleaned_tokens)
    new_tokens = cleaned_tokens - raw_tokens - ALLOWED_MODEL_NEW_TOKENS
    return len(new_tokens) > max(5, int(overlap_count * 1.5))


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


def _capitalize_sentence_starts(text: str) -> str:
    return re.sub(
        r"(^|[.!?]\s+)([a-z])",
        lambda match: f"{match.group(1)}{match.group(2).upper()}",
        text,
    )


def _strip_markdown_artifacts(text: str) -> str:
    return text.replace("`", "").replace("**", "")


def _preserve_user_perspective(raw_text: str, cleaned: str) -> str:
    raw_lower = raw_text.lower()
    if re.search(r"\bmy\b", raw_lower) and not re.search(r"\byour\b", raw_lower):
        cleaned = re.sub(r"\byour\b", "my", cleaned, flags=re.IGNORECASE)
    return cleaned


def _ensure_terminal_punctuation(text: str) -> str:
    cleaned = text.rstrip()
    if cleaned and cleaned[-1] not in ".?!":
        cleaned = f"{cleaned}."
    return cleaned


def _fallback_cleanup(raw_text: str) -> str:
    cleaned = raw_text.strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    for pattern, replacement in FALLBACK_PHRASE_REPLACEMENTS:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    for pattern in FALLBACK_FILLER_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()
    cleaned = re.sub(r"^(?:so|and|but)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+,", ",", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,")
    cleaned = _normalize_terms(cleaned)
    cleaned = _capitalize_standalone_i(cleaned)
    cleaned = _capitalize_sentence_starts(cleaned)
    cleaned = _capitalize_first_alpha(cleaned)
    return _ensure_terminal_punctuation(cleaned)


def _prepare_model_cleanup(raw_text: str, model_text: str) -> str:
    cleaned = _strip_common_wrappers(model_text)
    if _looks_like_model_answer(cleaned):
        raise RejectedCleanupError("Model returned an explanation instead of cleaned dictation.")
    if _looks_undercomplete(raw_text, cleaned):
        raise RejectedCleanupError("Model output was too short to represent the dictation.")
    if _introduces_example_terms(raw_text, cleaned):
        raise RejectedCleanupError("Model introduced terms from an example.")
    if _introduces_unsupported_issue_language(raw_text, cleaned):
        raise RejectedCleanupError("Model introduced issue details from an example.")
    if _has_low_content_overlap(raw_text, cleaned):
        raise RejectedCleanupError("Model output did not preserve enough dictation content.")
    if _introduces_too_much_new_content(raw_text, cleaned):
        raise RejectedCleanupError("Model introduced too much unsupported content.")
    cleaned = _strip_markdown_artifacts(cleaned)
    cleaned = _preserve_user_perspective(raw_text, cleaned)
    cleaned = _normalize_terms(cleaned)
    cleaned = _capitalize_standalone_i(cleaned)
    cleaned = _capitalize_sentence_starts(cleaned)
    cleaned = _capitalize_first_alpha(cleaned)
    return _ensure_terminal_punctuation(cleaned)


def _run_model_cleanup(raw_text: str, system_prompt: str, require_complete_retry: bool = False) -> str:
    user_content = f"raw: {raw_text}\nclean:"
    raw_tokens = re.findall(r"[a-z0-9]+", raw_text.lower())
    if require_complete_retry and len(raw_tokens) >= 40:
        min_words = max(20, len(raw_tokens) // 4)
        user_content = (
            f"raw: {raw_text}\n"
            f"Requirement: Return a complete cleaned prompt of at least {min_words} words "
            "unless that would require adding unsupported content.\n"
            "clean:"
        )

    result = client.complete_chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
    )
    return _prepare_model_cleanup(raw_text, _extract_message_text(result))


def clean_text(raw_text: str) -> tuple[str, float, str]:
    if client is None:
        raise RuntimeError("Cleanup client is not initialized.")

    raw_text = raw_text.strip()
    if not raw_text:
        return "", 0.0, "empty"

    start = time.perf_counter()
    try:
        try:
            cleaned = _run_model_cleanup(raw_text, SYSTEM_PROMPT)
            cleanup_mode = "model_prompt_polish"
        except RejectedCleanupError as exc:
            print(f"Model cleanup rejected; retrying with stricter prompt: {exc}")
            cleaned = _run_model_cleanup(raw_text, RETRY_SYSTEM_PROMPT, require_complete_retry=True)
            cleanup_mode = "model_prompt_polish_retry"
    except Exception as exc:
        print(f"Model cleanup failed; using fallback cleanup: {exc}")
        cleaned = _fallback_cleanup(raw_text)
        cleanup_mode = "fallback_cleanup"
    elapsed = time.perf_counter() - start

    return cleaned, elapsed, cleanup_mode


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

            cleaned, elapsed, cleanup_mode = clean_text(raw_text)

            self._send_json(
                200,
                {
                    "ok": True,
                    "cleaned": cleaned,
                    "elapsed_seconds": elapsed,
                    "cleanup_mode": cleanup_mode,
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
