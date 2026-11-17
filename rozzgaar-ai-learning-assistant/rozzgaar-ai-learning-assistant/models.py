from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="Unique client session identifier")
    course_id: str = Field(..., description="Course slug, e.g. 'edp'")
    module_id: str = Field(..., description="Module name exactly as returned by the API, e.g. 'Module 1'")
    chapter_id: str = Field(..., description="Chapter numeric id, e.g. '1'")
    message: str


class ChatResponse(BaseModel):
    reply: str
    module_name: str
    chapter_name: str
    context_switched: bool


class ResetRequest(BaseModel):
    session_id: str


class ResetResponse(BaseModel):
    status: str


class ChapterContentResponse(BaseModel):
    module_name: str
    chapter_name: str
    content: str
