from fastapi import Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader
from app.core.config import settings

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key_header: str = Security(API_KEY_HEADER)) -> str:
    """
    Verifies the request's API Key. If APP_ENV is development or dev,
    or if API_KEY is not set or empty, allows bypass.
    """
    if settings.is_development:
        # In dev mode, permit missing or incorrect API keys
        return api_key_header or "dev-bypass"

    if not api_key_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key is missing from X-API-Key header",
        )

    if api_key_header != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API Key",
        )

    return api_key_header
