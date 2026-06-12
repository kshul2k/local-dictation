from foundry_local_sdk import FoundryLocalManager
from foundry_local_sdk.configuration import LogLevel

import _bootstrap  # noqa: F401
from foundry_config import build_configuration


def main() -> int:
    FoundryLocalManager.initialize(
        build_configuration("local_dictation_cleanup_list_models", LogLevel.ERROR)
    )
    manager = FoundryLocalManager.instance

    rows = []
    for model in manager.catalog.list_models():
        for variant in model.variants:
            info = variant.info
            runtime = getattr(info, "runtime", None)
            rows.append(
                {
                    "size": getattr(info, "file_size_mb", None),
                    "alias": model.alias,
                    "id": variant.id,
                    "device": getattr(runtime, "device_type", "") if runtime else "",
                    "provider": getattr(runtime, "execution_provider", "") if runtime else "",
                    "task": getattr(info, "task", ""),
                    "cached": variant.is_cached,
                    "modalities": f"{variant.input_modalities}->{variant.output_modalities}",
                    "capabilities": variant.capabilities,
                }
            )

    rows.sort(key=lambda row: ((str(row["device"])), row["size"] or 0, row["alias"], row["id"]))
    print("size_mb | device | provider | cached | alias | id | task | modalities | capabilities")
    for row in rows:
        print(
            "{size} | {device} | {provider} | {cached} | {alias} | {id} | {task} | "
            "{modalities} | {capabilities}".format(**row)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
