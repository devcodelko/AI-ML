import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from config import logger, ALLOWED_ORIGINS, APP_PORT
from models import (
    ChatRequest,
    ChatResponse,
    ResetRequest,
    ResetResponse,
    ChapterContentResponse,
)
from chat_service import chat_service
from content_api_client import content_api_client

app = FastAPI(title="AI Learning Assistant API", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


@app.get("/")
def home():
    index_path = os.path.join(BASE_DIR, "index.html")
    return FileResponse(index_path)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/api/chapter-content", response_model=ChapterContentResponse)
def get_chapter_content(course_id: str, module_id: str, chapter_id: str):
    data = content_api_client.get_chapter(course_id, module_id, chapter_id)
    return ChapterContentResponse(**data)


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    result = chat_service.handle_message(
        session_id=request.session_id,
        course_id=request.course_id,
        module_id=request.module_id,
        chapter_id=request.chapter_id,
        message=request.message,
    )
    return ChatResponse(**result)


@app.post("/api/chat/stream")
def chat_stream(request: ChatRequest):
    """Server-Sent Events endpoint. Streams the model's reply token by token
    as it is generated, so the UI can render it word by word in real time."""
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    meta, token_generator = chat_service.handle_message_stream(
        session_id=request.session_id,
        course_id=request.course_id, 
        module_id=request.module_id,
        chapter_id=request.chapter_id,
        message=request.message,
    )

    def event_stream():
        yield f"data: {json.dumps({'type': 'meta', **meta})}\n\n"
        try:
            for token in token_generator:
                yield f"data: {json.dumps({'type': 'chunk', 'text': token})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as exc:
            logger.exception("Streaming generation failed")
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/chat/reset", response_model=ResetResponse)
def reset_chat(request: ResetRequest):
    chat_service.reset_session(request.session_id)
    return ResetResponse(status="reset")


if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print("  AI Learning Assistant")
    print(f"  URL   : http://127.0.0.1:{APP_PORT}")
    print("  Endpoints:")
    print("    POST /api/chat")
    print("    POST /api/chat/stream  (SSE, word-by-word)")
    print("    POST /api/chat/reset")
    print("    GET  /api/chapter-content")
    print("    GET  /health")
    print("=" * 60)

    uvicorn.run("main:app", host="0.0.0.0", port=APP_PORT, reload=True)
