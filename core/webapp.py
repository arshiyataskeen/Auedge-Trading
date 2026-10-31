"""Serves the React app built into static/app at /app/* (the old UI stays at /)."""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse

APP_DIR = Path(__file__).resolve().parent.parent / "static" / "app"
router = APIRouter()

NO_CACHE = {"Cache-Control": "no-cache"}
IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}


@router.get("/app", include_in_schema=False)
def app_root():
    return RedirectResponse("/app/", status_code=307)


@router.get("/app/{path:path}", include_in_schema=False)
def app_files(path: str):
    root = APP_DIR.resolve()
    index = root / "index.html"
    if not index.is_file():
        return PlainTextResponse("The new app is not built yet (cd web && npm run build)", status_code=404)
    if path:
        target = (root / path).resolve()
        if target.is_file() and target.is_relative_to(root):
            return FileResponse(target, headers=IMMUTABLE if target.relative_to(root).parts[0] == "assets" else NO_CACHE)
    return FileResponse(index, headers=NO_CACHE)
