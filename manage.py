#!/usr/bin/env python
"""Django command-line entry point for the local Phase 1.7 application."""

import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "greenhouse_web.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django is not installed. Run: python -m pip install -r requirements.txt"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
