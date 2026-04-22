from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.routes import router as api_router
from app.builder.router import router as builder_router
from app.builder.service import get_builder_service
from app.core.config import settings
from app.core.logging import setup_logging
from app.db.init_db import init_db
from app.services.element_scanner import ElementScannerService


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    await init_db()
    yield
    await get_builder_service().shutdown()
    await ElementScannerService.close_shared_browser()


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.include_router(api_router)
app.include_router(builder_router)

app.mount(
    "/static/frontend/node_modules",
    StaticFiles(directory="frontend/node_modules"),
    name="node_modules",
)
app.mount("/static/frontend", StaticFiles(directory="frontend/public"), name="frontend")
app.mount("/static", StaticFiles(directory=settings.STATIC_DIR), name="static")


@app.get("/")
async def root():
    return FileResponse("frontend/public/index.html")
