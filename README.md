# AI Proctoring MVP

An end-to-end starter for an AI-based proctoring workflow:

- Browser captures webcam frames
- FastAPI backend ingests frames over WebSocket
- OpenCV rules generate suspicious events
- Session + events are persisted in a database
- Session report API returns full event timeline and risk score

## Features

- Live detection signals:
  - No face detected
  - Multiple faces detected
  - Low-light environment
  - Identity mismatch vs initial baseline face
- Browser policy violation signals:
  - Tab hidden/switch
  - Window blur
  - Fullscreen exit
- Running risk score
- Real-time alert list in UI
- Session report endpoint for post-exam analysis
- Admin dashboard for session monitoring

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
6. Open [http://127.0.0.1:8000/admin](http://127.0.0.1:8000/admin) for dashboard.

## Database setup

- Default DB is SQLite at `proctoring.db` (works out of the box).
- For PostgreSQL, set:

  ```bash
  export DATABASE_URL="postgresql+psycopg://USER:PASSWORD@HOST:5432/DB_NAME"
  ```

- Then run the server; tables are auto-created on startup.

## API endpoints

- `POST /api/sessions` -> create a new proctoring session
- `GET /api/sessions/{session_id}/report` -> fetch session summary
- `GET /api/admin/sessions` -> list sessions for dashboard
- `WS /ws/sessions/{session_id}` -> stream frames and receive live detections

## Next upgrades (production direction)

- Add gaze/head pose estimation
- Add stronger identity verification and liveness checks
- Add keyboard and devtools behavior monitoring
- Add object storage for frame snapshots/clips
- Add authentication and role-based dashboards
- Support exam rules/policy configuration per tenant
