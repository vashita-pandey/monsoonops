import { useState } from "react";
import Admin from "./Admin";
import RoleScreen from "./RoleScreen";
import Resident from "./Resident";
import Vehicles from "./Vehicles";
import "./App.css";

const TABS = [
  { id: "admin", label: "Admin" },
  { id: "vehicles", label: "Vehicles" },
  { id: "security", label: "Security" },
  { id: "maintenance", label: "Maintenance" },
  { id: "resident", label: "Resident" },
];

export default function App() {
  const [tab, setTab] = useState("admin");

  return (
    <div className="app">
      <header className="topbar">
        <strong>MonsoonOps</strong>
        <span>Rain readiness ledger</span>
      </header>

      <nav className="tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={tab === t.id ? "tab tab-on" : "tab"}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <main>
        {tab === "admin" && <Admin />}
        {tab === "vehicles" && <Vehicles />}
        {tab === "security" && <RoleScreen role="security" defaultName="Ravi" />}
        {tab === "maintenance" && <RoleScreen role="maintenance" defaultName="Meena" />}
        {tab === "resident" && <Resident />}
      </main>
    </div>
  );
}