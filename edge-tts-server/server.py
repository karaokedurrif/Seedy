"""Micro-servidor TTS compatible con la API OpenAI /v1/audio/speech.
Usa Microsoft Edge TTS (voces neuronales gratuitas).
"""
import asyncio, io, re
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import edge_tts

# Mapa de voces OpenAI → Edge TTS español
VOICE_MAP = {
    "alloy":   "es-ES-ElviraNeural",   # mujer España
    "nova":    "es-ES-ElviraNeural",
    "shimmer": "es-ES-ElviraNeural",
    "echo":    "es-ES-AlvaroNeural",    # hombre España
    "fable":   "es-ES-AlvaroNeural",
    "onyx":    "es-ES-AlvaroNeural",
}

# Regex para limpiar markdown antes de hablar
MD_PATTERNS = [
    (re.compile(r'^#{1,6}\s+', re.MULTILINE), ''),          # headers
    (re.compile(r'\*{1,3}([^*]+)\*{1,3}'), r'\1'),          # bold/italic
    (re.compile(r'_{1,3}([^_]+)_{1,3}'), r'\1'),            # underscore emphasis
    (re.compile(r'`{1,3}[^`]*`{1,3}'), ''),                 # inline code
    (re.compile(r'^\s*[-•]\s+', re.MULTILINE), ''),          # bullets
    (re.compile(r'^\s*\d+\.\s+', re.MULTILINE), ''),         # numbered lists
    (re.compile(r'^\s*>\s+', re.MULTILINE), ''),             # blockquotes
    (re.compile(r'^[\-\*_]{3,}\s*$', re.MULTILINE), ''),     # horizontal rules
    (re.compile(r'\[([^\]]+)\]\([^\)]+\)'), r'\1'),          # links
    (re.compile(r'[~=|]'), ''),                              # misc
    (re.compile(r'\s{2,}'), ' '),                            # collapse spaces
]

def clean_markdown(text: str) -> str:
    for pat, repl in MD_PATTERNS:
        text = pat.sub(repl, text)
    return text.strip()

app = FastAPI()

class SpeechRequest(BaseModel):
    model: str = "tts-1"
    input: str
    voice: str = "alloy"
    response_format: str = "mp3"
    speed: float = 1.0

@app.post("/v1/audio/speech")
async def speech(req: SpeechRequest):
    edge_voice = VOICE_MAP.get(req.voice, "es-ES-ElviraNeural")
    text = clean_markdown(req.input)
    if not text:
        text = "Sin contenido."

    rate = f"{int((req.speed - 1) * 100):+d}%"
    communicate = edge_tts.Communicate(text, edge_voice, rate=rate)

    buf = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])

    buf.seek(0)
    return StreamingResponse(buf, media_type="audio/mpeg")

@app.get("/v1/models")
async def list_models():
    return {"data": [{"id": "tts-1", "object": "model"}, {"id": "tts-1-hd", "object": "model"}]}

@app.get("/v1/audio/speech/voices")
async def list_voices():
    return {"voices": list(VOICE_MAP.keys())}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
