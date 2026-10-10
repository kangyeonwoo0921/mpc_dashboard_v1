# mpc_lab — Standalone Greenhouse MPC (cherry tomato)

Recommendation-only MPC prototype for roof vent + diffuse screen + shade screen. The shade screen is
also the night heat-retention screen; there is no separate thermal screen.

Independent of the 3D dashboard: nothing outside `mpc_lab/` is modified or imported
(`docs/PROTECTED_PATHS.md`). No PLC writes, no actuator commands.

Sources (read-only, `../markdown/`):

- `greenhouse_mpc_integrated_design_baseline.md` — technical baseline (physics, references, logic)
- `claude_codex_standalone_mpc_design_prompt.md` — development specification and work order

## Status

| Phase | Content | State |
|---|---|---|
| 2.0 Repository isolation | `docs/PROTECTED_PATHS.md` | done |
| 2.1 Structural specification | `docs/ARCHITECTURE.md`, `docs/CONTROL_LOGIC.md`, `docs/MODEL_ASSUMPTIONS.md`, `docs/SOURCE_RECONCILIATION.md` | done |
| 2.2 Types and configuration | `src/greenhouse_mpc/{provenance,types,config_loader}.py`, `config/*.yaml`, `tests/` | done |
| Prediction-model physics | `src/greenhouse_mpc/physics/`, `config/model_components.yaml`, `docs/EQUATION_INVENTORY.md`, `docs/VARIABLE_NAMING.md`, `docs/VARIABLE_REGISTRY.md`, `docs/UNIT_AUDIT.md` | equation functions done; open questions Q-1..Q-13 |
| Time discretization | `src/greenhouse_mpc/dynamics/`, `docs/TIME_DISCRETIZATION.md` | done (numerical settings still null) |
| Step 1A outside data pipeline | `src/greenhouse_mpc/ingestion/`, `config/outside_data.yaml`, `docs/OUTSIDE_DATA_PIPELINE.md` | done; run `python -m greenhouse_mpc.ingestion.outside_pipeline` |
| Clear-sky reference (forecast step 1) | `src/greenhouse_mpc/solar/`, `config/solar_reference.yaml`, `docs/CLEARSKY_REFERENCE.md` | done; clear-sky index kc done (5-min, sun elevation >= 20 deg, no cap) |
| GHI forecast baselines (step 2) | `src/greenhouse_mpc/forecast/`, `docs/GHI_FORECAST_BASELINE.md` | done: persistence, climatology, convex combination (reference), 5-60 min; run `python -m greenhouse_mpc.forecast.baseline_pipeline` |
| GHI forecast model (step 3) | `src/greenhouse_mpc/forecast/`, `config/ghi_forecast.yaml`, `docs/GHI_FORECAST_MODEL.md` | XGBoost, expanding weekly split; development, checkpoint and final (sealed) runs done: skill vs CC +0.02..+0.07 at 5-15 min, none at 60 min |

**Equation source of truth:** `docs/greenhouse_mpc_final_equation_baseline.md` (Vanthoor 2011 Ch. 8,
Cabrera 2009, psychrometrics). It supersedes the equation content of `MODEL_ASSUMPTIONS.md` and the
humidity-ratio state in `ARCHITECTURE.md` (dynamic states are now `T_air`, `VP_air`).

No optimizer or solver exists yet. Every config value carries provenance; unknown
values are `null` with status `unknown`/`field_required` and the loader rejects anything else.

## Setup and tests

```powershell
# conda env "sfes" (C:\Users\user\anaconda3\envs\sfes)
conda activate sfes
python -m pip install -e .
python -m unittest discover -s tests
```
