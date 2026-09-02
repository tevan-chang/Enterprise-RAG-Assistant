import asyncio
from abc import ABC, abstractmethod

import httpx

from app.config import settings


class FallbackParsingError(Exception):
    pass


class BaseFallbackParser(ABC):
    @abstractmethod
    async def parse(self, file_bytes: bytes, file_name: str) -> str:
        """回傳解析後的純文字/Markdown 內容"""


class LlamaParseAdapter(BaseFallbackParser):
    """pdfplumber 解析異常時的 fallback（見 spec §1 / Guardrail #4）。

    憑證一律讀環境變數 LLAMA_CLOUD_API_KEY，不硬編碼於 repo。
    """

    _BASE_URL = "https://api.cloud.llamaindex.ai/api/v1/parsing"
    _POLL_INTERVAL_SECONDS = 2
    _POLL_TIMEOUT_SECONDS = 60

    async def parse(self, file_bytes: bytes, file_name: str) -> str:
        if not settings.llama_cloud_api_key:
            raise FallbackParsingError("LLAMA_CLOUD_API_KEY 未設定，無法觸發 LlamaParse fallback")

        headers = {"Authorization": f"Bearer {settings.llama_cloud_api_key}"}
        async with httpx.AsyncClient(base_url=self._BASE_URL, headers=headers, timeout=30) as client:
            try:
                upload_resp = await client.post("/upload", files={"file": (file_name, file_bytes)})
                upload_resp.raise_for_status()
                job_id = upload_resp.json()["id"]
            except httpx.HTTPError as exc:
                raise FallbackParsingError(f"LlamaParse 上傳失敗: {exc}") from exc

            elapsed = 0
            while elapsed < self._POLL_TIMEOUT_SECONDS:
                status_resp = await client.get(f"/job/{job_id}")
                status_resp.raise_for_status()
                status = status_resp.json().get("status")

                if status == "SUCCESS":
                    result_resp = await client.get(f"/job/{job_id}/result/markdown")
                    result_resp.raise_for_status()
                    return result_resp.json().get("markdown", "")
                if status == "ERROR":
                    raise FallbackParsingError(f"LlamaParse 解析失敗: job {job_id}")

                await asyncio.sleep(self._POLL_INTERVAL_SECONDS)
                elapsed += self._POLL_INTERVAL_SECONDS

            raise FallbackParsingError(f"LlamaParse 解析逾時: job {job_id}")
