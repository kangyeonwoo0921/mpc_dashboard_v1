"""Stable, one-based identifiers. No Blender automatic suffixes are allowed."""


def column_name(kind, station, grid):
    return f"GH_COL_{kind.upper()}_X{station:03d}_Y{grid:02d}"


def rafter_name(station, span):
    return f"GH_RAFTER_X{station:03d}_S{span:02d}"


def vent_name(span, index=1):
    return f"GH_VENT_S{span:02d}_{index:02d}"


def bed_name(span, row):
    return f"GH_BED_S{span:02d}_R{row:02d}"
