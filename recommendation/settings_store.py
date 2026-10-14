"""User-adjustable recommendation settings (priority-1 set, user decision 2026-10-12).

Every field carries its default, allowed range, unit and source so the web UI can show where a value comes
from. Values are stored server-side (``settings.json``) so every viewer sees the same settings; every change
is appended to ``settings_log.jsonl``. Location: ``RECOMMENDATION_DATA_DIR`` (default ``<project>/runtime``).
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SEOUL = ZoneInfo("Asia/Seoul")
PROJECT_DIR = Path(__file__).resolve().parent.parent
SCHEMA_VERSION = "recommendation-settings/0.1"
_LOCK = threading.Lock()


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    group: str
    kind: str                       # number | choice | date
    default: Any
    help: str
    source: str
    provisional: bool = True
    unit: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    choices: tuple = field(default_factory=tuple)   # ((value, label), ...)

    def meta(self):
        out = {"key": self.key, "label": self.label, "group": self.group, "kind": self.kind,
               "default": self.default, "help": self.help, "source": self.source, "provisional": self.provisional}
        if self.unit is not None:
            out["unit"] = self.unit
        if self.kind == "number":
            out.update({"min": self.minimum, "max": self.maximum, "step": self.step})
        if self.choices:
            out["choices"] = [{"value": v, "label": l} for v, l in self.choices]
        return out


GROUPS = (
    ("crop", "작물·운영"),
    ("shade_day", "차광커튼2 · 낮 차광"),
    ("shade_night", "차광커튼2 · 밤 보온"),
    ("diffuse", "차광커튼1 (산광) · 밤"),
)

FIELDS = (
    Field("growth_stage", "생육 단계", "crop", "choice", "vegetative",
          "추천 화면과 참고 가이드에 표시됩니다. 현장 확인 전 잠정값입니다.",
          "사용자 설정 (2026-10-12: 생육기, 10월 재배 가이드 참고)",
          choices=(("establishment", "활착기"), ("vegetative", "생육기"),
                   ("flowering", "개화·착과기"), ("harvest", "수확기"))),
    Field("transplant_date", "정식일", "crop", "date", "2026-09-22",
          "정식 후 경과일 표시에 사용합니다.", "현장 보고 (2026-10)", provisional=False),
    Field("operation_mode", "운영 모드", "crop", "choice", "auto",
          "자동: 밤 보온 + 낮 일사 차광을 모두 적용. 고온기: 밤 보온 끔. 저온기: 낮 차광 끔(빛 보존).",
          "프로젝트 결정 (상태 머신, CONTROL_LOGIC.md §3)", provisional=False,
          choices=(("auto", "자동"), ("hot", "고온기"), ("cold", "저온기"))),
    Field("shade_threshold_w_m2", "차광 일사 기준", "shade_day", "number", 700,
          "외부 일사(피복 위 센서 값)가 이 값 이상으로 지속될 때 차광을 추천합니다. 센서는 한낮에 실제보다 낮게 읽습니다.",
          "재배 가이드 순간 일사 600–700 W/m² 상한, 외부 일사로 임시 해석 (2026-10-12)",
          unit="W/m²", minimum=300, maximum=1000, step=10),
    Field("persistence_min", "지속 시간", "shade_day", "number", 15,
          "조건이 이 시간 동안 유지될 때만 펼치거나 걷습니다(잦은 개폐 방지). 예측 간격이 5분이라 5분 단위입니다.",
          "프로젝트 결정 (2026-10-12). 개념: Altes-Buch et al. 2019 proving time",
          unit="분", minimum=5, maximum=60, step=5),
    Field("min_hold_min", "최소 유지 시간", "shade_day", "number", 15,
          "한 번 바꾼 뒤 이 시간 동안은 다시 바꾸지 않습니다(안전 규칙 제외). 현장 스크린 이동 시간 확인 후 조정하세요.",
          "개념: Altes-Buch et al. 2019 minimum time. 값은 현장 확인 전 잠정",
          unit="분", minimum=0, maximum=120, step=5),
    Field("shade_night_closure_percent", "밤 보온 닫힘 정도", "shade_night", "number", 80,
          "밤에 차광커튼2를 이만큼 닫도록 추천합니다(80% 닫힘 = 20% 열림).",
          "8·10월 재배 가이드: 필요 시 약 80% 닫힘", unit="% 닫힘", minimum=0, maximum=100, step=5),
    Field("shade_night_start_offset_h", "보온 시작 (일몰 기준)", "shade_night", "number", -1.0,
          "음수면 일몰 전입니다.", "12월 재배 가이드: 일몰 1시간 전", unit="시간", minimum=-4, maximum=4, step=0.5),
    Field("shade_night_end_offset_h", "보온 해제 (일출 기준)", "shade_night", "number", 0.5,
          "양수면 일출 후입니다.", "12월 재배 가이드: 일출 30분 후", unit="시간", minimum=-4, maximum=4, step=0.5),
    Field("diffuse_tout_threshold_c", "산광 스크린 사용 외기 온도", "diffuse", "number", 15,
          "외기가 이 온도보다 낮을 때만 밤에 산광 스크린을 펼치도록 추천합니다.",
          "12월 재배 가이드 (OD-2 채택)", unit="°C", minimum=0, maximum=30, step=0.5),
    Field("diffuse_night_start_offset_h", "산광 시작 (일몰 기준)", "diffuse", "number", -2.0,
          "음수면 일몰 전입니다.", "12월 재배 가이드: 일몰 2시간 전", unit="시간", minimum=-4, maximum=4, step=0.5),
    Field("diffuse_night_end_offset_h", "산광 해제 (일출 기준)", "diffuse", "number", 2.0,
          "양수면 일출 후입니다.", "12월 재배 가이드: 일출 2시간 후", unit="시간", minimum=-4, maximum=4, step=0.5),
)
FIELD_BY_KEY = {f.key: f for f in FIELDS}
DEFAULTS = {f.key: f.default for f in FIELDS}


class SettingsError(ValueError):
    def __init__(self, errors):
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = errors


def data_dir() -> Path:
    value = os.environ.get("RECOMMENDATION_DATA_DIR")
    return Path(value) if value else PROJECT_DIR / "runtime"


def _validate_one(f: Field, value):
    if f.kind == "number":
        if isinstance(value, bool):
            raise ValueError("숫자가 필요합니다")
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError("숫자가 필요합니다") from None
        if number != number:
            raise ValueError("숫자가 필요합니다")
        if f.minimum is not None and number < f.minimum or f.maximum is not None and number > f.maximum:
            raise ValueError(f"{f.minimum}–{f.maximum} 범위여야 합니다")
        if f.step:
            steps = (number - (f.minimum or 0)) / f.step
            if abs(steps - round(steps)) > 1e-9:
                raise ValueError(f"{f.step} 단위여야 합니다")
        return int(number) if float(number).is_integer() and isinstance(f.default, int) else number
    if f.kind == "choice":
        if value not in {v for v, _ in f.choices}:
            raise ValueError("허용되지 않는 값입니다")
        return value
    if f.kind == "date":
        try:
            return date.fromisoformat(str(value)).isoformat()
        except ValueError:
            raise ValueError("YYYY-MM-DD 형식이어야 합니다") from None
    raise ValueError("알 수 없는 형식")


def validate(changes: dict) -> dict:
    if not isinstance(changes, dict):
        raise SettingsError({"values": "객체가 필요합니다"})
    errors, clean = {}, {}
    for key, value in changes.items():
        f = FIELD_BY_KEY.get(key)
        if f is None:
            errors[key] = "알 수 없는 설정입니다"
            continue
        try:
            clean[key] = _validate_one(f, value)
        except ValueError as error:
            errors[key] = str(error)
    if errors:
        raise SettingsError(errors)
    return clean


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load() -> dict:
    """Current values (defaults for anything missing or invalid) and when they were last changed."""
    stored = _read_json(data_dir() / "settings.json") or {}
    values = dict(DEFAULTS)
    for key, value in (stored.get("values") or {}).items():
        if key in FIELD_BY_KEY:
            try:
                values[key] = _validate_one(FIELD_BY_KEY[key], value)
            except ValueError:
                pass
    return {"values": values, "updated_at": stored.get("updated_at"), "updated_by": stored.get("updated_by")}


def history(limit: int = 20) -> list:
    path = data_dir() / "settings_log.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines[-limit:][::-1]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def save(changes: dict, changed_by: str | None = None, note: str | None = None, now: datetime | None = None) -> dict:
    """Validate and store changes; returns the new state. Unchanged values are not logged."""
    clean = validate(changes)
    now = now or datetime.now(SEOUL)
    with _LOCK:
        current = load()
        diff = {k: {"from": current["values"][k], "to": v} for k, v in clean.items() if current["values"][k] != v}
        values = {**current["values"], **clean}
        directory = data_dir()
        directory.mkdir(parents=True, exist_ok=True)
        stamp = now.isoformat(timespec="seconds")
        by = (changed_by or "").strip()[:40] or None
        if diff:
            record = {"values": values, "updated_at": stamp, "updated_by": by}
            temporary = directory / "settings.json.tmp"
            temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(directory / "settings.json")
            with (directory / "settings_log.jsonl").open("a", encoding="utf-8") as log:
                log.write(json.dumps({"time": stamp, "by": by, "note": (note or "").strip()[:200] or None,
                                      "changes": diff}, ensure_ascii=False) + "\n")
    return load()


def reset(keys=None, changed_by: str | None = None, now: datetime | None = None) -> dict:
    keys = list(FIELD_BY_KEY) if not keys else [k for k in keys if k in FIELD_BY_KEY]
    return save({k: DEFAULTS[k] for k in keys}, changed_by=changed_by, note="기본값으로 되돌림", now=now)


def describe() -> dict:
    """Everything the settings form needs."""
    state = load()
    return {"schema_version": SCHEMA_VERSION, "values": state["values"], "defaults": DEFAULTS,
            "updated_at": state["updated_at"], "updated_by": state["updated_by"],
            "groups": [{"key": k, "label": l} for k, l in GROUPS], "fields": [f.meta() for f in FIELDS],
            "history": history()}
