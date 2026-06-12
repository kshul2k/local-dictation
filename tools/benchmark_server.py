import json
import time
from urllib import error, request


SERVER_URL = "http://127.0.0.1:8765/cleanup"
CASES = [
    (
        "short",
        "okay this is a quick test can you add punctuation and make it readable",
    ),
    (
        "meaning",
        "okay this is a test of local dictation cleanup i want it to add punctuation and capitalization without changing what i mean",
    ),
    (
        "technical",
        "i want codex to work on the govfetch scoring profile catch up logic using fastapi postgres sqlalchemy alembic and the sam dot gov ingestion pipeline",
    ),
    (
        "medium",
        "okay i want to test this for dictating messages into chatgpt and codex the transcription is accurate enough but it usually does not add punctuation so i need a small local model to clean it up without changing what i mean",
    ),
]


def cleanup(text: str) -> tuple[int, dict[str, object], float]:
    payload = json.dumps({"text": text}).encode("utf-8")
    req = request.Request(
        SERVER_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.perf_counter()
    try:
        with request.urlopen(req, timeout=90) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body), time.perf_counter() - start
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        return exc.code, json.loads(body), time.perf_counter() - start


def main() -> int:
    failures = 0
    for name, text in CASES:
        status, data, elapsed = cleanup(text)
        ok = bool(data.get("ok"))
        if not ok:
            failures += 1
        print(f"=== {name} ===")
        print(f"status={status} ok={ok} total_elapsed={elapsed:.3f}s model_elapsed={data.get('elapsed_seconds')}")
        if ok:
            print(data.get("cleaned"))
        else:
            print(data.get("error"))
        print()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
