"""Meter-based geometry calculations; deliberately independent of bpy."""
import math

EPS = 1e-8
SCREEN_MIN_SCALE = 1e-6


def make_stations(total_length, spacing, include_ends=True):
    if not math.isfinite(total_length) or not math.isfinite(spacing) or min(total_length, spacing) <= 0:
        raise ValueError("length and spacing must be finite and positive")
    count = math.floor(total_length / spacing)
    values = [-total_length / 2 + i * spacing for i in range(count + 1)]
    if include_ends:
        if math.isclose(values[-1], total_length / 2, abs_tol=EPS):
            values[-1] = total_length / 2
        else:
            values.append(total_length / 2)
    return values


def secondary_stations(length, spacing, main_spacing):
    main = make_stations(length, main_spacing)
    return [x for x in make_stations(length, spacing)
            if not any(math.isclose(x, m, abs_tol=EPS) for m in main)]


def span_bounds(count, width):
    return [-count * width / 2 + i * width for i in range(count + 1)]


def span_centers(count, width):
    return [b + width / 2 for b in span_bounds(count, width)[:-1]]


def span_start_offsets(greenhouse):
    # Distance of each span's front end behind X1; all zero for a rectangular footprint.
    offsets = greenhouse.get("span_start_offsets")
    return list(offsets) if offsets is not None else [0.0] * greenhouse["span_count"]


def span_x_range(greenhouse, span):
    """One-based span -> (front x, rear x); every span ends at the rear X23 plane."""
    return -greenhouse["length"] / 2 + span_start_offsets(greenhouse)[span - 1], greenhouse["length"] / 2


def gridline_x_start(greenhouse, gridline):
    """One-based gridline -> front x of the longer of its adjacent spans."""
    offsets = span_start_offsets(greenhouse)
    adjacent = [offsets[k] for k in (gridline - 2, gridline - 1) if 0 <= k < len(offsets)]
    return -greenhouse["length"] / 2 + min(adjacent)


def front_x_at(greenhouse, y):
    """Front-plane x candidates at width position y (two at a span boundary)."""
    bounds = span_bounds(greenhouse["span_count"], greenhouse["span_width"])
    return {span_x_range(greenhouse, j)[0] for j in range(1, greenhouse["span_count"] + 1)
            if bounds[j - 1] - EPS <= y <= bounds[j] + EPS}


def stations_from(stations, start):
    return [(i, x) for i, x in enumerate(stations, 1) if x >= start - 1e-6]


def roof_arch_radius(greenhouse):
    roof = greenhouse["roof"]
    return roof["arch_radius"] if roof["profile"] == "circular_pointed_arch" else None


def pointed_arch_center(width, eave, ridge, radius):
    # Circle through (-width/2, eave) and (0, ridge); returns (x, z) of the left half's center.
    half, rise = width / 2, ridge - eave
    chord = math.hypot(half, rise)
    if radius < chord / 2:
        raise ValueError("arch radius must be at least half the eave-to-ridge chord")
    offset = math.sqrt(radius ** 2 - (chord / 2) ** 2)
    return -half / 2 + offset * rise / chord, (eave + ridge) / 2 - offset * half / chord


def arch_height(y, width, eave, ridge, radius=None):
    if radius is None:
        # Quadratic Bezier with P1.z = 2*ridge-eave.
        return ridge - (ridge - eave) * (2 * y / width) ** 2
    # Two circular arcs meeting at the ridge; each half's center lies across the span axis.
    cx, cz = pointed_arch_center(width, eave, ridge, radius)
    return cz + math.sqrt(radius ** 2 - (abs(y) + cx) ** 2)


def generate_arch_points(span_width, eave_height, ridge_height, segments, radius=None):
    return [(y, arch_height(y, span_width, eave_height, ridge_height, radius))
            for y in [-span_width / 2 + span_width * i / segments for i in range(segments + 1)]]


def bed_y_positions(span_center_y, span_width, rows_per_span, edge_margin=0.0):
    if rows_per_span == 0:
        return []
    usable = span_width - 2 * edge_margin
    if rows_per_span < 0 or usable <= 0:
        raise ValueError("rows and available bed width are invalid")
    return [span_center_y - usable / 2 + (r + 0.5) * usable / rows_per_span
            for r in range(rows_per_span)]


def clamp_percent(percent):
    if not math.isfinite(percent):
        raise ValueError("opening percent must be finite")
    return max(0.0, min(100.0, percent))


def vent_angle(percent, max_angle_deg, side="positive_y"):
    return math.radians(clamp_percent(percent) * max_angle_deg / 100) * (1 if side == "positive_y" else -1)


def screen_scale(percent):
    return max(1 - clamp_percent(percent) / 100, SCREEN_MIN_SCALE)


def screen_pieces_per_span(values):
    """Fabric pieces per span of one screen layer: two halves when they run out from both gutters."""
    return 2 if values.get("travel") == "across_span" and values.get("gather_side") == "both" else 1


def screen_deployed_y_ranges(center_y, width, fraction, gather_side):
    """Across-span screens: [(y_low, y_high)] covered by fabric deployed by ``fraction`` over one span.
    'both' = two halves stored at both gutters that meet at the centre when fully deployed."""
    if gather_side == "both":
        half = fraction * width / 2
        return [(center_y - width / 2, center_y - width / 2 + half), (center_y + width / 2 - half, center_y + width / 2)]
    sign = -1 if gather_side == "negative_y" else 1
    edge = center_y + sign * width / 2
    return [tuple(sorted((edge, edge - sign * fraction * width)))]


def vent_rotation_from_post_deg(greenhouse, panel_width_ratio, angle_from_post_deg):
    """Leaf rotation (deg) from closed to fully open, from the field angle measured between the
    vertical ridge post (pointing down) and the opened leaf.

    The leaf hinges at the ridge and its chord runs to the free edge at panel_width_ratio*span_width.
    Closed, the chord lies below horizontal by the roof's chord angle; fully open it lies
    (angle_from_post - 90) above horizontal. Pure geometry of the configured roof profile.
    """
    width = greenhouse["span_width"] * panel_width_ratio
    eave, ridge = greenhouse["eave_height"]["value"], greenhouse["ridge_height"]["value"]
    drop = ridge - arch_height(width, greenhouse["span_width"], eave, ridge, roof_arch_radius(greenhouse))
    closed_below_horizontal = math.degrees(math.atan2(drop, width))
    return closed_below_horizontal + (angle_from_post_deg - 90)


def vent_sides(config):
    side = config["roof_vents"]["side"]
    return ["positive_y", "negative_y"] if side == "both" else [side]


def vent_half_length_ratio(config):
    g, v = config["greenhouse"], config["roof_vents"]
    if v.get("end_clearance") is not None:
        return (g["length"] / 2 - v["end_clearance"]) / g["length"]
    return v["panel_length_ratio"] / 2


def vent_bounds(config, side=None, span=1):
    g, v = config["greenhouse"], config["roof_vents"]
    side = side or vent_sides(config)[0]
    x0, x1 = span_x_range(g, span)
    span_length = x1 - x0
    center = (x0 + x1) / 2 + span_length * (v["x_center_ratio"] - 0.5)
    if v.get("end_clearance") is not None:
        half_length = span_length / 2 - v["end_clearance"]
    else:
        half_length = span_length * v["panel_length_ratio"] / 2
    width = g["span_width"] * v["panel_width_ratio"]
    return center - half_length, center + half_length, (width if side == "positive_y" else -width)
