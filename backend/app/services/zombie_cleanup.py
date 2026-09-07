import logging

import sentry_sdk

from app.config import settings
from app.repositories.documents_repository import DocumentsRepository

logger = logging.getLogger(__name__)


def cleanup_zombie_tasks() -> int:
    """FastAPI lifespan 啟動階段跑一次（不是常駐輪詢，見 spec §2.1 / Guardrail #1）。

    找出 processing_status 仍卡在 parsing/chunking/embedding 且 updated_at
    超過門檻的紀錄，代表容器崩潰造成 BackgroundTasks 遺失，直接標記 failed，
    避免前端無限期 Polling。
    """
    repo = DocumentsRepository()
    zombies = repo.find_zombie_tasks(settings.zombie_task_timeout_minutes)
    if not zombies:
        return 0

    repo.mark_failed_bulk([z["id"] for z in zombies])
    for z in zombies:
        logger.warning(
            "Zombie task 標記為 failed: doc_id=%s file_name=%s stale_status=%s updated_at=%s",
            z["id"],
            z["file_name"],
            z["processing_status"],
            z["updated_at"],
        )
        sentry_sdk.capture_message(
            f"Zombie task 標記為 failed: doc_id={z['id']} file_name={z['file_name']} "
            f"stale_status={z['processing_status']} updated_at={z['updated_at']}",
            level="warning",
        )
    return len(zombies)
