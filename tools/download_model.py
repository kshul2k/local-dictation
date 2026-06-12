from foundry_local_sdk import FoundryLocalManager
from foundry_local_sdk.configuration import LogLevel

import argparse
import os

import _bootstrap  # noqa: F401
from foundry_config import build_configuration, get_model_reference


DEFAULT_MODEL = os.environ.get("DICTATION_CLEANUP_MODEL", "qwen2.5-0.5b")


def format_percent(value: object) -> float:
    try:
        percent = float(value)
    except (TypeError, ValueError):
        return 0.0
    return percent * 100 if percent <= 1 else percent


def main() -> int:
    parser = argparse.ArgumentParser(description="Download and verify a Foundry Local model.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="model alias or full model id")
    parser.add_argument(
        "--skip-qnn-register",
        action="store_true",
        help="do not register QNNExecutionProvider before selecting the model",
    )
    parser.add_argument(
        "--skip-load",
        action="store_true",
        help="download/cache only, without loading the model",
    )
    args = parser.parse_args()

    config = build_configuration("local_dictation_cleanup_download", LogLevel.INFORMATION)
    FoundryLocalManager.initialize(config)
    manager = FoundryLocalManager.instance

    if not args.skip_qnn_register:
        print("Registering QNNExecutionProvider...")

        def on_ep_progress(ep_name: str, percent: float) -> None:
            print(f"\r  {ep_name:<35} {percent:5.1f}%", end="", flush=True)

        result = manager.download_and_register_eps(
            ["QNNExecutionProvider"],
            progress_callback=on_ep_progress,
        )
        print()
        print(f"EP registration result: success={result.success}, status={result.status}")
        print(f"Registered EPs: {getattr(result, 'registered_eps', None)}")
        print(f"Failed EPs: {getattr(result, 'failed_eps', None)}")

    model = get_model_reference(manager, args.model)
    print(f"Selected model id: {model.id}")
    print(f"Cached before download: {model.is_cached}")

    if not model.is_cached:
        print(f"Downloading {args.model}...")

        def on_model_progress(progress: object) -> None:
            print(f"\r  model download {format_percent(progress):5.1f}%", end="", flush=True)

        try:
            model.download(progress_callback=on_model_progress)
        except TypeError:
            try:
                model.download(on_model_progress)
            except TypeError:
                model.download()
        print()

    print(f"Cached after download: {model.is_cached}")
    if args.skip_load:
        print("Skipping load verification.")
        return 0

    print("Loading model once to verify runtime...")
    model.load()
    print(f"Loaded model id: {model.id}")
    model.unload()
    print("Model download and load verification complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
