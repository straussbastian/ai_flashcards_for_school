from fastapi import Depends, FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

app = FastAPI(title="Flashcards", docs_url=None, redoc_url=None, openapi_url=None)

LANDESEITE = """<!doctype html>
<html lang="de">
<head><meta charset="utf-8"><title>Lernkarten</title></head>
<body><p>Diese Seite wird ueber einen Link aufgerufen, den du von deiner Lehrkraft bekommst.</p></body>
</html>"""


@app.get("/healthz")
async def healthz(session: AsyncSession = Depends(get_session)) -> JSONResponse:
    try:
        await session.scalar(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            {"status": "fehler", "datenbank": "nicht erreichbar"}, status_code=503
        )
    return JSONResponse({"status": "ok", "datenbank": "ok"})


@app.get("/", response_class=HTMLResponse)
async def landeseite() -> str:
    return LANDESEITE
