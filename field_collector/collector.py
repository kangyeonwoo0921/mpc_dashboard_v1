"""Read-only collector for the field dashboard's live API (runs on the field PC).

    python collector.py --once        # one read, print the main values, write nothing
    python collector.py               # loop: one read per interval, write files (see below)

Only HTTP GET to ``config.json`` -> ``url``; no cookies, no credentials, no other request. Standard
library only (Python 3.9+), so nothing is installed on the field PC.

Files under ``output_dir``:

    latest.json                       last successful response (replaced atomically)
    raw/live_YYYY-MM-DD.jsonl         one line per read: collection time + response (static parts removed)
    outside/outside_YYYY-MM-DD.csv    same columns as the dashboard's outside export
                                      (시각,누적일사량,외부온도,외부풍속,외부풍향,일사센서) for mpc_lab
    collector.log                     start, errors, recoveries

A failed read is logged and the loop continues; nothing is written for that minute (a gap stays a gap).

Safeguards (the field PC is not ours): only one instance runs (file lock); the process runs at
below-normal priority; after a failed read it waits ``retry_wait_s`` before trying again; writing pauses
while free disk space is below ``min_free_disk_gb``; the interval cannot be shorter than 10 s.
"""

import argparse
import csv
import json
import os
import shutil
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
OUTSIDE_HEADER = ["시각", "누적일사량", "외부온도", "외부풍속", "외부풍향", "일사센서"]
OUTSIDE_KEYS = ["누적일사", "외부기온", "풍속", "풍향", "일사량"]
# Parts of the response that never change between reads (labels, unit tables, display duplicates).
STATIC_KEYS = {"cards": None, "farm": ["act_rows", "meas_rows", "onoff_rows"], "sens": ["methods"]}


def load_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if not str(config["url"]).startswith(("http://127.0.0.1", "http://localhost")):
        raise ValueError("url must point to the local dashboard (http://127.0.0.1 or http://localhost)")
    config.setdefault("interval_s", 60)
    config.setdefault("timeout_s", 10)
    config.setdefault("second_offset", 5)
    config.setdefault("retry_wait_s", 300)
    config.setdefault("min_free_disk_gb", 5)
    if config["interval_s"] < 10:
        raise ValueError("interval_s must be at least 10 s")
    return config


class SingleInstance:
    """Exclusive lock on ``collector.lock``; released automatically when the process ends."""

    def __init__(self, output_dir):
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        self.path = Path(output_dir) / "collector.lock"
        self.handle = None

    def acquire(self):
        handle = open(self.path, "a+")
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        self.handle = handle
        return True

    def release(self):
        if self.handle is not None:
            self.handle.close()
            self.handle = None


def lower_priority():
    """Below-normal CPU priority on Windows (no effect elsewhere or on failure)."""
    if os.name != "nt":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), 0x00004000)   # BELOW_NORMAL_PRIORITY_CLASS
    except Exception:
        pass


def disk_ok(output_dir, min_free_gb):
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(path).free >= float(min_free_gb) * 1024 ** 3


def fetch(url, timeout_s):
    """One GET request; returns the decoded JSON body."""
    request = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        return json.loads(response.read().decode("utf-8"))


def trimmed(response):
    out = dict(response)
    for key, subkeys in STATIC_KEYS.items():
        if key not in out:
            continue
        if subkeys is None:
            out.pop(key)
        elif isinstance(out[key], dict):
            out[key] = {k: v for k, v in out[key].items() if k not in subkeys}
    return out


def outside_row(response, collected_at):
    outside = (response.get("farm") or {}).get("outside") or {}
    values = [outside.get(key) for key in OUTSIDE_KEYS]
    return [collected_at.strftime("%Y-%m-%d %H:%M:%S"), *["" if v is None else v for v in values]]


def summary(response):
    farm = response.get("farm") or {}
    house = ((farm.get("zones") or [{}])[0].get("houses") or [{}])[0]
    return {"device_time": farm.get("time"), "outside": farm.get("outside"), "meas": house.get("meas"),
            "acts": house.get("acts"), "onoff": house.get("onoff"), "status": response.get("status")}


def _append_csv(path, header, row):
    new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8-sig" if new else "utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        if new:
            writer.writerow(header)
        writer.writerow(row)


def write_outputs(output_dir, response, collected_at):
    output_dir = Path(output_dir)
    day = collected_at.strftime("%Y-%m-%d")
    raw = output_dir / "raw" / f"live_{day}.jsonl"
    raw.parent.mkdir(parents=True, exist_ok=True)
    with raw.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"collected_at": collected_at.isoformat(timespec="seconds"),
                                 "response": trimmed(response)}, ensure_ascii=False) + "\n")
    _append_csv(output_dir / "outside" / f"outside_{day}.csv", OUTSIDE_HEADER, outside_row(response, collected_at))
    latest = output_dir / "latest.json"
    temporary = latest.with_suffix(".tmp")
    temporary.write_text(json.dumps({"collected_at": collected_at.isoformat(timespec="seconds"), "response": response},
                                    ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, latest)


def log(output_dir, message):
    path = Path(output_dir) / "collector.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(KST).isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp} {message}\n")


def sleep_until_next(interval_s, second_offset):
    now = time.time()
    next_tick = (now // interval_s + 1) * interval_s + second_offset
    time.sleep(max(0.0, next_tick - now))


def step(config, state, now=None):
    """One collection step; returns extra seconds to wait before the next regular tick."""
    output_dir = config["output_dir"]
    collected_at = now or datetime.now(KST)
    if not disk_ok(output_dir, config["min_free_disk_gb"]):
        if not state.get("disk_paused"):
            log(output_dir, f"paused: free disk below {config['min_free_disk_gb']} GB")
        state["disk_paused"] = True
        return 0
    if state.pop("disk_paused", False):
        log(output_dir, "resumed: disk space available")
    try:
        response = fetch(config["url"], config["timeout_s"])
        write_outputs(output_dir, response, collected_at)
    except Exception as error:                          # keep running; the gap stays visible
        if not state.get("failing"):
            log(output_dir, f"read failed: {type(error).__name__}: {error}")
        state["failing"] = True
        return config["retry_wait_s"]
    if state.pop("failing", False):
        log(output_dir, "recovered")
    return 0


def run(config):
    output_dir = config["output_dir"]
    lock = SingleInstance(output_dir)
    if not lock.acquire():
        print("another collector is already running; exiting")
        return 1
    lower_priority()
    log(output_dir, f"start url={config['url']} interval={config['interval_s']}s")
    state = {}
    try:
        while True:
            sleep_until_next(config["interval_s"], config["second_offset"])
            extra = step(config, state)
            if extra:
                time.sleep(extra)
    finally:
        lock.release()


def main(argv=None):
    parser = argparse.ArgumentParser(description="read-only collector for the field dashboard API")
    parser.add_argument("--config", default=str(Path(__file__).with_name("config.json")))
    parser.add_argument("--once", action="store_true", help="read once, print, write nothing")
    args = parser.parse_args(argv)
    config = load_config(args.config)
    if args.once:
        response = fetch(config["url"], config["timeout_s"])
        print(json.dumps(summary(response), ensure_ascii=False, indent=2))
        print("outside CSV row:", outside_row(response, datetime.now(KST)))
        return 0
    return run(config)


if __name__ == "__main__":
    sys.exit(main())
