"""Built-in alert presets.

Sprint 1 will populate Derivatives presets and Sprint 2 will populate Narrative
presets. For Sprint 0 we expose an empty registry plus the loader signature so
the engine can be wired up end-to-end.
"""

from __future__ import annotations

from radar.alerts.engine import BaseRule


def load_default_rules() -> list[BaseRule]:
    """Return the rules that should run on every poll cycle."""
    return []
