"""Where generated data goes.

Defaults keep everything under ``mpc_lab/data``. On the operations PC two environment variables move it:

    GREENHOUSE_DATA_DIR     processed data, models, live forecast log (e.g. C:\GreenhouseOps, outside
                            OneDrive, so files rewritten every 5 min are not synced)
    GREENHOUSE_SHARED_DIR   small files other machines read (latest_forecast.json), e.g. a synced folder

Raw exports (config raw_dir) and ``records/`` stay in the project.
"""

import os
from pathlib import Path

from .config_loader import CONFIG_DIR

MPC_LAB_DIR = CONFIG_DIR.parent


def data_dir():
    value = os.environ.get("GREENHOUSE_DATA_DIR")
    return Path(value) if value else MPC_LAB_DIR / "data"


def data_dir_overridden():
    return bool(os.environ.get("GREENHOUSE_DATA_DIR"))


def processed_dir():
    return data_dir() / "processed"


def shared_dir():
    value = os.environ.get("GREENHOUSE_SHARED_DIR")
    return Path(value) if value else None
