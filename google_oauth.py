from __future__ import annotations

import json
import logging
import os

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

import crypto

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]

def get_client_config() -> dict:
    """Retrieve Google OAuth client config from environment variable."""
    try:
        config_str = os.environ["GOOGLE_OAUTH_CLIENT_JSON"]
        return json.loads(config_str)
    except KeyError:
        logger.error("GOOGLE_OAUTH_CLIENT_JSON environment variable not set.")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse GOOGLE_OAUTH_CLIENT_JSON: {e}")
        raise

def build_auth_url(telegram_id: int, redirect_uri: str) -> str:
    """Build Google OAuth consent URL.
    - state parameter = encrypted telegram_id
    - redirect_uri = e.g. 'https://your-domain/api/setup/google/callback'
    - access_type='offline' to get refresh_token
    - prompt='consent' to always get refresh_token
    """
    try:
        client_config = get_client_config()
        flow = Flow.from_client_config(
            client_config,
            scopes=SCOPES,
            redirect_uri=redirect_uri
        )
        state_str = str(telegram_id)
        state = crypto.encrypt(state_str)
        
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            prompt='consent',
            state=state,
            include_granted_scopes='true'
        )
        return auth_url
    except Exception as e:
        logger.exception(f"Error building auth URL for telegram_id {telegram_id}: {e}")
        raise

def get_or_create_calendar(service) -> str:
    """Find existing 'TDTU Bot' calendar or create one.
    - List user's calendars
    - If 'TDTU Bot' exists, return its ID
    - Otherwise create new calendar named 'TDTU Bot', timezone Asia/Ho_Chi_Minh
    - Return calendar_id
    """
    try:
        page_token = None
        while True:
            calendar_list = service.calendarList().list(pageToken=page_token).execute()
            for calendar_list_entry in calendar_list.get('items', []):
                if calendar_list_entry['summary'] == 'TDTU Bot':
                    return calendar_list_entry['id']
            page_token = calendar_list.get('nextPageToken')
            if not page_token:
                break
        
        # Create a new calendar
        calendar = {
            'summary': 'TDTU Bot',
            'timeZone': 'Asia/Ho_Chi_Minh'
        }
        created_calendar = service.calendars().insert(body=calendar).execute()
        return created_calendar['id']
    except Exception as e:
        logger.exception(f"Error finding or creating calendar: {e}")
        raise

def exchange_code(code: str, state: str, redirect_uri: str) -> tuple[str, str]:
    """Exchange auth code for tokens.
    - Decrypt state to get telegram_id
    - Exchange code for credentials
    - Returns (refresh_token, calendar_id)
    - Calls get_or_create_calendar() to find/create 'TDTU Bot' calendar
    """
    try:
        telegram_id_str = crypto.decrypt(state)
        telegram_id = int(telegram_id_str)
    except Exception as e:
        logger.exception(f"Error decrypting state parameter: {e}")
        raise ValueError("Invalid state parameter") from e

    try:
        client_config = get_client_config()
        flow = Flow.from_client_config(
            client_config,
            scopes=SCOPES,
            redirect_uri=redirect_uri
        )
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        if not credentials.refresh_token:
            message = (
                "Google không trả refresh token. Hãy xóa quyền của ứng dụng tại "
                "https://myaccount.google.com/permissions rồi thử kết nối lại."
            )
            logger.warning("No refresh token received for telegram_id %s.", telegram_id)
            raise ValueError(message)
            
        service = build('calendar', 'v3', credentials=credentials)
        calendar_id = get_or_create_calendar(service)
        
        return credentials.refresh_token, calendar_id
    except Exception as e:
        logger.exception(f"Error exchanging code for telegram_id {telegram_id}: {e}")
        raise

def get_calendar_service(encrypted_refresh_token: str):
    """Build Google Calendar API service from encrypted refresh token.
    - Decrypt refresh_token using crypto.decrypt
    - Build credentials with google.oauth2.credentials.Credentials
    - Return googleapiclient.discovery.Resource
    """
    try:
        refresh_token = crypto.decrypt(encrypted_refresh_token)
        client_config = get_client_config()
        
        client_id = client_config.get("web", {}).get("client_id") or client_config.get("installed", {}).get("client_id")
        client_secret = client_config.get("web", {}).get("client_secret") or client_config.get("installed", {}).get("client_secret")
        token_uri = client_config.get("web", {}).get("token_uri") or client_config.get("installed", {}).get("token_uri")
        
        credentials = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri=token_uri,
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES
        )
        
        service = build('calendar', 'v3', credentials=credentials)
        return service
    except Exception as e:
        logger.exception("Error building calendar service from encrypted refresh token")
        raise
