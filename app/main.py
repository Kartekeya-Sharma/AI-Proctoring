from __future__ import annotations

import base64
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


@dataclass
class Event:
    ts: float
    code: str
    severity: int
    message: str


@dataclass
class SessionState:
    id: str
    created_at: float = field(default_factory=lambda: time.time())
    frames_processed: int = 0
    risk_score: int = 0
    events: list[Event] = field(default_factory=list)


class SessionCreateResponse(BaseModel):
    session_id: str


class SessionReport(BaseModel):
    session_id: str
    created_at: float
    frames_processed: int
    risk_score: int
    events: list[dict[str, Any]]


class ProctorEngine:
    def __init__(self) -> None:
        self.face_detector = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        self.low_light_threshold = 45.0

    def analyze(self, frame_bgr: np.ndarray) -> list[Event]:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        faces = self.face_detector.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5)
        events: list[Event] = []
        now = time.time()

        if len(faces) == 0:
            events.append(
                Event(
                    ts=now,
                    code="NO_FACE",
                    severity=3,
                    message="No face detected in frame.",
                )
            )
        elif len(faces) > 1:
            events.append(
                Event(
                    ts=now,
                    code="MULTIPLE_FACES",
                    severity=5,
                    message=f"Detected {len(faces)} faces.",
                )
            )

        brightness = float(np.mean(gray))
        if brightness < self.low_light_threshold:
            events.append(
                Event(
                    ts=now,
                    code="LOW_LIGHT",
                    severity=2,
                    message=f"Low light condition (mean={brightness:.1f}).",
                )
            )
        return events


app = FastAPI(title="AI Proctoring MVP")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
engine = ProctorEngine()
sessions: dict[str, SessionState] = {}


def decode_base64_image(encoded_jpeg: str) -> np.ndarray:
    if "," in encoded_jpeg:
        encoded_jpeg = encoded_jpeg.split(",", 1)[1]
    image_bytes = base64.b64decode(encoded_jpeg)
    np_bytes = np.frombuffer(image_bytes, dtype=np.uint8)
    frame = cv2.imdecode(np_bytes, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Unable to decode frame")
    return frame


@app.get("/")
def root() -> FileResponse:
    return FileResponse("app/static/index.html")


@app.post("/api/sessions", response_model=SessionCreateResponse)
def create_session() -> SessionCreateResponse:
    session_id = str(uuid.uuid4())
    sessions[session_id] = SessionState(id=session_id)
    return SessionCreateResponse(session_id=session_id)


@app.get("/api/sessions/{session_id}/report", response_model=SessionReport)
def get_report(session_id: str) -> SessionReport:
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionReport(
        session_id=session.id,
        created_at=session.created_at,
        frames_processed=session.frames_processed,
        risk_score=session.risk_score,
        events=[
            {
                "ts": ev.ts,
                "code": ev.code,
                "severity": ev.severity,
                "message": ev.message,
            }
            for ev in session.events
        ],
    )


@app.websocket("/ws/sessions/{session_id}")
async def stream_session(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    session = sessions.get(session_id)
    if not session:
        await websocket.send_json({"error": "session_not_found"})
        await websocket.close()
        return

    try:
        while True:
            payload = await websocket.receive_json()
            frame_b64 = payload.get("frame")
            if not isinstance(frame_b64, str):
                await websocket.send_json({"error": "invalid_payload"})
                continue

            try:
                frame = decode_base64_image(frame_b64)
            except Exception:
                await websocket.send_json({"error": "frame_decode_failed"})
                continue

            events = engine.analyze(frame)
            session.frames_processed += 1
            for event in events:
                session.events.append(event)
                session.risk_score += event.severity

            await websocket.send_json(
                {
                    "frames_processed": session.frames_processed,
                    "risk_score": session.risk_score,
                    "events": [
                        {
                            "ts": event.ts,
                            "code": event.code,
                            "severity": event.severity,
                            "message": event.message,
                        }
                        for event in events
                    ],
                }
            )
    except WebSocketDisconnect:
        return
