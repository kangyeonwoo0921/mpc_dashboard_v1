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
