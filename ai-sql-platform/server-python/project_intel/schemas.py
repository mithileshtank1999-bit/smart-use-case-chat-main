from __future__ import annotations

from pydantic import BaseModel
from typing import Any
from typing import List
from datetime import date


class AIRequest(BaseModel):
    message: str


class DBRequest(BaseModel):
    query_type: str
    filters: dict | None = None


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[Message]
    employee_name: str | None = None


class SummaryRequest(BaseModel):
    project_id: str | None = None
    project_name: str | None = None
    project_data: dict | None = None


class RagRebuildRequest(BaseModel):
    project_id: str | None = None
    project_name: str | None = None


class RagSearchRequest(BaseModel):
    query: str
    top_k: int | None = 5
    project_id: str | None = None
    project_name: str | None = None
    chunk_types: list[str] | None = None


class ProjectPatchRequest(BaseModel):
    project_id: str
    updates: dict[str, Any]


class TimesheetFillRequest(BaseModel):
    project_id: int
    employee_name: str
    work_date: date | None = None  # defaults to today (server)
    start_time: str | None = "09:00"
    end_time: str | None = "17:00"
    effort_minutes: int | None = 480
    description: str | None = "SDG development"
    item: str | None = "Config"
    template_timesheetid: int | None = None
    engagementroleid: int | None = None
    engagementlocationid: int | None = None
    projecttaskid: int | None = None


class SpeechTranscribeRequest(BaseModel):
    audio_base64: str
    filename: str | None = "audio.webm"
    language: str | None = None


class TimesheetCommandRequest(BaseModel):
    project_id: int
    employee_name: str
    command: str


class DocumentSearchRequest(BaseModel):
    query: str
    top_k: int | None = 5


class MeetingAnalyzeRequest(BaseModel):
    transcript: str
    project_name: str | None = None


# ---- WSR (Weekly Status Report) ----

class WSRDefects(BaseModel):
    open: int = 0
    closed: int = 0
    in_progress: int = 0


class WSRHighlight(BaseModel):
    section: str
    bullets: list[str]


class WSRGroup(BaseModel):
    group: str
    items: list[str]


class WSRRequest(BaseModel):
    project_name: str
    reporting_period: str
    project_module: str | None = None
    key_highlights: list[WSRHighlight] = []
    blockers: list[str] = []
    key_risks: list[WSRGroup] = []
    next_week_plan: list[WSRGroup] = []
    completion_percentage: int | None = None
    report_recipients: list[str] = []
    defects: WSRDefects | None = None
    generated_by: str | None = None


class WSRFromTextRequest(BaseModel):
    text: str
    send_email: bool = False
