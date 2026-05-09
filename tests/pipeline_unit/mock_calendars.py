# =============================================================================
# tests/pipeline_unit/mock_calendars.py — Reusable mock calendar slot scenarios
# =============================================================================
# Each scenario is a dict of named free_slot lists covering a specific
# calendar shape.  Import these directly in test files:
#
#   from tests.pipeline_unit.mock_calendars import CALENDAR_SPARSE, CALENDAR_MORNING_HEAVY
#
# All ISO strings use +00:00 (UTC) to match project conventions.
# All slots are anchored to the week of 2026-05-11 (Monday).
# =============================================================================

from __future__ import annotations

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _slot(start: str, end: str) -> dict[str, str]:
    return {"start": start, "end": end}


# ---------------------------------------------------------------------------
# CALENDAR_SPARSE
# A few scattered slots across a 5-day week.
# Good for: basic scheduling, deadline ordering, overflow checks.
# ---------------------------------------------------------------------------
CALENDAR_SPARSE: list[dict[str, str]] = [
    _slot("2026-05-11T09:00:00+00:00", "2026-05-11T10:30:00+00:00"),   # Mon 90 min
    _slot("2026-05-12T13:00:00+00:00", "2026-05-12T15:00:00+00:00"),   # Tue 120 min
    _slot("2026-05-13T09:30:00+00:00", "2026-05-13T11:00:00+00:00"),   # Wed 90 min
    _slot("2026-05-14T14:00:00+00:00", "2026-05-14T16:30:00+00:00"),   # Thu 150 min
    _slot("2026-05-15T09:00:00+00:00", "2026-05-15T10:00:00+00:00"),   # Fri 60 min
]

# ---------------------------------------------------------------------------
# CALENDAR_MORNING_HEAVY
# Lots of morning capacity, minimal afternoons.
# Good for: energy-aware tests where morning=high energy dominates.
# ---------------------------------------------------------------------------
CALENDAR_MORNING_HEAVY: list[dict[str, str]] = [
    _slot("2026-05-11T09:00:00+00:00", "2026-05-11T12:00:00+00:00"),   # Mon 180 min
    _slot("2026-05-11T14:00:00+00:00", "2026-05-11T14:30:00+00:00"),   # Mon 30 min (small)
    _slot("2026-05-12T09:00:00+00:00", "2026-05-12T12:00:00+00:00"),   # Tue 180 min
    _slot("2026-05-13T09:00:00+00:00", "2026-05-13T11:30:00+00:00"),   # Wed 150 min
    _slot("2026-05-14T09:00:00+00:00", "2026-05-14T12:00:00+00:00"),   # Thu 180 min
    _slot("2026-05-15T09:00:00+00:00", "2026-05-15T12:00:00+00:00"),   # Fri 180 min
]

# ---------------------------------------------------------------------------
# CALENDAR_AFTERNOON_HEAVY
# Mornings busy, big afternoon blocks available.
# Good for: energy-aware tests with custom afternoon=high energy.
# ---------------------------------------------------------------------------
CALENDAR_AFTERNOON_HEAVY: list[dict[str, str]] = [
    _slot("2026-05-11T09:00:00+00:00", "2026-05-11T09:30:00+00:00"),   # Mon 30 min (small)
    _slot("2026-05-11T13:00:00+00:00", "2026-05-11T17:00:00+00:00"),   # Mon 240 min
    _slot("2026-05-12T13:00:00+00:00", "2026-05-12T17:00:00+00:00"),   # Tue 240 min
    _slot("2026-05-13T13:00:00+00:00", "2026-05-13T17:00:00+00:00"),   # Wed 240 min
    _slot("2026-05-14T13:00:00+00:00", "2026-05-14T17:00:00+00:00"),   # Thu 240 min
]

# ---------------------------------------------------------------------------
# CALENDAR_SINGLE_DAY
# All free time on a single Monday — no multi-day spread.
# Good for: testing within-day slot selection (fragmentation, energy).
# ---------------------------------------------------------------------------
CALENDAR_SINGLE_DAY: list[dict[str, str]] = [
    _slot("2026-05-11T09:00:00+00:00", "2026-05-11T09:45:00+00:00"),   # 45 min (small)
    _slot("2026-05-11T10:00:00+00:00", "2026-05-11T11:30:00+00:00"),   # 90 min (medium)
    _slot("2026-05-11T13:00:00+00:00", "2026-05-11T17:00:00+00:00"),   # 240 min (large)
]

# ---------------------------------------------------------------------------
# CALENDAR_MULTI_DAY_EQUAL
# Identical slots on every day — useful for verifying day-ordering behaviour.
# ---------------------------------------------------------------------------
CALENDAR_MULTI_DAY_EQUAL: list[dict[str, str]] = [
    _slot("2026-05-11T09:00:00+00:00", "2026-05-11T11:00:00+00:00"),   # Mon 120 min
    _slot("2026-05-12T09:00:00+00:00", "2026-05-12T11:00:00+00:00"),   # Tue 120 min
    _slot("2026-05-13T09:00:00+00:00", "2026-05-13T11:00:00+00:00"),   # Wed 120 min
    _slot("2026-05-14T09:00:00+00:00", "2026-05-14T11:00:00+00:00"),   # Thu 120 min
    _slot("2026-05-15T09:00:00+00:00", "2026-05-15T11:00:00+00:00"),   # Fri 120 min
]

# ---------------------------------------------------------------------------
# CALENDAR_WITH_EVENING
# Includes evening slots — used for low-energy evening tasks.
# Energy profile: morning=high, afternoon=medium, evening=low.
# ---------------------------------------------------------------------------
CALENDAR_WITH_EVENING: list[dict[str, str]] = [
    _slot("2026-05-11T09:00:00+00:00", "2026-05-11T10:00:00+00:00"),   # Mon morning
    _slot("2026-05-11T13:00:00+00:00", "2026-05-11T14:00:00+00:00"),   # Mon afternoon
    _slot("2026-05-11T18:00:00+00:00", "2026-05-11T19:00:00+00:00"),   # Mon evening
    _slot("2026-05-12T09:00:00+00:00", "2026-05-12T10:00:00+00:00"),   # Tue morning
    _slot("2026-05-12T13:00:00+00:00", "2026-05-12T14:00:00+00:00"),   # Tue afternoon
    _slot("2026-05-12T18:00:00+00:00", "2026-05-12T19:00:00+00:00"),   # Tue evening
]

# ---------------------------------------------------------------------------
# CALENDAR_TWO_SLOTS_SAME_DAY_SMALL_LARGE
# Key layout used in multiple fragmentation tests:
#   - A small slot early (09:00–09:45, 45min)
#   - A large slot afternoon (13:00–17:00, 240min)
# Structural mode → min_fragmentation picks the large one.
# Fallback mode  → deadline_first picks the small one first.
# ---------------------------------------------------------------------------
CALENDAR_TWO_SLOTS_SAME_DAY: list[dict[str, str]] = [
    _slot("2026-05-11T09:00:00+00:00", "2026-05-11T09:45:00+00:00"),   # 45 min (small)
    _slot("2026-05-11T13:00:00+00:00", "2026-05-11T17:00:00+00:00"),   # 240 min (large)
]

# ---------------------------------------------------------------------------
# CALENDAR_ONE_BIG_SLOT
# A single large block (9 hours) to simplify ordering assertions.
# ---------------------------------------------------------------------------
CALENDAR_ONE_BIG_SLOT: list[dict[str, str]] = [
    _slot("2026-05-11T09:00:00+00:00", "2026-05-11T18:00:00+00:00"),   # 540 min
]
