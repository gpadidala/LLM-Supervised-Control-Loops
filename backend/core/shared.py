"""Shared singleton instances for SCL-Governor.

The governor instance is created once and imported by route modules.
It is initialised lazily the first time ``get_governor()`` is called
(typically at application startup in main.py).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.governor import SCLGovernor

_governor: SCLGovernor | None = None


def init_governor() -> "SCLGovernor":
    """Create and cache the global SCLGovernor singleton."""
    global _governor  # noqa: PLW0603
    if _governor is None:
        from core.governor import SCLGovernor

        _governor = SCLGovernor()
    return _governor


def get_governor() -> "SCLGovernor":
    """Return the global SCLGovernor instance.

    Raises ``RuntimeError`` if ``init_governor()`` has not been called.
    """
    if _governor is None:
        # Auto-initialise for convenience (e.g. during testing)
        return init_governor()
    return _governor
