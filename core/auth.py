"""Password login for the online version. Only active when AUEDGE_PASSWORD is set (Railway variable);
on your own PC (no password set) AuEdge stays open as before.

After a correct password the browser gets a signed cookie for 30 days. Wrong passwords: 5 tries, then a
1-minute wait per address. Icons and the web-app manifest stay public so 'Add to Home Screen' works.
"""
import hashlib
import hmac
import html
import os
import time

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

COOKIE = "auedge_session"
MAX_AGE_S = 30 * 86400
PUBLIC = {"/login", "/icon.svg", "/apple-touch-icon.png", "/icon-192.png", "/icon-512.png", "/manifest.webmanifest"}
_fails: dict[str, list[float]] = {}


def password() -> str:
    return os.getenv("AUEDGE_PASSWORD", "")


def _token() -> str:
    # Changing the password signs everyone out (the token is derived from it).
    key = (os.getenv("AUEDGE_SECRET", "") + "|" + password()).encode()
    return hmac.new(key, b"auedge-login-v1", hashlib.sha256).hexdigest()


def _client(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")     # Railway sits behind a proxy
    # the LAST address is the one the hosting proxy itself saw (earlier ones can be faked by the sender)
    return fwd.split(",")[-1].strip() or (request.client.host if request.client else "?")


def _blocked(ip: str) -> int:
    recent = [t for t in _fails.get(ip, []) if time.time() - t < 60]
    _fails[ip] = recent
    return int(60 - (time.time() - recent[0])) + 1 if len(recent) >= 5 else 0


def page(msg: str = "") -> HTMLResponse:
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>AuEdge · sign in</title>
<link rel="icon" href="/icon.svg"><style>
  :root {{ --bg:#131722; --panel:#1e222d; --line:#2a2e39; --text:#d1d4dc; --muted:#787b86; --accent:#2962ff; --down:#f23645; }}
  @media (prefers-color-scheme: light) {{ :root {{ --bg:#f0f3fa; --panel:#fff; --line:#e0e3eb; --text:#131722; --muted:#6a6d78; }} }}
  body {{ margin:0; min-height:100vh; display:grid; place-items:center; background:var(--bg); color:var(--text);
         font:14px/1.5 -apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, sans-serif; padding:16px; box-sizing:border-box; }}
  form {{ width:100%; max-width:340px; background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:26px 24px; }}
  .top {{ display:flex; gap:10px; align-items:center; margin-bottom:18px; }} .top img {{ width:38px; height:38px; }}
  h1 {{ margin:0; font-size:19px; }} .meta {{ color:var(--muted); font-size:12.5px; }}
  input {{ width:100%; box-sizing:border-box; margin:6px 0 14px; padding:10px 12px; font:inherit; color:var(--text);
          background:var(--bg); border:1px solid var(--line); border-radius:6px; }}
  input:focus {{ outline:2px solid var(--accent); border-color:transparent; }}
  button {{ width:100%; padding:10px; border:0; border-radius:6px; background:var(--accent); color:#fff; font:inherit; font-weight:600; cursor:pointer; }}
  .err {{ color:var(--down); margin:-6px 0 12px; font-size:13px; }}
</style></head><body><form method="post" action="/login">
  <div class="top"><img src="/icon.svg" alt=""><div><h1>AuEdge</h1><div class="meta">XAU/USD · gold analysis</div></div></div>
  <label for="pw" class="meta">Password</label>
  <input id="pw" name="password" type="password" autocomplete="current-password" autofocus required>
  {f'<div class="err" role="alert">{html.escape(msg)}</div>' if msg else ''}
  <button type="submit">Sign in</button>
</form></body></html>""", status_code=401 if msg else 200)


async def login(request: Request):
    ip = _client(request)
    wait = _blocked(ip)
    if wait:
        return page(f"Too many tries. Wait {wait} seconds.")
    form = (await request.body()).decode("utf-8", "replace")
    from urllib.parse import parse_qs
    given = (parse_qs(form).get("password") or [""])[0]
    if not password() or not hmac.compare_digest(given.encode(), password().encode()):
        _fails.setdefault(ip, []).append(time.time())
        return page("Wrong password.")
    _fails.pop(ip, None)
    r = RedirectResponse("/", status_code=303)
    r.set_cookie(COOKIE, _token(), max_age=MAX_AGE_S, httponly=True, samesite="lax",
                 secure=request.headers.get("x-forwarded-proto", request.url.scheme) == "https")
    return r


def logout():
    r = RedirectResponse("/login", status_code=303)
    r.delete_cookie(COOKIE)
    return r


def _same_origin(request: Request) -> bool:
    """Browsers send Origin (or at least Referer) with every POST; it must be AuEdge's own address."""
    from urllib.parse import urlsplit
    src = request.headers.get("origin") or request.headers.get("referer")
    if not src:
        return True            # not from a browser page (e.g. curl on this PC); a website's form always sends one
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    return urlsplit(src).netloc == host


async def middleware(request: Request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS") and not _same_origin(request):
        return JSONResponse({"error": "Blocked: this request did not come from AuEdge's own page."}, status_code=403)
    if not password() or request.url.path in PUBLIC:
        return await call_next(request)
    if hmac.compare_digest(request.cookies.get(COOKIE, ""), _token()):
        return await call_next(request)
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": "Signed out. Reload the page and sign in."}, status_code=401)
    return RedirectResponse("/login", status_code=303)
