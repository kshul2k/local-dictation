import argparse
import json
from urllib import error, request


SERVER_URL = "http://127.0.0.1:8765/cleanup"
DEFAULT_TEXT = (
    "okay this is a quick test can you add punctuation and make it readable"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a cleanup request to the local server.")
    parser.add_argument("text", nargs="*", help="text to clean")
    args = parser.parse_args()

    raw_text = " ".join(args.text).strip() or DEFAULT_TEXT
    payload = json.dumps({"text": raw_text}).encode("utf-8")

    req = request.Request(
        SERVER_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=30) as response:
            print(response.read().decode("utf-8"))
        return 0
    except error.HTTPError as exc:
        print(exc.read().decode("utf-8"))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
