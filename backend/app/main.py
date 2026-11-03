import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from . import errors
from .config import settings
from .db import lifespan, pool
from .routers import accounts, activities, auth, deals, geohub_link, home, invoices, staff

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="GeoEstate CRM API", version="1.0.0", lifespan=lifespan,
              docs_url=f"{settings.api_prefix}/docs", openapi_url=f"{settings.api_prefix}/openapi.json")
errors.install(app)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
                   allow_methods=["*"], allow_headers=["*"])
P = settings.api_prefix

for r in (auth.router, auth.me_router, staff.router, accounts.router, deals.router, activities.router, home.router, invoices.router,
          geohub_link.router):
    app.include_router(r, prefix=P)


@app.get(f"{P}/health", include_in_schema=False)
async def health():
    try:
        async with pool.connection() as c:
            await c.execute("SELECT 1")
        return {"ok": True}
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False}, status_code=503)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


# ---- the built web app, served from the same service ----
if settings.web_dir:
    _web = Path(settings.web_dir).resolve()
    _FOREVER = {"Cache-Control": "public, max-age=31536000, immutable"}
    _REVALIDATE = {"Cache-Control": "no-cache"}

    @app.get("/{full_path:path}", include_in_schema=False)
    async def web_app(full_path: str):
        if P and ("/" + full_path).startswith(P + "/"):
            raise HTTPException(404)
        f = (_web / full_path).resolve()
        if full_path and f.is_file() and _web in f.parents:
            return FileResponse(f, headers=_FOREVER if full_path.startswith("assets/") else _REVALIDATE)
        if full_path.startswith("assets/"):
            raise HTTPException(404)
        return FileResponse(_web / "index.html", headers=_REVALIDATE)
