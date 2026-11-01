"""GET /api/agents/separation: read-only agent signal separation (see core.agent_separation)."""
import time

from fastapi import APIRouter

from core import agent_separation

router = APIRouter()
_cache: dict = {}
TTL = 900


def load_rows():
    return agent_separation.load_rows()


@router.get("/api/agents/separation")
def separation():
    hit = _cache.get("v")
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    try:
        rows, source = load_rows()
        res = agent_separation.separation(rows, source=source)
    except Exception:       # missing dataset.db / table: show nothing, never a 500, never cache the failure
        return []
    if res:
        _cache["v"] = (time.time(), res)
    return res
