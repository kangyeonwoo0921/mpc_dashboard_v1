"""Local physics-domain contracts; no model execution or field connection."""

from .builder import build_physics_input
from .contracts import PhysicsInput, RadiationOutput, SolarOutput

__all__ = ["PhysicsInput", "RadiationOutput", "SolarOutput", "build_physics_input"]
