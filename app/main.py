from fastapi import FastAPI

from app.routen import system

app = FastAPI(title="Flashcards", docs_url=None, redoc_url=None, openapi_url=None)

app.include_router(system.router)
