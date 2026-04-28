# AI Proctoring MVP

An end-to-end starter for an AI-based proctoring workflow:

- Browser captures webcam frames
- FastAPI backend ingests frames over WebSocket
- OpenCV rules generate suspicious events
- Session report API returns full event timeline and risk score

## Features

- Live detection signals:
  - No face detected
  - Multiple faces detected
  - Low-light environment
- Running risk score
- Real-time alert list in UI
- Session report endpoint for post-exam analysis

## Quick start

1. Create and activate a Python virtual environment.
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Start server:

   ```bash
   uvicorn app.main:app --reload
   ```

4. Open [http://127.0.0.1:8000](http://127.0.0.1:8000).
5. Click **Start Session** and allow camera permission.

## API endpoints

- `POST /api/sessions` -> create a new proctoring session
- `GET /api/sessions/{session_id}/report` -> fetch session summary
- `WS /ws/sessions/{session_id}` -> stream frames and receive live detections

## Next upgrades (production direction)

- Add identity verification and liveness checks
- Add gaze/head pose estimation
- Add tab-switch/fullscreen/keyboard event monitoring
- Persist sessions to PostgreSQL + object storage
- Add authentication and role-based dashboards
- Support exam rules/policy configuration per tenant
