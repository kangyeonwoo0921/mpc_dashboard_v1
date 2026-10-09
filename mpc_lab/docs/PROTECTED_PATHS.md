# Protected Paths — Existing 3D Dashboard (read-only for `mpc_lab`)

Phase 2.0 deliverable (design prompt §28, §32). Recorded 2026-10-02 from a read-only inspection.

**Rule:** everything outside `mpc_lab/` belongs to the existing 3D digital-twin dashboard and its
tooling. `mpc_lab` work must not modify, move, rename, delete or import from these paths, and the
dashboard must not import from `mpc_lab`, until a separate integration phase is explicitly requested.

Repository root: `mpc_dashboard_v1/`

| Path | What it is | Status |
|---|---|---|
| `manage.py` | Django entry point | protected |
| `greenhouse_web/` | Django project (settings, URLs, WSGI/ASGI) | protected |
| `digital_twin/` | Django app: viewer template, Three.js modules, CSS, served GLB, API views/URLs | protected |
| `live_data/` | LIVE Growlink-shaped adapter, mock sources, fixture | protected |
| `physics/` | Dashboard physics contracts, reference light models (`light_sample.py`, `light_model.py`), spec-based ray model (`radiation_v1/`), spec documents (`eqations/`) | protected |
| `src/` | Blender greenhouse generator (geometry, config loader, validation) | protected |
| `scripts/` | Blender generation / validation / asset sync scripts | protected |
| `config/` | Greenhouse geometry config + schema, `physics/`, `radiation_v1/` configs | protected |
| `dist/` | Generated `.blend`, `.glb`, generation report | protected |
| `tests/` | Dashboard, generator and physics test suites | protected |
| `markdown/` | Specifications, incl. the two MPC source documents | protected (read-only reference) |
| `reference/` | Construction drawing PDF | protected |
| `tmp/` | Validation renders, light cache, scratch outputs | protected |
| `db.sqlite3` | Django database | protected |
| `requirements.txt` | Dashboard dependency list | protected |
| `README.md` | Dashboard documentation | protected |
| `.venv/`, `.vscode/`, `.gitignore` | Environment / editor / VCS settings | protected |

Also protected (design prompt §28): Django settings, Three.js code, templates, static files,
Blender files, current API routes (`/`, `/api/digital-twin/live/`, `/api/digital-twin/solar/`,
`/api/digital-twin/radiation/v1/`), current tests, current database.

## Read-only facts used by `mpc_lab` design (no code dependency)

These were read, not imported, to document data availability:

- `live_data/fixtures/growlink_live_sample.json` — field data channels currently known (see
  `MODEL_ASSUMPTIONS.md` §6).
- `config/radiation_v1/optical.json`, `config/radiation_v1/site.json` — operator-reported optical
  values and site data already recorded by the dashboard project (see `MODEL_ASSUMPTIONS.md` §5).

## Allowed location for new work

```text
mpc_lab/
```

`mpc_lab` will get its own `requirements.txt` / `pyproject.toml` when implementation starts
(Phase 2.2). It must not edit the root `requirements.txt`.
