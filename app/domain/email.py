from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Email(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    sender: str = Field(alias="from")
    recipient: str = Field(alias="to")
    received_at: datetime
    subject: str = ""
    body: str = ""
    attachments: list[Any] = Field(default_factory=list)
