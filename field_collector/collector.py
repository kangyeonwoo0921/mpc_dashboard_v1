"""Read-only collector for the field dashboard's live API (runs on the field PC).

    python collector.py --once        # one read, print the main values, write nothing
    python collector.py               # loop: one read per interval, write files (see below)

Requests: HTTP GET to ``config.json`` -> ``url`` (a local dashboard only). If the dashboard answers with
its login page and ``credentials.json`` exists next to ``config.json`` (only with the operator's consent),
the collector logs in once with a POST to ``/login`` of the same local dashboard, keeps the session
cookie in memory only (never on disk) and repeats the GET. At most one login attempt per
``retry_wait_s``. Without ``credentials.json`` it never logs in. No browser cookies are reused.
Standard library only (Python 3.9+), so nothing is installed on the field PC.

Files under ``output_dir`` (a folder on the field PC's own disk):

    latest.json                       last successful response (replaced atomically)
    raw/live_YYYY-MM-DD.jsonl         one line per read: collection time + response (static parts removed)
    outside/outside_YYYY-MM-DD.csv    same columns as the dashboard's outside export
                                      (시각,누적일사량,외부온도,외부풍속,외부풍향,일사센서) for mpc_lab
    collector.log                     start, errors, recoveries

A failed read is logged and the loop continues; nothing is written for that minute (a gap stays a gap).

``sync_dir`` (optional, e.g. the Google Drive folder): a background thread copies changed files from
``output_dir`` to it every interval. A slow or unavailable sync folder never stops or delays collection;
missed copies are made once it is back. On start, today's files that exist only in ``sync_dir`` are copied
back to ``output_dir`` first, so a restart never overwrites rows already synced. Errors never end the
process: they are logged (to ``output_dir``) and the next interval runs as usual.

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
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
OUTSIDE_HEADER = ["시각", "누적일사량", "외부온도", "외부풍속", "외부풍향", "일사센서"]
OUTSIDE_KEYS = ["누적일사", "외부기온", "풍속", "풍향", "일사량"]
# Parts of the response that never change between reads (labels, unit tables, display duplicates).
STATIC_KEYS = {"cards": None, "farm": ["act_rows", "meas_rows", "onoff_rows"], "sens": ["methods"]}


def load_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8-sig"))   # tolerate a BOM (PowerShell 5.1)
    if not str(config["url"]).startswith(("http://127.0.0.1", "http://localhost")):
        raise ValueError("url must point to the local dashboard (http://127.0.0.1 or http://localhost)")
    config.setdefault("interval_s", 60)
    config.setdefault("timeout_s", 10)
    config.setdefault("second_offset", 5)
    config.setdefault("retry_wait_s", 300)
    config.setdefault("min_free_disk_gb", 5)
    config["sync_dir"] = config.get("sync_dir") or None
    if config["interval_s"] < 10:
        raise ValueError("interval_s must be at least 10 s")
    config["credentials"] = load_credentials(config.get("credentials_file") or Path(path).with_name("credentials.json"))
    return config


def load_credentials(path):
    """{"username", "password"} from a local file the operator agreed to, or None when the file is absent."""
    path = Path(path)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not (isinstance(data.get("username"), str) and isinstance(data.get("password"), str) and data["username"]):
        raise ValueError(f"{path.name}: needs string fields 'username' and 'password'")
    return {"username": data["username"], "password": data["password"]}


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


class LoginRequired(Exception):
    """The dashboard answered with its login page and no credentials.json is configured."""


class LoginFailed(Exception):
    """Logging in did not give access (wrong credentials, or a retry too soon after the last attempt)."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow redirects: only the configured URL (and /login when needed) is ever requested."""

    def redirect_request(self, *args, **kwargs):
        return None


REDIRECTS = (301, 302, 303, 307, 308)


