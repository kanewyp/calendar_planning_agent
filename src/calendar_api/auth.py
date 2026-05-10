# =============================================================================
# src/calendar_api/auth.py — Google Calendar OAuth 2.0 authentication
# =============================================================================
# Handles the OAuth consent flow so the user authenticates once per Streamlit
# session.  The resulting credentials object is stored in st.session_state
# and reused for all subsequent Calendar API calls.
#
# PREREQUISITE:
#   - A Google Cloud project with the Calendar API enabled.
#   - An OAuth 2.0 Client ID (Desktop or Web) downloaded as credentials.json.
#
# STEPS TO COMPLETE:
# 1. Implement get_credentials() following the inline guide below.
# 2. Implement build_calendar_service() to return an authorised service object.
# =============================================================================

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config.settings import settings

if TYPE_CHECKING:
    from googleapiclient.discovery import Resource

# OAuth scopes — read events + create events (NO delete/update)
SCOPES: list[str] = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]

# Path where the refresh token is cached between runs
_TOKEN_PATH = "token.json"


def get_credentials() -> Credentials:
    """Return valid Google OAuth credentials, prompting the user if needed.

    STEPS:
    1. Check if a token file (_TOKEN_PATH) exists on disk.
       a. If it does, load it with Credentials.from_authorized_user_file().
       b. If the token is expired but has a refresh token, refresh it using
          creds.refresh(google.auth.transport.requests.Request()).
       c. If refresh succeeds, save the refreshed token back to disk and return.
    2. If no valid token exists, start the OAuth consent flow:
       a. Create an InstalledAppFlow from the client secret file
          (settings.GOOGLE_CLIENT_SECRET_FILE) and SCOPES.
       b. Call flow.run_local_server(port=0) to open the browser consent page.
       c. Save the resulting credentials to _TOKEN_PATH for future runs.
    3. Return the Credentials object.

    SECURITY NOTES:
    - Never log or print the access/refresh tokens.
    - token.json is in .gitignore — ensure it stays that way.
    """
    token_path = Path(_TOKEN_PATH)
    creds: Credentials | None = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            settings.GOOGLE_CLIENT_SECRET_FILE, SCOPES
        )
        creds = flow.run_local_server(port=0)

    token_path.write_text(creds.to_json())
    return creds


def build_calendar_service() -> "Resource":
    """Build and return an authorised Google Calendar API service object.

    STEPS:
    1. Call get_credentials() to obtain valid creds.
    2. Return build("calendar", "v3", credentials=creds).
    """
    creds = get_credentials()
    return build("calendar", "v3", credentials=creds)
