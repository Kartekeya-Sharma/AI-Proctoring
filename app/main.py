from __future__ import annotations

import base64
import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import Float, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class ProctorSession(Base):
    __tablename__ = "proctor_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[float] = mapped_column(Float, default=lambda: time.time())
    frames_processed: Mapped[int] = mapped_column(Integer, default=0)
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    baseline_signature_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProctorEvent(Base):
    __tablename__ = "proctor_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    ts: Mapped[float] = mapped_column(Float)
    code: Mapped[str] = mapped_column(String(64))
    severity: Mapped[int] = mapped_column(Integer)
    message: Mapped[str] = mapped_column(Text)


@dataclass
class Event:
    ts: float
    code: str
    severity: int
    message: str


class SessionCreateResponse(BaseModel):
    session_id: str


class SessionReport(BaseModel):
    session_id: str
    created_at: float
    frames_processed: int
    risk_score: int
    events: list[dict[str, Any]]


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./proctoring.db")
engine_db = create_engine(DATABASE_URL, future=True)


class ProctorEngine:
    def __init__(self) -> None:
        self.face_detector = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        self.low_light_threshold = 45.0
        self.identity_mismatch_threshold = 0.18

    def _face_signature(
        self, gray: np.ndarray, face_box: tuple[int, int, int, int]
    ) -> np.ndarray:
        x, y, w, h = face_box
        face_crop = gray[y : y + h, x : x + w]
        resized = cv2.resize(face_crop, (32, 32))
        vec = resized.astype(np.float32).flatten()
        norm = np.linalg.norm(vec) + 1e-8
        return vec / norm

    def analyze(
        self, frame_bgr: np.ndarray, baseline_signature: np.ndarray | None
    ) -> tuple[list[Event], np.ndarray | None]:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        faces = self.face_detector.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5)
        events: list[Event] = []
        now = time.time()
        updated_baseline = baseline_signature

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
        else:
            signature = self._face_signature(gray, tuple(int(v) for v in faces[0]))
            if baseline_signature is None:
                updated_baseline = signature
                events.append(
                    Event(
                        ts=now,
                        code="IDENTITY_BASELINE_SET",
                        severity=0,
                        message="Reference identity baseline initialized.",
                    )
                )
            else:
                similarity = float(np.dot(signature, baseline_signature))
                if similarity < 1.0 - self.identity_mismatch_threshold:
                    events.append(
                        Event(
                            ts=now,
                            code="IDENTITY_MISMATCH",
                            severity=6,
                            message=f"Face mismatch detected (similarity={similarity:.2f}).",
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
        return events, updated_baseline


app = FastAPI(title="AI Proctoring MVP")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
detector = ProctorEngine()


def decode_base64_image(encoded_jpeg: str) -> np.ndarray:
    if "," in encoded_jpeg:
        encoded_jpeg = encoded_jpeg.split(",", 1)[1]
    image_bytes = base64.b64decode(encoded_jpeg)
    np_bytes = np.frombuffer(image_bytes, dtype=np.uint8)
    frame = cv2.imdecode(np_bytes, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Unable to decode frame")
    return frame


def create_event(db: Session, session_id: str, event: Event) -> None:
    db.add(
        ProctorEvent(
            session_id=session_id,
            ts=event.ts,
            code=event.code,
            severity=event.severity,
            message=event.message,
        )
    )


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(engine_db)


@app.get("/")
def root() -> FileResponse:
    return FileResponse("app/static/index.html")


@app.get("/admin")
def admin() -> FileResponse:
    return FileResponse("app/static/admin.html")


@app.post("/api/sessions", response_model=SessionCreateResponse)
def create_session() -> SessionCreateResponse:
    session_id = str(uuid.uuid4())
    with Session(engine_db) as db:
        db.add(ProctorSession(id=session_id))
        db.commit()
    return SessionCreateResponse(session_id=session_id)


@app.get("/api/sessions/{session_id}/report", response_model=SessionReport)
def get_report(session_id: str) -> SessionReport:
    with Session(engine_db) as db:
        session = db.get(ProctorSession, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        events = db.scalars(
            select(ProctorEvent)
            .where(ProctorEvent.session_id == session_id)
            .order_by(ProctorEvent.ts.asc())
        ).all()

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
                for ev in events
            ],
        )


@app.get("/api/admin/sessions")
def admin_sessions() -> dict[str, list[dict[str, Any]]]:
    with Session(engine_db) as db:
        rows = db.scalars(
            select(ProctorSession).order_by(ProctorSession.created_at.desc())
        ).all()
    return {
        "sessions": [
            {
                "session_id": s.id,
                "created_at": s.created_at,
                "frames_processed": s.frames_processed,
                "risk_score": s.risk_score,
            }
            for s in rows
        ]
    }


@app.websocket("/ws/sessions/{session_id}")
async def stream_session(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()

    with Session(engine_db) as db:
        session = db.get(ProctorSession, session_id)
        if not session:
            await websocket.send_json({"error": "session_not_found"})
            await websocket.close()
            return

    try:
        while True:
            payload = await websocket.receive_json()
            msg_type = payload.get("type", "frame")

            with Session(engine_db) as db:
                session = db.get(ProctorSession, session_id)
                if not session:
                    await websocket.send_json({"error": "session_not_found"})
                    continue

                if msg_type == "client_event":
                    code = str(payload.get("code", "CLIENT_EVENT"))
                    message = str(payload.get("message", "Client side violation signal"))
                    severity = int(payload.get("severity", 4))
                    event = Event(ts=time.time(), code=code, severity=severity, message=message)
                    create_event(db, session_id, event)
                    session.risk_score += severity
                    db.commit()
                    await websocket.send_json(
                        {
                            "frames_processed": session.frames_processed,
                            "risk_score": session.risk_score,
                            "events": [event.__dict__],
                        }
                    )
                    continue

                frame_b64 = payload.get("frame")
                if not isinstance(frame_b64, str):
                    await websocket.send_json({"error": "invalid_payload"})
                    continue

                try:
                    frame = decode_base64_image(frame_b64)
                except Exception:
                    await websocket.send_json({"error": "frame_decode_failed"})
                    continue

                baseline = None
                if session.baseline_signature_json:
                    baseline = np.array(json.loads(session.baseline_signature_json), dtype=np.float32)

                events, new_baseline = detector.analyze(frame, baseline)
                session.frames_processed += 1
                if new_baseline is not None and baseline is None:
                    session.baseline_signature_json = json.dumps(new_baseline.tolist())

                for event in events:
                    create_event(db, session_id, event)
                    session.risk_score += event.severity

                db.commit()

                await websocket.send_json(
                    {
                        "frames_processed": session.frames_processed,
                        "risk_score": session.risk_score,
                        "events": [event.__dict__ for event in events],
                    }
                )
    except WebSocketDisconnect:
        return
