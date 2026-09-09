import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.observability import init_sentry
from app.routers import admin, chat, documents, reports, usage
from app.services.zombie_cleanup import cleanup_zombie_tasks

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

init_sentry()


@asynccontextmanager
async def lifespan(app: FastAPI):
    zombie_count = cleanup_zombie_tasks()
    if zombie_count:
        logger.warning("啟動 Zombie Task Health Check：共標記 %d 筆 failed", zombie_count)
    yield


app = FastAPI(title="Enterprise AI Knowledge & Report Assistant API", lifespan=lifespan)

# 本地開發：前端 Next.js dev server（localhost:3000）呼叫後端需要 CORS 放行。
# 正式環境的 allow_origins 改指向 Vercel 網址（見 spec §16.2，屬 Day 9-10 buffer 範疇）。
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(reports.router)
app.include_router(usage.router)
app.include_router(admin.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
