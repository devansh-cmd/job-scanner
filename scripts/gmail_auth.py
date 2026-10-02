"""One-time Gmail OAuth on your laptop. Prints the refresh token to store
as the GMAIL_REFRESH_TOKEN GitHub secret.

1. Google Cloud Console: create a project, enable the Gmail API.
2. OAuth consent screen: External, add yourself as a test user.
3. Credentials: create an OAuth client ID of type "Desktop app",
   download it as credentials.json next to this script.
4. pip install google-auth-oauthlib && python scripts/gmail_auth.py
"""
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

flow = InstalledAppFlow.from_client_secrets_file(str(Path(__file__).parent / "credentials.json"), SCOPES)
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
print("\nGMAIL_CLIENT_ID     =", creds.client_id)
print("GMAIL_CLIENT_SECRET =", creds.client_secret)
print("GMAIL_REFRESH_TOKEN =", creds.refresh_token)
print("\nAdd these three as GitHub Actions secrets. Do not commit credentials.json.")
