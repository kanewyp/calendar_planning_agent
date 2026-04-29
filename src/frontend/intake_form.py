# =============================================================================
# src/frontend/intake_form.py — User intake form
# =============================================================================
# Collects five fields from the user and returns them as a structured dict.
#
# STEPS TO COMPLETE:
# 1. Build the Streamlit form with the five fields listed below.
# 2. On submit, validate that required fields are present.
# 3. Package the fields into the UserInputs dict and return it.
# =============================================================================

from __future__ import annotations

import datetime
from typing import TypedDict

import streamlit as st


class UserInputs(TypedDict):
    """Structured dictionary returned by the intake form."""
    goal: str                       # Free-text goal description
    deadline: datetime.date         # Target completion date
    context: str                    # Optional background context
    work_start: datetime.time       # Preferred working hours — start
    work_end: datetime.time         # Preferred working hours — end
    max_session_minutes: int        # Maximum single-session length


def render_intake_form() -> UserInputs | None:
    """Render the intake form and return user inputs on submission.

    Returns None if the form has not been submitted yet.

    STEPS:
    1. Use st.form("intake_form") to group all fields together.
    2. Inside the form:
       a. st.text_input for the goal (required).
       b. st.date_input for the deadline, default = today + 14 days.
       c. st.text_area for background context (optional).
       d. Two st.time_input widgets for work_start and work_end.
          Default to 09:00 and 18:00.
       e. st.number_input for max_session_minutes,
          min=15, max=240, default=90, step=15.
       f. st.form_submit_button("Plan my schedule").
    3. On submit, if goal is empty show st.error and return None.
    4. If work_start >= work_end, show st.error and return None.
    5. If deadline <= today, show st.error and return None.
    6. Otherwise, construct and return a UserInputs dict.
    """
    today = datetime.date.today()
    default_deadline = today + datetime.timedelta(days=14)

    with st.form("intake_form"):
        goal = st.text_input(
            "What do you want to accomplish?",
            placeholder="e.g. Learn the basics of React",
        )
        deadline = st.date_input(
            "Deadline",
            value=default_deadline,
            min_value=today + datetime.timedelta(days=1),
        )
        context = st.text_area(
            "Background context (optional)",
            placeholder="Any relevant background, constraints, or prior experience…",
        )
        col_start, col_end = st.columns(2)
        with col_start:
            work_start = st.time_input("Work start", value=datetime.time(9, 0))
        with col_end:
            work_end = st.time_input("Work end", value=datetime.time(18, 0))
        max_session_minutes = st.number_input(
            "Max session length (minutes)",
            min_value=15,
            max_value=240,
            value=90,
            step=15,
        )
        submitted = st.form_submit_button("Plan my schedule", type="primary")

    if not submitted:
        return None

    if not goal.strip():
        st.error("Please describe your goal.")
        return None

    if work_start >= work_end:
        st.error("Work start must be earlier than work end.")
        return None

    if deadline <= today:
        st.error("Deadline must be in the future.")
        return None

    return UserInputs(
        goal=goal.strip(),
        deadline=deadline,
        context=context.strip(),
        work_start=work_start,
        work_end=work_end,
        max_session_minutes=int(max_session_minutes),
    )
