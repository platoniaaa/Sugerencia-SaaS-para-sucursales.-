"""Endpoint del chatbot del sugerido.

Protegido por requiere_admin (fase 1). Si Gemini no esta configurado, responde
503 con un mensaje accionable.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import chatbot_service

router = APIRouter(prefix="/api/chat", tags=["chat"])


class Mensaje(BaseModel):
    role: str = Field(description="'user' o 'model'")
    text: str


class ChatRequest(BaseModel):
    pregunta: str = Field(min_length=1, max_length=2000)
    historial: list[Mensaje] = Field(default_factory=list)


class ChatResponse(BaseModel):
    respuesta: str


@router.post("", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    try:
        respuesta = chatbot_service.responder(
            db,
            req.pregunta,
            [m.model_dump() for m in req.historial],
        )
    except chatbot_service.GeminiNoConfigurado as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        # Errores del SDK (cuota agotada, key invalida, etc.) salen como 502 con el msg.
        raise HTTPException(
            status_code=502, detail=f"Error del modelo: {e}"
        ) from e
    return ChatResponse(respuesta=respuesta)
