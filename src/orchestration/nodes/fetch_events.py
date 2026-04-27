# =============================================================================
# src/orchestration/nodes/fetch_events.py — Fetch calendar events node
# =============================================================================
# Graph node that fetches busy blocks from the calendar and computes
# free slots.  Uses mock or live calendar based on CALENDAR_MODE.
#
# READS FROM STATE:  deadline, work_start, work_end
# WRITES TO STATE:   busy_blocks, free_slots
# =============================================================================

from __future__ import annotations

import datetime
from typing import Any

from config.settings import settings
from src.calendar_api.free_slots import compute_free_slots
from src.orchestration.state import AgentState


def fetch_events_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: fetch busy blocks and compute free slots.

    STEPS:
    1. Parse state["deadline"] into a datetime.date.
    2. Determine the time window:
       - time_min = now (timezone-aware UTC or local).
       - time_max = deadline at end of day.
    3. Branch on settings.CALENDAR_MODE:
       a. "mock" → call mock_calendar.fetch_mock_busy_blocks(time_min, time_max).
       b. "live" → call events.fetch_busy_blocks(time_min, time_max).
    4. Parse state["work_start"] and state["work_end"] into datetime.time.
    5. Call free_slots.compute_free_slots(
           busy_blocks, time_min, time_max, work_start, work_end
       ).
    6. Return {"busy_blocks": busy_blocks, "free_slots": free_slots}.
    """
   deadline_raw = state.get("deadline")
   if not isinstance(deadline_raw, str):
      raise ValueError(
         "fetch_events_node: deadline missing or not a string "
         f"(got {type(deadline_raw).__name__})"
      )

   try:
      deadline_date = datetime.date.fromisoformat(deadline_raw)
   except ValueError:
      try:
         deadline_date = datetime.datetime.fromisoformat(deadline_raw).date()
      except ValueError as exc:
         raise ValueError(
            f"fetch_events_node: invalid deadline format {deadline_raw!r}"
         ) from exc

   work_start_raw = state.get("work_start")
   work_end_raw = state.get("work_end")
   if not isinstance(work_start_raw, str) or not isinstance(work_end_raw, str):
      raise ValueError("fetch_events_node: work_start/work_end must be HH:MM strings")

   work_start = datetime.time.fromisoformat(work_start_raw)
   work_end = datetime.time.fromisoformat(work_end_raw)

   tz = datetime.timezone.utc
   time_min = datetime.datetime.now(tz=tz)
   time_max = datetime.datetime.combine(
      deadline_date,
      datetime.time(23, 59, 59, 999999),
      tzinfo=tz,
   )

   if time_max <= time_min:
      raise ValueError(
         "fetch_events_node: deadline is not in the future relative to now"
      )

   if settings.CALENDAR_MODE == "mock":
      from src.calendar_api.mock_calendar import fetch_mock_busy_blocks

      busy_blocks = fetch_mock_busy_blocks(time_min, time_max)
   elif settings.CALENDAR_MODE == "live":
      from src.calendar_api.events import fetch_busy_blocks

      busy_blocks = fetch_busy_blocks(time_min, time_max)
   else:
      raise ValueError(
         f"fetch_events_node: unknown CALENDAR_MODE {settings.CALENDAR_MODE!r}; "
         "expected 'mock' or 'live'"
      )

   free_slots = compute_free_slots(
      busy_blocks=busy_blocks,
      horizon_start=time_min,
      horizon_end=time_max,
      work_start=work_start,
      work_end=work_end,
   )

   return {
      "busy_blocks": busy_blocks,
      "free_slots": free_slots,
   }
