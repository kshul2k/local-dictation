import argparse

from foundry_local_sdk import FoundryLocalManager
from foundry_local_sdk.configuration import LogLevel

import _bootstrap  # noqa: F401
from foundry_config import build_configuration, get_model_reference


MODEL_ALIAS = "qwen2.5-0.5b"


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect Foundry Local provider/model status.")
    parser.add_argument(
        "--register-qnn",
        action="store_true",
        help="download and register QNNExecutionProvider if needed",
    )
    parser.add_argument("--model", default=MODEL_ALIAS, help="model alias or full model id")
    args = parser.parse_args()

    config = build_configuration("local_dictation_cleanup_probe", LogLevel.INFORMATION)
    FoundryLocalManager.initialize(config)
    manager = FoundryLocalManager.instance

    if args.register_qnn:
        print("Registering QNNExecutionProvider...")

        def on_progress(ep_name: str, percent: float) -> None:
            print(f"{ep_name}: {percent:5.1f}%")

        result = manager.download_and_register_eps(
            ["QNNExecutionProvider"],
            progress_callback=on_progress,
        )
        print(f"success={result.success}")
        print(f"status={result.status}")
        print(f"registered_eps={getattr(result, 'registered_eps', None)}")
        print(f"failed_eps={getattr(result, 'failed_eps', None)}")
        print()

    print("Execution providers:")
    for ep in manager.discover_eps():
        print(f"  {ep.name} | registered={ep.is_registered}")

    print()
    model = get_model_reference(manager, args.model)
    print(f"{args.model} selected model:")
    print(f"  id={model.id}")
    print(f"  is_cached={model.is_cached}")
    print(f"  is_loaded={model.is_loaded}")
    print(f"  context_length={model.context_length}")
    print(f"  capabilities={model.capabilities}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
