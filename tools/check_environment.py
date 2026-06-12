import importlib.metadata
import os
import platform
import struct
import sys


def package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not installed"


def main() -> int:
    print(f"Python: {sys.version.split()[0]}")
    print(f"Python exe: {sys.executable}")
    print(f"Python platform.machine: {platform.machine()}")
    print(f"Python bits: {struct.calcsize('P') * 8}")
    print(f"OS: {platform.platform()}")
    print(f"PROCESSOR_IDENTIFIER: {os.environ.get('PROCESSOR_IDENTIFIER', '')}")
    print(f"PROCESSOR_ARCHITECTURE: {os.environ.get('PROCESSOR_ARCHITECTURE', '')}")
    print(f"PROCESSOR_ARCHITEW6432: {os.environ.get('PROCESSOR_ARCHITEW6432', '')}")
    print()
    print(f"foundry-local-sdk-winml: {package_version('foundry-local-sdk-winml')}")
    print(f"foundry-local-core-winml: {package_version('foundry-local-core-winml')}")
    print(f"pyperclip: {package_version('pyperclip')}")
    print(f"pyautogui: {package_version('PyAutoGUI')}")
    print()

    machine = platform.machine().lower()
    host_looks_arm = "arm" in os.environ.get("PROCESSOR_IDENTIFIER", "").lower()
    if host_looks_arm and machine not in {"arm64", "aarch64"}:
        print(
            "WARNING: This looks like a Snapdragon/ARM64 host, but Python is "
            "not running as ARM64. Install/use Windows ARM64 Python before "
            "testing NPU acceleration."
        )
        return 2

    if sys.version_info[:2] not in {(3, 11), (3, 12), (3, 13)}:
        print(
            "WARNING: Foundry Local currently advertises Python 3.11, 3.12, "
            "and 3.13 support. Prefer one of those for this experiment."
        )
        return 2

    print("Environment shape looks suitable for the Foundry Local WinML test.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
