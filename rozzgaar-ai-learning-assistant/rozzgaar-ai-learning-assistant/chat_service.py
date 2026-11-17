import threading
from config import MAX_HISTORY_TURNS
from content_api_client import content_api_client
from groq_service import groq_service

SYSTEM_PROMPT_TEMPLATE = """You are an AI Learning Assistant embedded in an online course platform.
You must answer strictly and only using the chapter content provided below. Do not use outside knowledge unless the user explicitly asks you to go beyond this chapter.

Module: {module_name}
Chapter: {chapter_name}

Chapter Content:
\"\"\"
{chapter_content}
\"\"\"

CRITICAL LANGUAGE RULE (follow this above everything else):
- Always reply in the SAME language the user just wrote their message in, no matter what language the chapter content above is written in.
- If the user's message is in English, your entire reply must be in English.
- If the user's message is in Hindi (Devanagari) or Hinglish (Hindi written in Roman letters), your entire reply must be in natural, simple, everyday Hindi (Devanagari script).
- The language of the chapter content is irrelevant to this decision — never let it change your reply language. Only switch languages when the user's own message changes language or explicitly asks for a translation into a specific language.
- If you are unsure, default to the language of the user's most recent message, not the first message in the conversation.

Rules:
1. Answer strictly based on the chapter content above. Never invent facts not present in it.
2. Support requests such as: summarizing the chapter, reading it aloud (as text), generating MCQs, explaining a specific section, giving revision notes, answering direct questions about terms defined in the chapter, and translating the chapter into another language.
3. If asked something not covered in this chapter, politely state that the information is not available in this chapter and ask if they want a general answer outside the chapter's scope.
4. When generating MCQs, produce exactly the number requested, each with 4 options labeled A-D, and clearly mark the correct answer at the end of each question.
5. Format responses cleanly using markdown (use ## or ### for headings, "-" for bullet points, and **bold** for emphasis) where it improves readability.
6. Keep answers short and to the point. Do not pad with filler, meta-commentary ("Sure, here is..."), or restate the question. For a "summarize" request, give only the essential points in a tight paragraph or a few bullet points — do not reproduce large portions of the chapter text. Only go longer than that when the user explicitly asks for more detail, a full explanation, or a specific count of items (e.g. MCQs, notes).
7. Apply the CRITICAL LANGUAGE RULE above on every single reply, including summaries, MCQs, and revision notes — not just direct questions.
"""


class ChatService:
    def __init__(self, max_history_turns: int):
        self._sessions = {}
        self._lock = threading.Lock()
        self._max_history_turns = max_history_turns

    @staticmethod
    def _chapter_key(course_id: str, module_id: str, chapter_id: str) -> str:
        return f"{course_id}::{module_id}::{chapter_id}"

    def reset_session(self, session_id: str):
        with self._lock:
            self._sessions.pop(session_id, None)

    def _build_messages(self, session_id: str, course_id: str, module_id: str, chapter_id: str, message: str):
        chapter_data = content_api_client.get_chapter(course_id, module_id, chapter_id)
        new_key = self._chapter_key(course_id, module_id, chapter_id)

        with self._lock:
            session = self._sessions.get(session_id)
            context_switched = False

            if session is None or session["chapter_key"] != new_key:
                session = {"chapter_key": new_key, "history": []}
                self._sessions[session_id] = session
                context_switched = True

            system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
                module_name=chapter_data["module_name"],
                chapter_name=chapter_data["chapter_name"],
                chapter_content=chapter_data["content"],
            )

            history = session["history"]
            trimmed_history = history[-(self._max_history_turns * 2):]

            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(trimmed_history)
            messages.append({"role": "user", "content": message})

        meta = {
            "module_name": chapter_data["module_name"],
            "chapter_name": chapter_data["chapter_name"],
            "context_switched": context_switched,
        }
        return session, messages, meta

    def handle_message(self, session_id: str, course_id: str, module_id: str, chapter_id: str, message: str) -> dict:
        session, messages, meta = self._build_messages(session_id, course_id, module_id, chapter_id, message)

        reply = groq_service.generate(messages)

        with self._lock:
            session["history"].append({"role": "user", "content": message})
            session["history"].append({"role": "assistant", "content": reply})

        return {"reply": reply, **meta}

    def handle_message_stream(self, session_id: str, course_id: str, module_id: str, chapter_id: str, message: str):
        """Returns (meta, token_generator). token_generator yields text deltas as they
        arrive from the model and appends the finished turn to session history once
        the stream is exhausted."""
        session, messages, meta = self._build_messages(session_id, course_id, module_id, chapter_id, message)

        def token_generator():
            full_reply_parts = []
            for delta in groq_service.generate_stream(messages):
                full_reply_parts.append(delta)
                yield delta

            final_reply = "".join(full_reply_parts)
            with self._lock:
                session["history"].append({"role": "user", "content": message})
                session["history"].append({"role": "assistant", "content": final_reply})

        return meta, token_generator()


chat_service = ChatService(max_history_turns=MAX_HISTORY_TURNS)
