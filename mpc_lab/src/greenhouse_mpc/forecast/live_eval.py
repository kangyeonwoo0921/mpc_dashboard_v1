"""Live forecast vs observed GHI (read-only report of the live forecast log).

    python -m greenhouse_mpc.forecast.live_eval                  # all days in the live log
    python -m greenhouse_mpc.forecast.live_eval --days 7         # last 7 days
    python -m greenhouse_mpc.forecast.live_eval --start 2026-10-16 --end 2026-10-20 --csv pairs.csv

Matches every logged forecast (``forecast_live/forecasts.parquet``, written by the live runner) with the
observed GHI of its target bin and reports per horizon: samples, days, MAE, RMSE and mean bias of

    used        the forecast the operation actually used (per-horizon policy)
    xgb         the model candidate (xgb_expanding)
    cc          the reference (convex combination)
    persist     smart persistence: kc_input at the issue bin x clear-sky GHI at the target

plus the RMSE skill of ``used`` against persistence and against cc (1 - RMSE / RMSE_ref).
Observed GHI is the sensor 5-min mean where the clear-sky index is valid (sun >= 20 deg), the same
definition the weekly gate uses. Targets not observed yet are left out. Nothing is written except
the optional --csv file.
"""

import argparse
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .config import load_forecast_config
from .operation import KC_FILE, OperationPaths, load_live

METHODS = {"used": "ghi_hat", "xgb": "ghi_hat_xgb_expanding", "cc": "ghi_hat_convex_combination",
           "persist": "ghi_hat_persistence"}


def matched_pairs(live, table):
    """One row per logged forecast with its observed GHI (NaN rows dropped)."""
    if live is None or live.empty:
        return pd.DataFrame()
    observed = table.set_index("timestamp")
    valid = observed.kc_status.eq("valid")
    ghi_obs = observed.ghi.where(valid)
    kc_now = observed.kc_input.where(observed.kc_input_status.eq("valid"))
    pairs = live.copy()
    pairs["ghi_obs"] = ghi_obs.reindex(pd.DatetimeIndex(pairs.target_time)).to_numpy()
    pairs["ghi_hat_persistence"] = (kc_now.reindex(pd.DatetimeIndex(pairs.issue_time)).to_numpy()
                                    * pairs.ghi_clear.to_numpy())
    pairs["horizon_min"] = pairs.h_steps * 5
    pairs["day"] = pd.DatetimeIndex(pairs.target_time).date
    return pairs[pairs.ghi_obs.notna() & pairs.ghi_hat.notna()].reset_index(drop=True)


def _rmse(error):
    return float(np.sqrt(np.mean(np.square(error)))) if len(error) else np.nan


def summary(pairs):
    """Per-horizon metrics table (W/m2); empty when nothing matched yet."""
    rows = []
    for h, group in pairs.groupby("horizon_min"):
        row = {"horizon_min": int(h), "samples": len(group), "days": group.day.nunique(),
               "obs_mean": float(group.ghi_obs.mean())}
        for name, column in METHODS.items():
            if column not in group.columns:
                continue
            ok = group[column].notna()
            error = group.loc[ok, column] - group.loc[ok, "ghi_obs"]
            row[f"mae_{name}"] = float(error.abs().mean()) if ok.any() else np.nan
            row[f"rmse_{name}"] = _rmse(error)
            row[f"bias_{name}"] = float(error.mean()) if ok.any() else np.nan
        for ref in ("persist", "cc"):
            denominator = row.get(f"rmse_{ref}")
            row[f"skill_vs_{ref}"] = (1 - row["rmse_used"] / denominator) if denominator else np.nan
        row["method_used"] = ", ".join(sorted(group.method.dropna().unique()))
        rows.append(row)
    return pd.DataFrame(rows)


def report(table_frame):
    if table_frame.empty:
        return "아직 대조할 예측이 없습니다 (예측 대상 시각의 실측이 아직 없거나, 낮 예측 기록이 없음)."
    lines = ["앞(분)  표본  일수  실측평균 | RMSE: 사용  xgb   cc   지속 | MAE 사용 | 편향 사용 | 기술점수 vs지속  vs cc | 사용 방법"]
    for r in table_frame.itertuples():
        def f(value, width=5, digits=0):
            return f"{value:{width}.{digits}f}" if pd.notna(value) else " " * (width - 1) + "—"
        lines.append(f"{r.horizon_min:5d}  {r.samples:4d}  {r.days:4d}  {f(r.obs_mean, 7)} | "
                     f"{f(r.rmse_used)} {f(r.rmse_xgb)} {f(r.rmse_cc)} {f(r.rmse_persist)} | {f(r.mae_used, 7)} | "
                     f"{f(r.bias_used, 8)} | {f(r.skill_vs_persist, 13, 2)} {f(r.skill_vs_cc, 5, 2)} | {r.method_used}")
    lines.append("단위 W/m² (센서 기준). 편향 = 예측 − 실측 평균(+면 과대 예측). "
                 "기술점수 = 1 − RMSE(사용)/RMSE(기준), 0보다 크면 기준보다 나음.")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="live GHI forecast vs observed (read-only)")
    parser.add_argument("--days", type=int, help="only the last N days (by target day)")
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat, help="inclusive")
    parser.add_argument("--csv", help="also write the matched forecast/observation pairs to this CSV")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    live = load_live(OperationPaths.default())
    pairs = matched_pairs(live, pd.read_parquet(KC_FILE))
    if not pairs.empty:
        days = pd.Series(pairs.day)
        start = args.start or (date.today() - timedelta(days=args.days - 1) if args.days else None)
        if start:
            pairs = pairs[(days >= start).to_numpy()]
        if args.end:
            pairs = pairs[(pd.Series(pairs.day) <= args.end).to_numpy()]
    load_forecast_config()                                   # fails early on a broken config
    print(report(summary(pairs) if not pairs.empty else pd.DataFrame()))
    if not pairs.empty:
        print(f"대조 기간: {min(pairs.day)} ~ {max(pairs.day)}, 예측 발행 {pairs.issue_time.nunique()}회")
    if args.csv and not pairs.empty:
        columns = ["issue_time", "target_time", "horizon_min", "ghi_obs", "ghi_hat", "ghi_hat_xgb_expanding",
                   "ghi_hat_convex_combination", "ghi_hat_persistence", "ghi_clear", "method"]
        pairs[[c for c in columns if c in pairs.columns]].to_csv(args.csv, index=False, encoding="utf-8-sig")
        print(f"대조 표 저장: {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
