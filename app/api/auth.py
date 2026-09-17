from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

from app.config_manager import get_api_keys

_header = APIKeyHeader(name='X-API-Key', auto_error=False)


async def require_api_key(api_key: str = Security(_header)) -> str:
    keys = get_api_keys()
    if not keys:
        return api_key or ''
    if api_key not in keys:
        raise HTTPException(status_code=403, detail="API Key inválida o no proporcionada")
    return api_key
