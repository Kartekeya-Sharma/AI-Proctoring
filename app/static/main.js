const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const reportBtn = document.getElementById("reportBtn");
const sessionEl = document.getElementById("sessionId");
const framesEl = document.getElementById("frames");
const riskEl = document.getElementById("risk");
const alertsEl = document.getElementById("alerts");
const videoEl = document.getElementById("camera");
const canvasEl = document.getElementById("snapshotCanvas");

const ctx = canvasEl.getContext("2d");
let mediaStream = null;
let socket = null;
let captureTimer = null;
let sessionId = null;
const violationListenerCleanups = [];

function appendAlert(text) {
  const item = document.createElement("li");
  item.textContent = text;
  alertsEl.prepend(item);
}

async function startCamera() {
  mediaStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
  videoEl.srcObject = mediaStream;
}

function stopCamera() {
  if (!mediaStream) return;
  mediaStream.getTracks().forEach((track) => track.stop());
  mediaStream = null;
}

function frameToBase64() {
  ctx.drawImage(videoEl, 0, 0, canvasEl.width, canvasEl.height);
  return canvasEl.toDataURL("image/jpeg", 0.7);
}

async function createSession() {
  const res = await fetch("/api/sessions", { method: "POST" });
  if (!res.ok) throw new Error("Failed to create session");
  return res.json();
}

async function fetchReport() {
  if (!sessionId) return;
  const res = await fetch(`/api/sessions/${sessionId}/report`);
  const data = await res.json();
  appendAlert(
    `Report -> frames=${data.frames_processed}, risk=${data.risk_score}, events=${data.events.length}`
  );
}

function setRunningUI(isRunning) {
  startBtn.disabled = isRunning;
  stopBtn.disabled = !isRunning;
  reportBtn.disabled = isRunning || !sessionId;
}

function sendClientViolation(code, message, severity = 4) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  socket.send(JSON.stringify({ type: "client_event", code, message, severity }));
}

function setupViolationListeners() {
  const onVisibility = () => {
    if (document.hidden) {
      sendClientViolation("TAB_HIDDEN", "Candidate switched away from exam tab.", 5);
    }
  };
  const onBlur = () =>
    sendClientViolation("WINDOW_BLUR", "Exam window lost focus.", 4);
  const onFullscreen = () => {
    if (!document.fullscreenElement) {
      sendClientViolation("FULLSCREEN_EXIT", "Candidate exited fullscreen mode.", 4);
    }
  };

  document.addEventListener("visibilitychange", onVisibility);
  window.addEventListener("blur", onBlur);
  document.addEventListener("fullscreenchange", onFullscreen);

  violationListenerCleanups.push(() =>
    document.removeEventListener("visibilitychange", onVisibility)
  );
  violationListenerCleanups.push(() => window.removeEventListener("blur", onBlur));
  violationListenerCleanups.push(() =>
    document.removeEventListener("fullscreenchange", onFullscreen)
  );
}

function teardownViolationListeners() {
  while (violationListenerCleanups.length > 0) {
    const cleanup = violationListenerCleanups.pop();
    cleanup();
  }
}

startBtn.addEventListener("click", async () => {
  alertsEl.innerHTML = "";
  framesEl.textContent = "0";
  riskEl.textContent = "0";

  try {
    const data = await createSession();
    sessionId = data.session_id;
    sessionEl.textContent = sessionId;
    await startCamera();

    socket = new WebSocket(`${location.origin.replace("http", "ws")}/ws/sessions/${sessionId}`);

    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data);
      if (payload.error) {
        appendAlert(`Error: ${payload.error}`);
        return;
      }
      framesEl.textContent = String(payload.frames_processed);
      riskEl.textContent = String(payload.risk_score);
      for (const e of payload.events) {
        appendAlert(`[${e.code}] ${e.message}`);
      }
    };

    socket.onclose = () => {
      clearInterval(captureTimer);
      captureTimer = null;
      teardownViolationListeners();
      setRunningUI(false);
    };

    socket.onerror = () => appendAlert("WebSocket error");

    captureTimer = setInterval(() => {
      if (!socket || socket.readyState !== WebSocket.OPEN) return;
      socket.send(JSON.stringify({ frame: frameToBase64() }));
    }, 1000);

    setupViolationListeners();
    setRunningUI(true);
  } catch (err) {
    appendAlert(`Startup failed: ${err.message}`);
    setRunningUI(false);
  }
});

stopBtn.addEventListener("click", () => {
  if (captureTimer) {
    clearInterval(captureTimer);
    captureTimer = null;
  }
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.close();
  }
  teardownViolationListeners();
  stopCamera();
  setRunningUI(false);
  reportBtn.disabled = !sessionId;
});

reportBtn.addEventListener("click", () => {
  fetchReport().catch((err) => appendAlert(`Report failed: ${err.message}`));
});
