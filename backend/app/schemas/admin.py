from pydantic import BaseModel


class SyncKnowledgeBaseResponse(BaseModel):
    status: str


class TestNotificationResponse(BaseModel):
    status: str
