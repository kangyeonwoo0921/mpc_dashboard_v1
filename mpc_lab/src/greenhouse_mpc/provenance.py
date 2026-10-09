"""Parameter provenance (baseline BL §19, status labels BL §17.15; reconciliation C-10).

Every configurable value is a ``Parameter``: an unknown value stays ``None`` and is never read as zero.
"""

from dataclasses import dataclass, field
from typing import Any

SOURCE_TYPES = frozenset({
    "field_guide_baseline", "cherry_tomato_study", "general_tomato_literature",
    "greenhouse_physics_literature", "manufacturer_spec", "measured", "calibrated",
    "operator_report",          # farm-operator statement recorded by the project (not in BL list; see docs)
    "project_decision",         # explicit user/design decision, e.g. OD-1
    "engineering_candidate",    # DP §23 / BL §17 provisional design candidates, not literature claims
    "temporary_test_fixture", "unknown",
})

STATUSES = frozenset({
    "literature_baseline", "field_guide_baseline", "provisional", "calibrated",
    "field_verified", "unknown",
    "field_required",           # BL §16.2 / DP §24: must come from the target site or hardware
})

VERIFIED_STATUSES = frozenset({"calibrated", "field_verified"})


class ProvenanceError(ValueError):
    """A parameter record violates the provenance rules."""


@dataclass(frozen=True)
class Parameter:
    value: Any
    units: str | None = None
    source_type: str = "unknown"
    source_id: str | None = None
    status: str = "unknown"
    verified: bool = False
    calibration_required: bool = True
    notes: str | None = None
    path: str = field(default="", compare=False)

    def __post_init__(self):
        where = self.path or "parameter"
        if self.source_type not in SOURCE_TYPES:
            raise ProvenanceError(f"{where}: source_type {self.source_type!r} not in {sorted(SOURCE_TYPES)}")
        if self.status not in STATUSES:
            raise ProvenanceError(f"{where}: status {self.status!r} not in {sorted(STATUSES)}")
        if not isinstance(self.verified, bool):
            raise ProvenanceError(f"{where}: verified must be a boolean")
        if self.verified and self.status not in VERIFIED_STATUSES:
            raise ProvenanceError(f"{where}: verified=true requires status calibrated or field_verified")
        if self.value is None and self.status not in ("unknown", "field_required"):
            raise ProvenanceError(f"{where}: a null value must have status unknown or field_required")
        if self.value is not None and self.status in ("unknown", "field_required"):
            raise ProvenanceError(f"{where}: status {self.status} must not carry a value")

    @property
    def known(self):
        return self.value is not None


PARAMETER_KEYS = frozenset(Parameter.__dataclass_fields__) - {"path"}


def is_parameter_record(node):
    return isinstance(node, dict) and "value" in node and "status" in node and "source_type" in node


def parse_parameters(node, path=""):
    """Recursively turn parameter records into ``Parameter`` objects; other mappings stay mappings."""
    if is_parameter_record(node):
        unknown_keys = set(node) - PARAMETER_KEYS
        if unknown_keys:
            raise ProvenanceError(f"{path}: unknown parameter fields {sorted(unknown_keys)}")
        return Parameter(**node, path=path)
    if isinstance(node, dict):
        return {key: parse_parameters(value, f"{path}.{key}" if path else str(key)) for key, value in node.items()}
    if isinstance(node, list):
        return [parse_parameters(value, f"{path}[{i}]") for i, value in enumerate(node)]
    return node


def iter_parameters(node):
    if isinstance(node, Parameter):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from iter_parameters(value)
    elif isinstance(node, list):
        for value in node:
            yield from iter_parameters(value)
