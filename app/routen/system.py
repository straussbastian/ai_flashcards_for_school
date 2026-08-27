from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.templates import rendern

router = APIRouter()


@router.get("/healthz")
async def healthz(session: AsyncSession = Depends(get_session)) -> JSONResponse:
    try:
        await session.scalar(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            {"status": "fehler", "datenbank": "nicht erreichbar"}, status_code=503
        )
    return JSONResponse({"status": "ok", "datenbank": "ok"})


@router.get("/", response_class=HTMLResponse)
async def landeseite(request: Request) -> HTMLResponse:
    return rendern(request, "landeseite.html")
