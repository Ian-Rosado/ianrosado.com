"""
Shared Google OAuth for every Portland Events script.

ONE credential pair serves everything:
    scripts/add-to-calendar/credentials.json   (OAuth client secret)
    scripts/add-to-calendar/token.json         (cached user token)

Unified scopes (Calendar + Sheets) so a fresh sign-in from any one script
produces a token every other script can reuse. If the cached token is missing
a required scope (e.g. it predates this module), the browser consent flow
re-runs automatically — no more "delete token.json and try again".

Usage from a script in scripts/<subdir>/:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from google_auth import get_credentials, get_gspread_client, get_calendar_service

Paths are anchored to THIS file, not the working directory, so scripts no
longer need to be run from inside their own folder for auth to work.
"""

from pathlib import Path

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/spreadsheets",
]

CREDS_DIR = Path(__file__).resolve().parent / "add-to-calendar"
TOKEN_FILE = CREDS_DIR / "token.json"
CLIENT_SECRET_FILE = CREDS_DIR / "credentials.json"


def get_credentials():
    """Return valid user credentials, refreshing or re-running the browser
    consent flow as needed. Raises SystemExit if the client secret is missing."""
    import sys
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        # A token granted with fewer scopes (e.g. sheets-only) silently 403s
        # later — treat it as invalid so the consent flow re-runs now.
        if creds and creds.scopes and not set(SCOPES) <= set(creds.scopes):
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Unattended runs (the scheduled weekly prep) must fail loudly in
            # the log, not block forever on a browser consent nobody will see.
            import os
            if os.environ.get("GOOGLE_AUTH_NONINTERACTIVE"):
                print("ERROR: token needs a browser re-consent but this is a "
                      "non-interactive run. Run any pipeline script manually "
                      "once to re-authenticate.")
                sys.exit(1)
            if not CLIENT_SECRET_FILE.exists():
                print(f"ERROR: OAuth client secret not found at:\n  {CLIENT_SECRET_FILE}\n"
                      "Copy credentials.json into scripts/add-to-calendar/ (see CLAUDE.md).")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())

    return creds


def get_gspread_client():
    """Return an authenticated gspread client."""
    import gspread
    return gspread.authorize(get_credentials())


def get_calendar_service():
    """Return an authenticated Google Calendar v3 service."""
    from googleapiclient.discovery import build
    return build("calendar", "v3", credentials=get_credentials())
