"""Phase 1.7 local LIVE data boundary.

Only mock sources are available in this phase.  Source-specific field names stay
inside :mod:`live_data.adapter`.
"""

from .sources import get_live_snapshot

__all__ = ["get_live_snapshot"]
