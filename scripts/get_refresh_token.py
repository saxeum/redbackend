from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
# prompt="consent" makes Google return a refresh token every time.
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

# These are the mailbox credentials, not the sign-in client: the backend reads
# GMAIL_* so the two OAuth clients cannot be confused with each other.
assert creds.refresh_token, "no refresh token returned; re-run with prompt=consent"
print(f"GMAIL_CLIENT_ID={creds.client_id}")
print(f"GMAIL_CLIENT_SECRET={creds.client_secret}")
print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")
