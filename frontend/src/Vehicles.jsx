import { useCallback, useEffect, useState } from "react";
import { getVehicles, getStatus } from "./api";

export default function Vehicles() {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const [v, st] = await Promise.all([getVehicles(), getStatus()]);
      setData(v);
      setStatus(st);
    } catch {
      setData(null);
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 4000);
    return () => clearInterval(id);
  }, [refresh]);

  if (!data || !status) {
    return (
      <div className="page">
        <section className="card">
          <h2>Vehicle priority</h2>
          <p className="muted">No active incident. Press Simulate rain on the Admin tab.</p>
        </section>
      </div>
    );
  }

  const movedCount = data.total - data.remaining;
  const pct = data.total ? Math.round((100 * movedCount) / data.total) : 0;

  return (
    <div className="page">
      <section className="card">
        <div className="row">
          <div>
            <h2>Vehicle priority</h2>
            <span className="chip chip-sim">SIMULATED scenario</span>
          </div>
          <div className="veh-count">
            <strong>{data.remaining}</strong>
            <span>still to move</span>
          </div>
        </div>
        <div className="bar"><div className="bar-fill" style={{ width: `${pct}%` }} /></div>
        <p className="muted small">
          Lowest basement level first, then low-lying bays. Move each car to the slot shown.
        </p>
      </section>

      {data.vehicles.map((v, i) => (
        <section className={v.moved ? "card veh-done" : "card"} key={v.vehicleKey}>
          <div className="task task-plain">
            <span className="veh-num">{v.moved ? "✓" : i + 1}</span>
            <div className="task-main">
              <div className="veh-route">
                {v.bay} <span className="veh-arrow">to</span> {v.moveToSlot}
              </div>
              <div className="muted small">
                Flat {v.flat} | plate ending {v.plateLast4}
              </div>
            </div>
            {v.lowLying && !v.moved && <span className="chip chip-crit">low-lying bay</span>}
            {v.moved && <span className="chip">moved</span>}
          </div>
        </section>
      ))}
    </div>
  );
}