from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routen import lernseite, system
from app.templates import VERZEICHNIS

app = FastAPI(title="Flashcards", docs_url=None, redoc_url=None, openapi_url=None)

app.mount("/static", StaticFiles(directory=str(VERZEICHNIS.parent / "static")), name="static")

app.include_router(system.router)
# Muss als letzter kommen: /{slug} ist zwar durch ein Muster begrenzt, aber
# eine spaetere Route mit gleicher Form wuerde sonst verdeckt.
app.include_router(lernseite.router)
