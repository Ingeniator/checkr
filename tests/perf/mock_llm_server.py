"""Mock OpenAI-compatible LLM server for performance testing.

Returns a fixed "Score: 85" response after a configurable delay
to simulate real LLM latency.
"""

import asyncio
import os
import time

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Mock LLM Server")

MOCK_DELAY = float(os.environ.get("MOCK_DELAY", "0.1"))


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str = ""
    messages: list[ChatMessage] = []
    temperature: float = 0.0


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    await asyncio.sleep(MOCK_DELAY)
    return {
        "id": f"mock-{time.time_ns()}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Score: 85"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=1234)
