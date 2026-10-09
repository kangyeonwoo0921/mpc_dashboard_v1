"""Load mpc_lab/config/*.yaml into provenance-checked ``Parameter`` trees (DP Phase 2.2)."""

from pathlib import Path

import yaml

from .provenance import Parameter, ProvenanceError, iter_parameters, parse_parameters
from .types import MPCConfig

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
CONFIG_FILES = ("crop_reference", "controller", "greenhouse", "actuators", "safety")


def load_config_file(name, config_dir=CONFIG_DIR):
    path = Path(config_dir) / f"{name}.yaml"
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise ProvenanceError(f"{path}: top level must be a mapping")
    return parse_parameters(raw, name)


def load_all(config_dir=CONFIG_DIR):
    return {name: load_config_file(name, config_dir) for name in CONFIG_FILES}


def build_mpc_config(controller):
    """MPCConfig from the parsed controller tree; null weights stay None (optimizer must not run)."""
    horizons = controller["horizons"]
    for name, param in horizons.items():
        if not param.known:
            raise ProvenanceError(f"controller.horizons.{name}: value required")
    return MPCConfig(
        sampling_minutes=horizons["sampling_minutes"].value,
        prediction_horizon_minutes=horizons["prediction_horizon_minutes"].value,
        control_horizon_minutes=horizons["control_horizon_minutes"].value,
        weights={name: param.value for name, param in controller["weights"].items()},
        enable_diffuse_screen_control=controller["enable_diffuse_screen_control"].value,
        solver={name: param.value for name, param in controller.get("solver", {}).items()},
    )


def build_integrator_settings(controller):
    """IntegratorSettings from controller.numerical_integration; null tolerances/substeps stay None, so
    IntegratorSettings raises MissingParameterError until they are configured."""
    from .dynamics.integrators import IntegratorSettings
    node = controller["numerical_integration"]
    return IntegratorSettings(method=node["method"].value, rtol=node["rtol"].value,
                              atol_T_air=node["atol_T_air"].value, atol_VP_air=node["atol_VP_air"].value,
                              n_substeps=node["rk4_n_substeps"].value)


def unresolved(tree):
    """Parameters still without a value (status unknown / field_required), by dotted path."""
    return sorted(p.path for p in iter_parameters(tree) if not p.known)


def status_summary(tree):
    counts = {}
    for param in iter_parameters(tree):
        counts[param.status] = counts.get(param.status, 0) + 1
    return counts


__all__ = ["CONFIG_DIR", "CONFIG_FILES", "Parameter", "build_integrator_settings", "build_mpc_config", "load_all",
           "load_config_file", "status_summary", "unresolved"]