class Session:
    """GETs the live API; logs in only when the dashboard asks for it and credentials were provided.

    Redirects are not followed, so a redirect to the login page is recognised from its Location header
    without loading that page, and the page shown after logging in is never requested.
    """

    def __init__(self, url, credentials=None, min_login_interval_s=300):
        self.url = url
        self.credentials = credentials
        self.min_login_interval_s = min_login_interval_s
        self.last_login = None
        self.cookies = CookieJar()                       # memory only, never written to disk
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies),
                                                  _NoRedirect())

    def _get(self, timeout_s):
        request = urllib.request.Request(self.url, method="GET", headers={"Accept": "application/json"})
        try:
            with self.opener.open(request, timeout=timeout_s) as response:
                return response.read(), response.headers.get("Content-Type", ""), response.geturl()
        except urllib.error.HTTPError as error:
            if error.code in REDIRECTS:              # e.g. 302 -> /login?next=/api/live: not followed
                return b"", "", urllib.parse.urljoin(self.url, error.headers.get("Location", ""))
            raise

    def _decode(self, body, content_type, final_url):
        """JSON body, None for the login page, error for anything else."""
        if "json" in content_type:
            return json.loads(body.decode("utf-8"))
        if urllib.parse.urlparse(final_url).path.rstrip("/").endswith("/login"):
            return None
        raise ValueError(f"unexpected {content_type or 'response'} from {final_url}")

    def login(self, timeout_s):
        now = time.monotonic()
        if self.last_login is not None and now - self.last_login < self.min_login_interval_s:
            raise LoginFailed("login was tried less than retry_wait_s ago; waiting before trying again")
        self.last_login = now
        parts = urllib.parse.urlparse(self.url)
        form = urllib.parse.urlencode({"username": self.credentials["username"],
                                       "password": self.credentials["password"]}).encode("utf-8")
        request = urllib.request.Request(f"{parts.scheme}://{parts.netloc}/login", data=form, method="POST",
                                         headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with self.opener.open(request, timeout=timeout_s) as response:
                response.read()
                return response.status, response.headers
        except urllib.error.HTTPError as error:
            if error.code not in REDIRECTS:              # the usual answer is a redirect; it is not followed
                raise
            return error.code, error.headers

    def get_json(self, timeout_s):
        data = self._decode(*self._get(timeout_s))
        if data is not None:
            return data
        if self.credentials is None:
            raise LoginRequired("the dashboard asks for a login; add credentials.json (README, section 0) "
                                "only after the operator agrees")
        self.login(timeout_s)
        data = self._decode(*self._get(timeout_s))
        if data is None:
            raise LoginFailed("still on the login page after logging in; check credentials.json")
        return data


def _cookie_attributes(headers):
    """Set-Cookie headers without their values: 'name; Path=/; HttpOnly; ...'."""
    out = []
    for header in headers.get_all("Set-Cookie") or []:
        name, _, rest = header.partition("=")
        attributes = [a.strip() for a in rest.split(";")[1:]]
        out.append("; ".join([name.strip() + "=<hidden>", *attributes]))
    return out


def check_login(config):
    """Step-by-step login diagnosis; prints statuses, redirect targets and cookie attributes, never secrets."""
    credentials = config.get("credentials")
    if credentials is None:
        print("credentials.json not found next to config.json")
        return 2
    session = Session(config["url"], credentials, min_login_interval_s=0)
    timeout_s = config["timeout_s"]
    body, kind, final = session._get(timeout_s)
    print(f"1 GET data URL  -> {kind or 'redirect'} {final}")
    status, headers = session.login(timeout_s)
    print(f"2 POST /login   -> {status} Location={headers.get('Location')}")
    for line in _cookie_attributes(headers):
        print(f"  Set-Cookie: {line}")
    print(f"  cookies kept: {[c.name for c in session.cookies]}")
    body, kind, final = session._get(timeout_s)
    print(f"3 GET data URL  -> {kind or 'redirect'} {final}")
    print("username length:", len(credentials["username"]), "| first letter uppercase:", credentials["username"][:1].isupper())
    return 0


def fetch(url, timeout_s, session=None):
    """One read of the live API; returns the decoded JSON body."""
    return (session or Session(url)).get_json(timeout_s)


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
    """Append to collector.log; never raises (a logging failure must not stop collection)."""
    try:
        path = Path(output_dir) / "collector.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(KST).isoformat(timespec="seconds")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp} {message}\n")
    except Exception:
        pass


SYNC_PATTERNS = ("latest.json", "collector.log", "outside/outside_*.csv", "raw/live_*.jsonl")
# Sync folders such as Google Drive upload the whole file on every change. The raw archive grows to a few
# MB a day and nothing reads it live, so it is copied at most once per RAW_SYNC_EVERY_S (and once more
# after its day ends); latest.json and the small outside CSV are copied every interval.
RAW_SYNC_EVERY_S = 3600


def _copy_atomic(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".part")
    shutil.copyfile(source, temporary)
    os.replace(temporary, target)


def sync_outputs(output_dir, sync_dir, synced, now=None, raw_every_s=RAW_SYNC_EVERY_S):
    """Copy files of output_dir that changed since the last successful copy; returns the number copied.

    ``synced`` maps relative path -> (size, mtime_ns, copied_at). Raises on the first failure; the files
    not copied are retried on the next call. Today's raw archive is copied at most every ``raw_every_s``.
    """
    output_dir, sync_dir, copied = Path(output_dir), Path(sync_dir), 0
    now = now if now is not None else time.time()
    today = datetime.fromtimestamp(now, KST).strftime("%Y-%m-%d")
    for pattern in SYNC_PATTERNS:
        for source in sorted(output_dir.glob(pattern)):
            relative = source.relative_to(output_dir).as_posix()
            stat = source.stat()
            previous = synced.get(relative)
            if previous and previous[:2] == (stat.st_size, stat.st_mtime_ns):
                continue
            if (previous and relative.startswith("raw/") and today in relative
                    and now - previous[2] < raw_every_s):
                continue                                 # today's raw archive: hourly
            _copy_atomic(source, sync_dir / relative)
            synced[relative] = (stat.st_size, stat.st_mtime_ns, now)
            copied += 1
    return copied


