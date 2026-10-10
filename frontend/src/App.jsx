import { useState } from "react";
import Admin from "./Admin";
import RoleScreen from "./RoleScreen";
import "./App.css";

const TABS = [
  { id: "admin", label: "Admin" },
  { id: "security", label: "Security" },
  { id: "maintenance", label: "Maintenance" },
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
        {tab === "security" && <RoleScreen role="security" defaultName="Ravi" />}
        {tab === "maintenance" && <RoleScreen role="maintenance" defaultName="Meena" />}
      </main>
    </div>
  );
}