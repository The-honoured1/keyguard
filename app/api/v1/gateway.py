from fastapi import APIRouter, Request, Depends
from typing import Dict

router = APIRouter()

@router.get("/me")
async def get_my_key_info(request: Request) -> Dict:
    """
    Echoes back the API key information attached by the middleware.
    """
    key_obj = request.state.api_key
    return {
        "status": "authorized",
        "key_label": key_obj.label,
        "organization_id": str(key_obj.org_id),
        "scopes": key_obj.scopes,
        "rate_limit": key_obj.rate_limit_per_minute
    }

@router.post("/echo")
async def echo_payload(request: Request, payload: Dict) -> Dict:
    """
    A simple echo endpoint for testing throughput/latency.
    """
    return {
        "message": "received",
        "payload": payload,
        "internal_id": str(request.state.api_key.id)
    }