def seed_from_sync(output_dir, sync_dir, day):
    """Copy the given day's files that exist only in sync_dir back to output_dir (keeps synced rows)."""
    copied = []
    for relative in (f"outside/outside_{day}.csv", f"raw/live_{day}.jsonl"):
        source, target = Path(sync_dir) / relative, Path(output_dir) / relative
        if source.exists() and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            copied.append(relative)
    return copied


def sync_loop(config, stop_event):
    """Background copies to sync_dir; failures are logged once and retried every interval."""
    synced, failing = {}, False
    while not stop_event.is_set():
        try:
            sync_outputs(config["output_dir"], config["sync_dir"], synced)
            if failing:
                log(config["output_dir"], "sync recovered")
            failing = False
        except Exception as error:
            if not failing:
                log(config["output_dir"], f"sync failed: {type(error).__name__}: {error}")
            failing = True
        stop_event.wait(config["interval_s"])


def sleep_until_next(interval_s, second_offset):
    now = time.time()
    next_tick = (now // interval_s + 1) * interval_s + second_offset
    time.sleep(max(0.0, next_tick - now))


def step(config, state, now=None):
    """One collection step; returns extra seconds to wait before the next regular tick."""
    output_dir = config["output_dir"]
    collected_at = now or datetime.now(KST)
    try:
        space_ok = disk_ok(output_dir, config["min_free_disk_gb"])
    except Exception as error:
        log(output_dir, f"disk check failed: {type(error).__name__}: {error}")
        return config["retry_wait_s"]
    if not space_ok:
        if not state.get("disk_paused"):
            log(output_dir, f"paused: free disk below {config['min_free_disk_gb']} GB")
        state["disk_paused"] = True
        return 0
    if state.pop("disk_paused", False):
        log(output_dir, "resumed: disk space available")
    if "session" not in state:
        state["session"] = Session(config["url"], config.get("credentials"), config["retry_wait_s"])
    try:
        response = fetch(config["url"], config["timeout_s"], state["session"])
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
    import threading

    output_dir = config["output_dir"]
    lock = SingleInstance(output_dir)
    if not lock.acquire():
        print("another collector is already running; exiting")
        return 1
    lower_priority()
    login = "on (credentials.json)" if config.get("credentials") else "off"
    log(output_dir, f"start url={config['url']} interval={config['interval_s']}s login={login} "
                    f"sync={'on' if config['sync_dir'] else 'off'}")
    stop = threading.Event()
    if config["sync_dir"]:
        try:
            seeded = seed_from_sync(output_dir, config["sync_dir"], datetime.now(KST).strftime("%Y-%m-%d"))
            if seeded:
                log(output_dir, f"seeded from sync folder: {', '.join(seeded)}")
        except Exception as error:
            log(output_dir, f"seed skipped: {type(error).__name__}: {error}")
        threading.Thread(target=sync_loop, args=(config, stop), name="sync", daemon=True).start()
    state = {}
    try:
        while True:
            sleep_until_next(config["interval_s"], config["second_offset"])
            try:
                extra = step(config, state)
            except Exception as error:                  # never let one minute end the collector
                log(output_dir, f"step error: {type(error).__name__}: {error}")
                extra = config["retry_wait_s"]
            if extra:
                time.sleep(extra)
    finally:
        stop.set()
        lock.release()


def main(argv=None):
    parser = argparse.ArgumentParser(description="read-only collector for the field dashboard API")
    parser.add_argument("--config", default=str(Path(__file__).with_name("config.json")))
    parser.add_argument("--once", action="store_true", help="read once, print, write nothing")
    parser.add_argument("--check-login", action="store_true", help="diagnose the login step (no secrets printed)")
    args = parser.parse_args(argv)
    config = load_config(args.config)
    if args.check_login:
        return check_login(config)
    if args.once:
        try:
            response = fetch(config["url"], config["timeout_s"], Session(config["url"], config.get("credentials")))
        except (LoginRequired, LoginFailed) as error:
            print(f"{type(error).__name__}: {error}")
            return 2
        print(json.dumps(summary(response), ensure_ascii=False, indent=2))
        print("outside CSV row:", outside_row(response, datetime.now(KST)))
        return 0
    return run(config)


if __name__ == "__main__":
    sys.exit(main())
