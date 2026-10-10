import { useCallback, useEffect, useState } from "react";
import { getTasks, getStatus, completeTask } from "./api";

const FLATS = Array.from({ length: 10 }, (_, i) => `A-${101 + i}`);

export default function Resident() {
  const [flat, setFlat] = useState(FLATS[0]);
  const [tasks, setTasks] = useState([]);
  const [status, setStatus] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [tk, st] = await Promise.all([getTasks("resident"), getStatus()]);
      setTasks(tk.tasks);
      setStatus(st);
    } catch {
      setTasks([]);
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, [refresh]);

  async function onMoved(t) {
    setBusyId(t.taskId);
    setError("");
    try {
      await completeTask(t.taskId, { by: `Flat ${flat}` });
      await refresh();
    } catch (e) {
      setError(e.message);
    }
    setBusyId(null);
  }

  const mine = tasks.filter((t) => t.assignee === flat);

  return (
    <div className="page">
      <section className="card">
        <h2>Resident</h2>
        <label className="name-row">
          Your flat
          <select
            value={flat}
            onChange={(e) => setFlat(e.target.value)}
            style={{ font: "inherit", padding: "8px 10px", borderRadius: 8 }}
          >
            {FLATS.map((f) => (
              <option key={f} value={f}>{f}</option>
            ))}
          </select>
        </label>
        {status && (
          <p className="muted">
            Risk level: <strong>{status.riskLevel}</strong>
          </p>
        )}
      </section>

      {error && <div className="error">{error}</div>}

      {!status && (
        <section className="card">
          <p className="muted">No active alert right now. You do not need to do anything.</p>
        </section>
      )}

      {status && mine.length === 0 && (
        <section className="card">
          <p className="muted">There are no tasks for this flat.</p>
        </section>
      )}

      {mine.map((t) => (
        <section className="card" key={t.taskId}>
          <div className="task task-plain">
            <span className={`dot dot-${t.status}`} />
            <div className="task-main">
              <div>{t.title}</div>
              <div className="muted small">
                Basement parking floods first in heavy rain. Moving your car now protects it.
              </div>
            </div>
            {t.critical && <span className="chip chip-crit">critical</span>}
          </div>

          {t.status !== "done" && (
            <button className="act" disabled={busyId === t.taskId} onClick={() => onMoved(t)}>
              {busyId === t.taskId ? "Saving..." : "I have moved my car"}
            </button>
          )}
          {t.status === "done" && (
            <div className="muted small">Thank you. Your car is marked as moved.</div>
          )}
        </section>
      ))}
    </div>
  );
}