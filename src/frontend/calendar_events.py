# =============================================================================
# src/frontend/calendar_events.py — FullCalendar event builder
# =============================================================================
# Pure transform from AgentState into the event-dict shape consumed by
# streamlit-calendar (FullCalendar). Combines existing busy_blocks with the
# selected heuristic's proposed events so the user can see how the AI plan
# overlays the user's real calendar.
# =============================================================================

from __future__ import annotations

from typing import Any

from src.orchestration.state import AgentState


STRATEGY_STATE_KEYS: dict[str, str] = {
    "deadline_first": "candidate_deadline_first",
    "min_fragmentation": "candidate_min_fragmentation",
    "energy_aware": "candidate_energy_aware",
}

STRATEGY_COLORS: dict[str, str] = {
    "deadline_first": "#1a73e8",
    "min_fragmentation": "#34a853",
    "energy_aware": "#f9ab00",
}

EXISTING_COLOR = "#9aa0a6"
EXISTING_TEXT_COLOR = "#202124"


def build_calendar_events(
    state: AgentState,
    strategy_name: str,
) -> list[dict[str, Any]]:
    """Build the FullCalendar event list for the given heuristic.

    The returned list mixes:
    - "existing" events from `state["busy_blocks"]` rendered in neutral gray
      so the user sees their real calendar load.
    - "proposed" events from the candidate schedule for `strategy_name`,
      colored by strategy so overlap with existing busy time is visible.

    Raises ValueError on an unknown strategy name to fail fast at the call
    site rather than silently rendering an empty calendar.
    """
    if strategy_name not in STRATEGY_STATE_KEYS:
        raise ValueError(
            f"Unknown strategy '{strategy_name}'. "
            f"Expected one of: {sorted(STRATEGY_STATE_KEYS)}"
        )

    events: list[dict[str, Any]] = []

    for block in state.get("busy_blocks", []) or []:
        events.append(
            {
                "title": "Busy",
                "start": block["start"],
                "end": block["end"],
                "backgroundColor": EXISTING_COLOR,
                "borderColor": EXISTING_COLOR,
                "textColor": EXISTING_TEXT_COLOR,
                "extendedProps": {
                    "kind": "existing",
                    "description": "",
                    "strategy": None,
                },
            }
        )

    candidate_key = STRATEGY_STATE_KEYS[strategy_name]
    color = STRATEGY_COLORS[strategy_name]
    for proposed in state.get(candidate_key, []) or []:
        events.append(
            {
                "title": proposed["name"],
                "start": proposed["start"],
                "end": proposed["end"],
                "backgroundColor": color,
                "borderColor": color,
                "textColor": "#ffffff",
                "extendedProps": {
                    "kind": "proposed",
                    "description": proposed.get("description", ""),
                    "strategy": strategy_name,
                },
            }
        )

    return events
