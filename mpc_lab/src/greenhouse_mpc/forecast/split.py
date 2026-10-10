"""Chronological, whole-day test periods with an expanding training window (config ``split``).

Roles by date (KST calendar days, inclusive ends):

    training only       ..first_test_start - 1
    development         first_test_start .. development_end      design decisions use only these
    checkpoint          .. checkpoint_end                         run once, no design change after it
    final               .. final_end                              sealed; run once

Each role span is cut into ``fold_length_days`` weeks; a week with fewer than ``min_test_days`` days of
valid kc is merged into the next week of the same role (the last one into the previous). Every fold
trains on all days before its test start; the last ``validation_days`` of that window are used for
early stopping only.

``table_for_role`` cuts the kc table at the end of the role, so a development run cannot read
checkpoint or final days.
"""

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

ROLES = ("development", "checkpoint", "final")
ROLE_END = {"development": "development_end", "checkpoint": "checkpoint_end", "final": "final_end"}


@dataclass(frozen=True)
class Fold:
    name: str
    role: str
    train_start: date        # first day of data
    validation_start: date   # first validation day (early stopping)
    test_start: date
    test_end: date           # inclusive

    def as_dict(self):
        return {k: str(v) for k, v in vars(self).items()}


def day_of(timestamps):
    """KST calendar day of tz-aware timestamps."""
    index = pd.DatetimeIndex(timestamps)
    if index.tz is None:
        raise ValueError("timestamps must be timezone-aware")
    return index.tz_convert("Asia/Seoul").date


def valid_days(table):
    frame = table.set_index("timestamp") if "timestamp" in table.columns else table
    valid = frame.kc_status.eq("valid")
    return set(pd.Series(day_of(frame.index[valid])))


def _role_spans(config, upto_role="final"):
    start = config.date("first_test_start")
    spans = []
    for role in ROLES[:ROLES.index(upto_role) + 1]:
        end = config.date(ROLE_END[role])
        spans.append((role, start, end))
        start = end + timedelta(days=1)
    return spans


def make_folds(config, table, upto_role="final"):
    """Folds of every role up to and including ``upto_role`` (uses only the dates of valid kc days)."""
    days_with_data = valid_days(table)
    first_day = min(day_of(table.timestamp))
    length = int(config.value("split.fold_length_days"))
    minimum = int(config.value("split.min_test_days"))
    validation = int(config.value("split.validation_days"))
    folds = []
    for role, start, end in _role_spans(config, upto_role):
        weeks, cursor = [], start
        while cursor <= end:
            weeks.append([cursor, min(cursor + timedelta(days=length - 1), end)])
            cursor += timedelta(days=length)
        merged = []
        for week in weeks:
            if merged and _count(days_with_data, *merged[-1]) < minimum:
                merged[-1][1] = week[1]
            else:
                merged.append(week)
        if len(merged) > 1 and _count(days_with_data, *merged[-1]) < minimum:
            merged[-2][1] = merged.pop()[1]
        for i, (test_start, test_end) in enumerate(merged, 1):
            folds.append(Fold(f"{role}_{i}", role, first_day, test_start - timedelta(days=validation),
                              test_start, test_end))
    return folds


def _count(days, start, end):
    return sum(start <= d <= end for d in days)


def table_for_role(table, config, role):
    """kc table cut after the last day of ``role`` (later roles stay unread)."""
    end = config.date(ROLE_END[role])
    return table[pd.Series(day_of(table.timestamp), index=table.index) <= end].reset_index(drop=True)
