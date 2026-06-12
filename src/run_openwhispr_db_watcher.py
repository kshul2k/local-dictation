from __future__ import annotations

import traceback
import site

from runtime_paths import ROOT_DIR, log_path


BOOTSTRAP_LOG = log_path("openwhispr_db_watcher.bootstrap.log")
VENV_SITE_PACKAGES = ROOT_DIR / ".venv" / "Lib" / "site-packages"


def main() -> int:
    try:
        if VENV_SITE_PACKAGES.exists():
            site.addsitedir(VENV_SITE_PACKAGES)

        import openwhispr_db_cleanup_watcher

        return openwhispr_db_cleanup_watcher.main()
    except BaseException:
        BOOTSTRAP_LOG.write_text(traceback.format_exc(), encoding="utf-8")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
