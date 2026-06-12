import argparse
import traceback

from foundry_local_sdk import FoundryLocalManager
from foundry_local_sdk.configuration import LogLevel

import _bootstrap  # noqa: F401
from foundry_config import build_configuration, get_model_reference


DEFAULT_MODELS = [
    "qwen2.5-0.5b-instruct-qnn-npu:1",
    "qwen2.5-1.5b-instruct-qnn-npu:3",
]


def format_percent(value: object) -> float:
    try:
        percent = float(value)
    except (TypeError, ValueError):
        return 0.0
    return percent * 100 if percent <= 1 else percent


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Foundry Local QNN/NPU model loading.")
    parser.add_argument("models", nargs="*", default=DEFAULT_MODELS, help="explicit QNN model IDs")
    parser.add_argument("--download", action="store_true", help="download uncached models before loading")
    parser.add_argument("--trace", action="store_true", help="print full Python traceback on failure")
    args = parser.parse_args()

    FoundryLocalManager.initialize(build_configuration("local_dictation_cleanup_npu_probe", LogLevel.INFORMATION))
    manager = FoundryLocalManager.instance

    print("Registering QNNExecutionProvider...")

    def on_ep_progress(ep_name: str, percent: float) -> None:
        print(f"\r  {ep_name:<35} {percent:5.1f}%", end="", flush=True)

    result = manager.download_and_register_eps(
        ["QNNExecutionProvider"],
        progress_callback=on_ep_progress,
    )
    print()
    print(f"EP registration: success={result.success} status={result.status}")
    print(f"registered_eps={getattr(result, 'registered_eps', None)}")
    print(f"failed_eps={getattr(result, 'failed_eps', None)}")

    print("Execution providers:")
    for ep in manager.discover_eps():
        print(f"  {ep.name} | registered={ep.is_registered}")
    print()

    failures = 0
    for model_id in args.models:
        print(f"=== {model_id} ===")
        try:
            model = get_model_reference(manager, model_id)
            print(f"id={model.id}")
            print(f"is_cached={model.is_cached}")
            if not model.is_cached:
                if not args.download:
                    print("skipped: not cached")
                    print()
                    continue

                print("downloading...")

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
                print(f"is_cached={model.is_cached}")

            print("loading...")
            model.load()
            print("load=ok")
            model.unload()
            print("unload=ok")
        except Exception as exc:
            failures += 1
            print(f"load=failed: {exc}")
            if args.trace:
                traceback.print_exc()
        print()

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
