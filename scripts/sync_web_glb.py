"""Compatibility wrapper; use :mod:`scripts.sync_web_assets`."""

from sync_web_assets import main


if __name__ == "__main__":
    raise SystemExit(main())
