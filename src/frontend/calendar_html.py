# =============================================================================
# src/frontend/calendar_html.py — FullCalendar HTML/JS template builder
# =============================================================================
# Returns a self-contained HTML document that renders a Google-Calendar-like
# month / week / day view via FullCalendar 6 (loaded from a CDN). The document
# is consumed by Streamlit's `components.v1.html(...)` so we get full CSS
# control and the standard FullCalendar UX without going through the
# `streamlit-calendar` wrapper layer.
#
# The page is read-only: events render with hover tooltips and a click popover,
# but the user cannot drag, resize, or create events here. Final scheduling is
# committed by approving the heuristic in the surrounding Streamlit shell.
# =============================================================================

from __future__ import annotations

import datetime
import json
from typing import Any


FULLCALENDAR_CDN = "https://cdn.jsdelivr.net/npm/fullcalendar@6.1.11/index.global.min.js"


_GOOGLE_CSS = """
:root {
  --gc-bg: #ffffff;
  --gc-text: #3c4043;
  --gc-text-muted: #5f6368;
  --gc-border: #dadce0;
  --gc-hover: #f1f3f4;
  --gc-today-bg: #e8f0fe;
  --gc-accent: #1a73e8;
  --gc-weekend-bg: #fafafa;
}
* { box-sizing: border-box; }
html, body {
  margin: 0;
  padding: 0;
  background: var(--gc-bg);
  color: var(--gc-text);
  font-family: 'Google Sans', 'Roboto', -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
  font-size: 14px;
  -webkit-font-smoothing: antialiased;
}
#cal {
  padding: 8px 12px 16px;
}
/* Toolbar */
.fc .fc-toolbar.fc-header-toolbar {
  margin-bottom: 12px;
  padding: 6px 0;
}
.fc .fc-toolbar-title {
  font-family: 'Google Sans', 'Roboto', sans-serif;
  font-size: 22px;
  font-weight: 400;
  color: var(--gc-text);
}
.fc .fc-button {
  background: transparent;
  color: var(--gc-text);
  border: 1px solid var(--gc-border);
  border-radius: 18px;
  padding: 4px 14px;
  font-weight: 500;
  font-size: 13px;
  text-transform: none;
  box-shadow: none;
  transition: background 120ms ease;
}
.fc .fc-button:hover {
  background: var(--gc-hover);
  border-color: var(--gc-border);
  color: var(--gc-text);
}
.fc .fc-button-primary:not(:disabled).fc-button-active,
.fc .fc-button-primary:not(:disabled):active {
  background: var(--gc-today-bg);
  color: var(--gc-accent);
  border-color: var(--gc-accent);
  box-shadow: none;
}
.fc .fc-button-primary:focus { box-shadow: none; }
.fc .fc-prev-button, .fc .fc-next-button {
  border-radius: 50%;
  width: 32px; height: 32px;
  padding: 0;
  border-color: transparent;
}
.fc .fc-prev-button:hover, .fc .fc-next-button:hover {
  background: var(--gc-hover);
}
.fc .fc-today-button {
  margin-right: 8px;
}
/* Day cell */
.fc-theme-standard td, .fc-theme-standard th, .fc-theme-standard .fc-scrollgrid {
  border-color: var(--gc-border);
}
.fc .fc-col-header-cell {
  background: var(--gc-bg);
  padding: 6px 0;
}
.fc .fc-col-header-cell-cushion {
  color: var(--gc-text-muted);
  font-weight: 500;
  font-size: 11px;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  padding: 6px 4px;
}
.fc-day-sat, .fc-day-sun { background: var(--gc-weekend-bg); }
.fc .fc-daygrid-day-number {
  color: var(--gc-text);
  font-size: 12px;
  padding: 6px 8px 2px;
  text-decoration: none;
}
.fc .fc-day-other .fc-daygrid-day-number { color: #bdc1c6; }
/* Today emphasis (small blue circle around the date number) */
.fc .fc-day-today { background: transparent !important; }
.fc .fc-day-today .fc-daygrid-day-number {
  background: var(--gc-accent);
  color: #fff;
  border-radius: 50%;
  display: inline-block;
  width: 24px; height: 24px;
  line-height: 24px;
  text-align: center;
  margin: 4px 0 0 4px;
  padding: 0;
  font-weight: 500;
}
/* Events */
.fc-h-event, .fc-v-event {
  border-radius: 4px;
  border: none;
  font-size: 12px;
  padding: 1px 6px;
  font-weight: 500;
  cursor: pointer;
  transition: filter 120ms ease;
}
.fc-h-event:hover, .fc-v-event:hover { filter: brightness(0.95); }
.fc-event-title { font-weight: 500; }
.fc-event-time { font-weight: 400; opacity: 0.9; margin-right: 4px; }
.fc-daygrid-event { margin: 1px 4px; }
.fc-daygrid-day-events { margin-top: 2px; }
.fc .fc-more-link {
  color: var(--gc-text-muted);
  font-size: 11px;
  font-weight: 500;
  padding: 0 6px;
}
.fc .fc-more-link:hover { color: var(--gc-accent); background: var(--gc-hover); border-radius: 3px; }
/* Time grid */
.fc .fc-timegrid-slot {
  height: 32px;
  border-color: var(--gc-border);
}
.fc .fc-timegrid-slot-label-cushion {
  color: var(--gc-text-muted);
  font-size: 10px;
}
.fc .fc-timegrid-now-indicator-line { border-color: #ea4335; border-width: 1px; }
.fc .fc-timegrid-now-indicator-arrow { border-color: #ea4335; }
/* Popover (more-link / event detail popover) */
.fc .fc-popover {
  border: 1px solid var(--gc-border);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(60, 64, 67, 0.15);
}
.fc .fc-popover-header {
  background: var(--gc-bg);
  color: var(--gc-text);
  font-weight: 500;
  padding: 10px 12px;
  border-bottom: 1px solid var(--gc-border);
}
.fc .fc-popover-body { padding: 8px 12px; }
/* Event detail card injected via eventClick */
.gc-event-card {
  position: fixed;
  z-index: 9999;
  min-width: 280px;
  max-width: 360px;
  background: #fff;
  border: 1px solid var(--gc-border);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(60, 64, 67, 0.20);
  padding: 14px 16px;
  font-size: 13px;
  color: var(--gc-text);
  pointer-events: auto;
}
.gc-event-card .gc-card-title {
  font-size: 16px;
  font-weight: 500;
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.gc-event-card .gc-card-dot {
  width: 12px; height: 12px;
  border-radius: 50%;
  flex-shrink: 0;
}
.gc-event-card .gc-card-row {
  margin: 4px 0;
  color: var(--gc-text-muted);
  font-size: 12px;
}
.gc-event-card .gc-card-row strong {
  color: var(--gc-text);
  font-weight: 500;
}
.gc-event-card .gc-card-close {
  position: absolute;
  top: 6px; right: 8px;
  background: transparent;
  border: none;
  font-size: 18px;
  color: var(--gc-text-muted);
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
}
.gc-event-card .gc-card-close:hover { background: var(--gc-hover); }
.gc-event-card .gc-card-description {
  margin-top: 8px;
  color: var(--gc-text);
  font-size: 13px;
  line-height: 1.4;
}
.gc-card-overlay {
  position: fixed; inset: 0;
  z-index: 9998;
  background: transparent;
}
"""


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Google+Sans:wght@400;500;600&family=Roboto:wght@400;500&display=swap" rel="stylesheet">
<script src="__FULLCALENDAR_CDN__"></script>
<style>__GOOGLE_CSS__</style>
</head>
<body>
<div id="cal"></div>
<script>
(function() {
  var EVENTS = __EVENTS_JSON__;
  var INITIAL_DATE = "__INITIAL_DATE__";
  var INITIAL_VIEW = "__INITIAL_VIEW__";
  var SLOT_MIN = "__SLOT_MIN__";
  var SLOT_MAX = "__SLOT_MAX__";

  function fmtTimeRange(start, end) {
    if (!start) return "";
    var s = new Date(start);
    var opts = { hour: 'numeric', minute: '2-digit', timeZone: 'UTC' };
    var startStr = s.toLocaleTimeString([], opts);
    if (!end) return startStr;
    var e = new Date(end);
    return startStr + " – " + e.toLocaleTimeString([], opts);
  }

  function fmtDate(d) {
    if (!d) return "";
    return new Date(d).toLocaleDateString([], {
      weekday: 'long', month: 'long', day: 'numeric', timeZone: 'UTC'
    });
  }

  function escapeHtml(s) {
    if (s === null || s === undefined) return "";
    return String(s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function clearCard() {
    var existing = document.querySelector('.gc-event-card');
    var overlay = document.querySelector('.gc-card-overlay');
    if (existing) existing.remove();
    if (overlay) overlay.remove();
  }

  function showEventCard(info) {
    clearCard();
    var ev = info.event;
    var props = ev.extendedProps || {};
    var color = ev.backgroundColor || '#1a73e8';
    var kindLabel = props.kind === 'existing' ? 'Existing event' : 'AI proposal';
    var strategyLabel = props.strategy ? ('Strategy: ' + props.strategy.replace(/_/g, ' ')) : '';

    var overlay = document.createElement('div');
    overlay.className = 'gc-card-overlay';
    overlay.addEventListener('click', clearCard);
    document.body.appendChild(overlay);

    var card = document.createElement('div');
    card.className = 'gc-event-card';
    card.innerHTML = (
      '<button class="gc-card-close" aria-label="Close">&times;</button>'
      + '<div class="gc-card-title">'
      + '<span class="gc-card-dot" style="background:' + escapeHtml(color) + '"></span>'
      + escapeHtml(ev.title || 'Untitled')
      + '</div>'
      + '<div class="gc-card-row">' + escapeHtml(fmtDate(ev.start)) + '</div>'
      + '<div class="gc-card-row">' + escapeHtml(fmtTimeRange(ev.start, ev.end)) + '</div>'
      + '<div class="gc-card-row"><strong>' + escapeHtml(kindLabel) + '</strong></div>'
      + (strategyLabel ? '<div class="gc-card-row">' + escapeHtml(strategyLabel) + '</div>' : '')
      + (props.description ? '<div class="gc-card-description">' + escapeHtml(props.description) + '</div>' : '')
    );

    var rect = info.el.getBoundingClientRect();
    var topPx = Math.max(8, rect.top - 8);
    var leftPx = Math.min(window.innerWidth - 380, rect.right + 12);
    if (leftPx < 8) leftPx = 8;
    card.style.top = topPx + 'px';
    card.style.left = leftPx + 'px';
    document.body.appendChild(card);

    card.querySelector('.gc-card-close').addEventListener('click', clearCard);
    document.addEventListener('keydown', function escListener(e) {
      if (e.key === 'Escape') {
        clearCard();
        document.removeEventListener('keydown', escListener);
      }
    });
  }

  document.addEventListener('DOMContentLoaded', function() {
    var calEl = document.getElementById('cal');
    var calendar = new FullCalendar.Calendar(calEl, {
      timeZone: 'UTC',
      initialView: INITIAL_VIEW,
      initialDate: INITIAL_DATE,
      headerToolbar: {
        left: 'prev,next today',
        center: 'title',
        right: 'dayGridMonth,timeGridWeek,timeGridDay'
      },
      buttonText: { today: 'Today', month: 'Month', week: 'Week', day: 'Day' },
      events: EVENTS,
      editable: false,
      selectable: false,
      height: 'auto',
      contentHeight: 'auto',
      expandRows: true,
      navLinks: true,
      nowIndicator: true,
      weekNumbers: false,
      firstDay: 0,
      dayMaxEvents: 3,
      slotMinTime: SLOT_MIN,
      slotMaxTime: SLOT_MAX,
      slotDuration: '00:30:00',
      allDaySlot: false,
      moreLinkText: function(n) { return '+' + n + ' more'; },
      eventTimeFormat: { hour: 'numeric', minute: '2-digit', meridiem: 'short' },
      eventDisplay: 'block',
      eventDidMount: function(info) {
        var props = info.event.extendedProps || {};
        var lines = [info.event.title || ''];
        if (props.description) lines.push(props.description);
        info.el.setAttribute('title', lines.filter(Boolean).join('\\n'));
      },
      eventClick: function(info) {
        info.jsEvent.preventDefault();
        showEventCard(info);
      },
      datesSet: clearCard,
    });
    calendar.render();
  });
})();
</script>
</body>
</html>
"""


def _initial_calendar_date(
    events: list[dict[str, Any]],
    fallback_iso: str | None,
) -> str:
    """Pick a sensible focus date for the calendar's initial render."""
    proposed = [e for e in events if (e.get("extendedProps") or {}).get("kind") == "proposed"]
    candidate_pool = proposed or events
    if candidate_pool:
        first_start = candidate_pool[0].get("start", "")
        if first_start:
            return first_start[:10]

    if fallback_iso:
        return str(fallback_iso)[:10]

    return datetime.date.today().isoformat()


def build_calendar_html(
    events: list[dict[str, Any]],
    *,
    initial_date: str | None = None,
    initial_view: str = "dayGridMonth",
    work_start: str = "08:00",
    work_end: str = "20:00",
    fallback_date_iso: str | None = None,
) -> str:
    """Render the full self-contained HTML document for the calendar iframe.

    Args:
        events: FullCalendar event dicts (already built by `calendar_events`).
        initial_date: YYYY-MM-DD string. If None, derived from events or
            `fallback_date_iso`.
        initial_view: One of "dayGridMonth", "timeGridWeek", "timeGridDay".
        work_start, work_end: "HH:MM" strings used as time-grid bounds.
        fallback_date_iso: Used when events is empty and no `initial_date`
            is provided.
    """
    resolved_date = initial_date or _initial_calendar_date(events, fallback_date_iso)
    # Escape forward slashes in the JSON payload so a "</script>" substring
    # inside an event title or description cannot terminate the host script
    # tag. JSON parsers treat the escaped form as identical content.
    events_payload = json.dumps(events).replace("</", "<\\/")
    return (
        _HTML_TEMPLATE
        .replace("__FULLCALENDAR_CDN__", FULLCALENDAR_CDN)
        .replace("__GOOGLE_CSS__", _GOOGLE_CSS)
        .replace("__EVENTS_JSON__", events_payload)
        .replace("__INITIAL_DATE__", resolved_date)
        .replace("__INITIAL_VIEW__", initial_view)
        .replace("__SLOT_MIN__", str(work_start))
        .replace("__SLOT_MAX__", str(work_end))
    )
