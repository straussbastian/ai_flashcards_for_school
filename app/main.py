from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="Flashcards", docs_url=None, redoc_url=None, openapi_url=None)

LANDESEITE = """<!doctype html>
<html lang="de">
<head><meta charset="utf-8"><title>Lernkarten</title></head>
<body><p>Diese Seite wird ueber einen Link aufgerufen, den du von deiner Lehrkraft bekommst.</p></body>
</html>"""


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def landeseite() -> str:
    return LANDESEITE
