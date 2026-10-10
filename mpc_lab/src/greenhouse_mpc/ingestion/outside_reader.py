"""Raw outside CSV -> parsed rows (one output row per raw data row, nothing dropped).

Raw files are only read. Each row keeps its source file, line number and original text, the layout it
was matched to and a schema status:

- ``ok``                      field count and wind-direction position match a known layout
- ``trailing_empty_removed``  one empty trailing field removed, then matched (observed export anomaly)
- ``anomaly``                 no unambiguous layout; values are left unparsed for review

The header row is recorded but never used to assign columns (schema drift happens under one header).
"""

import csv
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from .outside_schema import VARIABLES

WIND_TOKEN = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*°\s*(\S*)\s*$")
NUMERIC_VARIABLES = tuple(v for v in VARIABLES if v != "wind_dir")


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def match_layout(fields, layouts):
    """Return (layout_name, fields_used, schema_status, note)."""
    candidates = [(list(fields), "ok", "")]
    if fields and fields[-1].strip() == "":
        candidates.append((list(fields[:-1]), "trailing_empty_removed", "one empty trailing field removed"))
    for used, status, note in candidates:
        wind_positions = [i for i, value in enumerate(used) if WIND_TOKEN.match(value)]
        for name, layout in layouts.items():
            if len(used) == len(layout) and wind_positions == [layout.index("wind_dir")]:
                return name, used, status, note
    wind_positions = [i for i, value in enumerate(fields) if WIND_TOKEN.match(value)]
    return None, None, "anomaly", f"{len(fields)} fields, wind-direction token at {wind_positions}; no unambiguous layout"


def _number(text):
    text = (text or "").strip()
    if text == "":
        return math.nan, False
    try:
        value = float(text)
    except ValueError:
        return math.nan, True          # present but unparseable
    return (value, False) if math.isfinite(value) else (math.nan, True)


def parse_row(fields, layouts, timestamp_format, timezone):
    """Parse one raw data row (list of strings) into a flat record."""
    record = {"raw_text": json.dumps(fields, ensure_ascii=False), "n_fields": len(fields),
              "raw_timestamp": fields[0] if fields else ""}
    try:
        record["timestamp"] = datetime.strptime(record["raw_timestamp"].strip(), timestamp_format).replace(tzinfo=timezone)
        record["timestamp_ok"] = True
    except ValueError:
        record["timestamp"], record["timestamp_ok"] = pd.NaT, False
    layout, used, status, note = match_layout(fields, layouts)
    record.update(layout=layout, schema_status=status, schema_note=note)
    for name in VARIABLES:
        record[f"{name}_raw"] = None
        record[name] = math.nan
        record[f"{name}_parse_error"] = False
    record["wind_dir_compass"] = None
    if layout is None:
        return record
    for name, text in zip(layouts[layout], used):
        if name == "timestamp":
            continue
        record[f"{name}_raw"] = text
        if name == "wind_dir":
            match = WIND_TOKEN.match(text)
            record["wind_dir"] = float(match.group(1))
            record["wind_dir_compass"] = match.group(2) or None
        else:
            record[name], record[f"{name}_parse_error"] = _number(text)
    return record


def read_outside_file(path, config):
    """Parsed rows of one export plus file-level metadata."""
    path = Path(path)
    with path.open(encoding=config.encoding, newline="") as fh:
        rows = list(csv.reader(fh))
    header = tuple(cell.strip() for cell in rows[0]) if rows else ()
    records = []
    for line, fields in enumerate(rows[1:], start=2):
        if not fields:
            continue                    # blank line: nothing to parse (counted in metadata)
        record = parse_row(fields, config.layouts, config.timestamp_format, config.timezone)
        record.update(source_file=path.name, source_line=line)
        records.append(record)
    meta = {"file": path.name, "sha256": file_digest(path), "header": list(header),
            "header_known": header in config.known_headers, "data_rows": len(records),
            "blank_lines": sum(1 for fields in rows[1:] if not fields)}
    return records, meta


def read_outside_exports(config, paths=None):
    """All exports in ``config.raw_dir`` (sorted by name) -> (parsed DataFrame, per-file metadata)."""
    paths = sorted(Path(p) for p in paths) if paths is not None else sorted(Path(config.raw_dir).glob(config.file_glob))
    records, metas = [], []
    for path in paths:
        file_records, meta = read_outside_file(path, config)
        records.extend(file_records)
        metas.append(meta)
    frame = pd.DataFrame.from_records(records)
    if frame.empty:
        return frame, metas
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True).dt.tz_convert(config.timezone)
    frame = frame.sort_values(["timestamp", "source_file", "source_line"], kind="mergesort", na_position="last")
    return frame.reset_index(drop=True), metas
