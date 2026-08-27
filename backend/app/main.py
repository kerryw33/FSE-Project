from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.database import Base, engine
from app.models import *  # noqa: F401,F403 - ensure all models are registered before create_all


@asynccontextmanager
async def lifespan(app: FastAPI):
    # KISS for the MVP slice: create_all against SQLite. A real migration
    # tool (Alembic) should replace this once the schema stabilises.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="XRPL FX Remittance Platform", version="0.1.0", lifespan=lifespan)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}


app.include_router(api_router)
