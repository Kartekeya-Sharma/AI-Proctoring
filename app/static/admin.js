const rowsEl = document.getElementById("sessionRows");
const refreshBtn = document.getElementById("refreshBtn");

function formatTime(ts) {
  return new Date(ts * 1000).toLocaleString();
}

async function loadSessions() {
  const res = await fetch("/api/admin/sessions");
  const data = await res.json();
  rowsEl.innerHTML = "";
  for (const s of data.sessions) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${s.session_id}</td>
      <td>${formatTime(s.created_at)}</td>
      <td>${s.frames_processed}</td>
      <td>${s.risk_score}</td>
      <td><a class="admin-link" href="/api/sessions/${s.session_id}/report" target="_blank">open</a></td>
    `;
    rowsEl.appendChild(tr);
  }
}

refreshBtn.addEventListener("click", () => {
  loadSessions().catch(() => {
    rowsEl.innerHTML = "<tr><td colspan='5'>Failed to load sessions.</td></tr>";
  });
});

loadSessions().catch(() => {
  rowsEl.innerHTML = "<tr><td colspan='5'>Failed to load sessions.</td></tr>";
});
