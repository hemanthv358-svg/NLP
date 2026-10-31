from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4_000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1_000)
    style: Literal["concise", "detailed", "student"] = "concise"
    history: list[HistoryMessage] = Field(default_factory=list, max_length=12)
    site_url: HttpUrl | None = None
    request_id: str | None = Field(default=None, min_length=8, max_length=64, pattern=r"^[a-zA-Z0-9-]+$")
    thinking_level: Literal["off", "low", "medium", "high"] = "medium"


class CrawlRequest(BaseModel):
    url: HttpUrl
