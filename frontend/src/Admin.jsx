import { useCallback, useEffect, useState } from "react";
import { getSite, getStatus, getScore, getTasks, simulate, timeWarp } from "./api";

const ROLES = ["admin", "security", "maintenance", "resident"];

const STAGE_LABEL = {
  issued: "Alert issued",
  admin_notified: "Escalated to admin",
  site_red: "Site red",
  locked: "Score locked",
};

function formatHours(h) {
  if (h <= 0) return "Rain window reached";
  const m = Math.round(h * 60);
  return `${Math.floor(m / 60)}h ${m % 60}m left`;
}

export default function Admin() {
  const [site, setSite] = useState(null);
  const [status, setStatus] = useState(null);
  const [score, setScore] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setSite(await getSite());
      try {
        const [st, sc, tk] = await Promise.all([getStatus(), getScore(), getTasks()]);
        setStatus(st);
        setScore(sc);
        setTasks(tk.tasks);
      } catch {
        setStatus(null);
        setScore(null);
        setTasks([]);
      }
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, [refresh]);

  async function act(fn) {
    setBusy(true);
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(e.message);
    }
    setBusy(false);
  }

  const level = status ? status.riskLevel : "Normal";
  const pct = score ? score.readinessPercent : 0;
  const shownScore = status && status.lockedScore !== null ? status.lockedScore : pct;

  return (
    <div className="page">
      {error && <div className="error">Could not reach the API: {error}</div>}

      <section className="card">
        <div className="row">
          <div>
            <h2>{site ? site.name : "Loading site..."}</h2>
            <span className="chip chip-sim">SIMULATED scenario</span>
          </div>
          <div className={`level level-${level.toLowerCase()}`}>{level}</div>
        </div>

        {status ? (
          <p className="muted">
            {STAGE_LABEL[status.stage]} | {formatHours(status.hoursToWindow)}
            {status.escalatedTasks > 0 && ` | ${status.escalatedTasks} tasks escalated`}
          </p>
        ) : (
          <p className="muted">No active incident. Press Simulate rain to start one.</p>
        )}

        {status && status.siteRed && (
          <div className="banner-red">
            SITE RED: critical tasks are still open close to the rain window
          </div>
        )}

        <div className="buttons">
          <button disabled={busy} onClick={() => act(simulate)}>Simulate rain (90 mm)</button>
          <button disabled={busy || !status} onClick={() => act(() => timeWarp(60))}>
            Time-warp +1 hour
          </button>
          <button disabled={busy || !status} onClick={() => act(() => timeWarp(180))}>
            Time-warp +3 hours
          </button>
        </div>
      </section>

      {score && (
        <section className="card">
          <h3>
            Readiness {shownScore}%
            {status.lockedScore !== null && <span className="chip">locked</span>}
          </h3>
          <div className="bar"><div className="bar-fill" style={{ width: `${shownScore}%` }} /></div>
          <div className="stats">
            <div><strong>{score.criticalDone}/{score.criticalTotal}</strong><span>critical tasks done</span></div>
            <div><strong>{score.vehiclesMoved}/{score.vehiclesTotal}</strong><span>vehicles moved</span></div>
            <div><strong>{score.unacknowledged}</strong><span>not acknowledged</span></div>
          </div>
        </section>
      )}

      {ROLES.map((role) => {
        const list = tasks
          .filter((t) => t.role === role)
          .sort((a, b) => a.taskId.localeCompare(b.taskId));
        if (list.length === 0) return null;
        return (
          <section className="card" key={role}>
            <h3 className="cap">{role} ({list.filter((t) => t.status === "done").length}/{list.length} done)</h3>
            {list.map((t) => (
              <div className="task" key={t.taskId}>
                <span className={`dot dot-${t.status}`} />
                <div className="task-main">
                  <div>{t.title}</div>
                  <div className="muted small">
                    {t.status}
                    {t.evidence !== "none" && ` | proof: ${t.evidence}`}
                    {t.escalated && " | escalated"}
                  </div>
                </div>
                {t.critical && <span className="chip chip-crit">critical</span>}
              </div>
            ))}
          </section>
        );
      })}
    </div>
  );
}