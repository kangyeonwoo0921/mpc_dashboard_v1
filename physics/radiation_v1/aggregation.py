"""Area-weighted crop-zone statistics (spec section 22).

I_eff = sum(I_j * A_j) / sum(A_j); statistics are None while any cell value is missing.
"""

import numpy as np


def area_weighted(values, areas):
    if not values or any(v is None for v in values):
        return {"mean_W_m2": None, "min_W_m2": None, "max_W_m2": None,
                "p10_W_m2": None, "p50_W_m2": None, "p90_W_m2": None}
    v, a = np.asarray(values, float), np.asarray(areas, float)
    order = np.argsort(v)
    cumulative = np.cumsum(a[order]) / a.sum()

    def percentile(q):
        return float(v[order][np.searchsorted(cumulative, q)])

    return {"mean_W_m2": float((v * a).sum() / a.sum()), "min_W_m2": float(v.min()), "max_W_m2": float(v.max()),
            "p10_W_m2": percentile(0.10), "p50_W_m2": percentile(0.50), "p90_W_m2": percentile(0.90)}


def summarize(results, cells):
    areas = [c.area_m2 for c in cells]
    total_area = sum(areas)
    summary = area_weighted([r.total_W_m2 for r in results], areas)
    summary["sunlit_fraction"] = sum(a for r, a in zip(results, areas) if r.sunlit) / total_area
    summary["missing_cell_fraction"] = sum(a for r, a in zip(results, areas) if r.total_W_m2 is None) / total_area
    for part in ("direct", "diffuse"):
        summary[f"{part}_mean_W_m2"] = area_weighted([getattr(r, f"{part}_W_m2") for r in results], areas)["mean_W_m2"]
    # Direct beam over the cells it could be resolved for (unknown side/end wall optics leave gaps).
    known = [(r.direct_W_m2, a) for r, a in zip(results, areas) if r.direct_W_m2 is not None]
    summary["direct_resolved_fraction"] = sum(a for _, a in known) / total_area
    summary["direct_resolved_mean_W_m2"] = area_weighted([v for v, _ in known], [a for _, a in known])["mean_W_m2"]
    return summary
