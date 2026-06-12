import os

from foundry_local_sdk import Configuration
from foundry_local_sdk.configuration import LogLevel

from runtime_paths import ROOT_DIR

PROJECT_DIR = ROOT_DIR
DEFAULT_MODEL_CACHE_DIR = PROJECT_DIR / ".foundry-model-cache"


def build_configuration(app_name: str, log_level: LogLevel = LogLevel.INFORMATION) -> Configuration:
    model_cache_dir = Path(
        os.environ.get("DICTATION_CLEANUP_MODEL_CACHE", str(DEFAULT_MODEL_CACHE_DIR))
    )
    model_cache_dir.mkdir(parents=True, exist_ok=True)
    return Configuration(
        app_name=app_name,
        log_level=log_level,
        model_cache_dir=str(model_cache_dir),
    )


def get_model_reference(manager: object, model_ref: str) -> object:
    catalog = manager.catalog
    if ":" in model_ref:
        model = catalog.get_model_variant(model_ref)
    else:
        model = catalog.get_model(model_ref)
    if model is None:
        raise RuntimeError(f"Model not found: {model_ref}")
    return model
