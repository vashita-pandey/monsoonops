import { useCallback, useEffect, useState } from "react";
import { getTasks, getStatus, ackTask, completeTask, uploadEvidence } from "./api";

const PROOF_LABEL = {
  photo: "needs a photo",
  testlog: "needs a test log",
  second_person: "needs a second person to confirm",
  none: "",
};

export default function RoleScreen({ role, defaultName }) {
  const [tasks, setTasks] = useState([]);
  const [status, setStatus] = useState(null);
  const [name, setName] = useState(defaultName);
  const [notes, setNotes] = useState({});
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState("");

  const setNote = (id, value) => setNotes((n) => ({ ...n, [id]: value }));

  const refresh = useCallback(async () => {
    try {
      const [tk, st] = await Promise.all([getTasks(role), getStatus()]);
      setTasks([...tk.tasks].sort((a, b) => a.taskId.localeCompare(b.taskId)));
      setStatus(st);
    } catch {
      setTasks([]);
      setStatus(null);
    }
  }, [role]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, [refresh]);

  async function run(taskId, fn) {
    setBusyId(taskId);
    setError("");
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(e.message);
    }
    setBusyId(null);
  }

  const onAck = (t) => run(t.taskId, () => ackTask(t.taskId, name));

  function onPhoto(t, file) {
    if (!file) return;
    if (!["image/jpeg", "image/png"].includes(file.type)) {
      setError("Please choose a JPG or PNG photo.");
      return;
    }
    run(t.taskId, async () => {
      const key = await uploadEvidence(t.taskId, file, file.type);
      await completeTask(t.taskId, { by: name, evidence: key });
    });
  }

  function onTestLog(t) {
    const text = (notes[t.taskId] || "").trim();
    if (!text) {
      setError("Write a short test note first.");
      return;
    }
    run(t.taskId, async () => {
      const blob = new Blob([text], { type: "text/plain" });
      const key = await uploadEvidence(t.taskId, blob, "text/plain");
      await completeTask(t.taskId, { by: name, evidence: key });
    });
  }

  function onSecondPerson(t) {
    const verifier = (notes[t.taskId] || "").trim();
    if (!verifier) {
      setError("Enter the name of the person confirming.");
      return;
    }
    run(t.taskId, () => completeTask(t.taskId, { by: name, verifiedBy: verifier }));
  }

  const onDone = (t) => run(t.taskId, () => completeTask(t.taskId, { by: name }));

  function actions(t) {
    const busy = busyId === t.taskId;

    if (t.evidence === "photo") {
      return (
        <label className={`file-btn ${busy ? "file-btn-off" : ""}`}>
          {busy ? "Uploading..." : "Take or choose photo"}
          <input
            type="file"
            accept="image/jpeg,image/png"
            capture="environment"
            hidden
            disabled={busy}
            onChange={(e) => {
              onPhoto(t, e.target.files[0]);
              e.target.value = "";
            }}
          />
        </label>
      );
    }

    if (t.evidence === "testlog") {
      return (
        <div className="evidence-box">
          <textarea
            rows={2}
            placeholder="e.g. Pump ran for 2 minutes, water flowing normally"
            value={notes[t.taskId] || ""}
            onChange={(e) => setNote(t.taskId, e.target.value)}
          />
          <button className="act" disabled={busy} onClick={() => onTestLog(t)}>
            {busy ? "Saving..." : "Submit test log"}
          </button>
        </div>
      );
    }

    if (t.evidence === "second_person") {
      return (
        <div className="evidence-box">
          <input
            type="text"
            placeholder="Name of the person confirming"
            value={notes[t.taskId] || ""}
            onChange={(e) => setNote(t.taskId, e.target.value)}
          />
          <button className="act" disabled={busy} onClick={() => onSecondPerson(t)}>
            {busy ? "Saving..." : "Mark done"}
          </button>
        </div>
      );
    }

    return (
      <button className="act" disabled={busy} onClick={() => onDone(t)}>
        {busy ? "Saving..." : "Mark done"}
      </button>
    );
  }

  const doneCount = tasks.filter((t) => t.status === "done").length;

  return (
    <div className="page">
      <section className="card">
        <h2 className="cap">{role} tasks</h2>
        <label className="name-row">
          You are
          <input type="text" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        {status && (
          <p className="muted">
            Risk level: <strong>{status.riskLevel}</strong> | {doneCount}/{tasks.length} done
          </p>
        )}
        {status && status.stage === "locked" && (
          <p className="muted small">
            The readiness score is locked. Actions after this point are still logged.
          </p>
        )}
      </section>

      {error && <div className="error">{error}</div>}

      {!status && (
        <section className="card">
          <p className="muted">No active incident. Press Simulate rain on the Admin tab.</p>
        </section>
      )}

      {tasks.map((t) => (
        <section className="card" key={t.taskId}>
          <div className="task task-plain">
            <span className={`dot dot-${t.status}`} />
            <div className="task-main">
              <div>{t.title}</div>
              <div className="muted small">
                {t.status}
                {PROOF_LABEL[t.evidence] && ` | ${PROOF_LABEL[t.evidence]}`}
                {t.escalated && " | escalated"}
              </div>
            </div>
            {t.critical && <span className="chip chip-crit">critical</span>}
          </div>

          {t.status === "open" && (
            <button className="act" disabled={busyId === t.taskId} onClick={() => onAck(t)}>
              Acknowledge
            </button>
          )}
          {t.status === "acknowledged" && actions(t)}
          {t.status === "done" && (
            <div className="muted small">
              Done by {t.doneBy}
              {t.verifiedBy && t.verifiedBy !== "none" && `, confirmed by ${t.verifiedBy}`}
            </div>
          )}
        </section>
      ))}
    </div>
  );
}