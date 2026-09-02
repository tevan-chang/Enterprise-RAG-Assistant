import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routers import documents
from app.services.zombie_cleanup import cleanup_zombie_tasks

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    zombie_count = cleanup_zombie_tasks()
    if zombie_count:
        logger.warning("啟動 Zombie Task Health Check：共標記 %d 筆 failed", zombie_count)
    yield


app = FastAPI(title="Enterprise AI Knowledge & Report Assistant API", lifespan=lifespan)
app.include_router(documents.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
