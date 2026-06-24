import React, { useRef } from "react";
import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Cpu,
  Network,
  Database,
  MessagesSquare,
  Activity,
  Container,
  Globe,
  Boxes,
} from "lucide-react";

const links = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/models", label: "Modèles vLLM", icon: Cpu },
  { to: "/mcp", label: "Serveur MCP", icon: Network },
  { to: "/tunnels", label: "Tunnels", icon: Globe },
  { to: "/docker", label: "Gestion Docker", icon: Container },
  { to: "/rag", label: "RAG / Documents", icon: Database },
  { to: "/chat", label: "Chat de test", icon: MessagesSquare },
  { to: "/studio3d", label: "Studio 3D", icon: Boxes },
];

export default function Sidebar({
  connected,
  kioskMode = false,
  onKioskToggle,
  open = false,
  onClose,
}) {
  const clickCountRef = useRef(0);
  const clickTimerRef = useRef(null);

  const visibleLinks = kioskMode
    ? links.filter((l) => l.to === "/" || l.to === "/chat" || l.to === "/studio3d")
    : links;

  const onLogoClick = () => {
    clickCountRef.current += 1;
    if (clickTimerRef.current) clearTimeout(clickTimerRef.current);
    if (clickCountRef.current >= 5) {
      clickCountRef.current = 0;
      onKioskToggle?.();
      return;
    }
    clickTimerRef.current = setTimeout(() => {
      clickCountRef.current = 0;
    }, 2500);
  };

  return (
    <aside
      className={`fixed inset-y-0 left-0 z-40 flex w-64 shrink-0 transform flex-col border-r border-ink-border bg-ink-900 p-4 transition-transform duration-200 lg:static lg:z-auto lg:translate-x-0 lg:bg-ink-900/60 ${
        open ? "translate-x-0" : "-translate-x-full"
      }`}
    >
      <div className="mb-8 flex items-center gap-3 px-2">
        <button
          type="button"
          aria-label="Basculer le mode kiosk"
          onClick={onLogoClick}
          className="grid h-10 w-10 place-items-center rounded-xl bg-brand text-black font-extrabold"
        >
          v
        </button>
        <div>
          <div className="text-lg font-extrabold leading-none text-white">vibeMCP</div>
          <div className="text-[11px] font-medium text-brand">DGX Spark · GB10</div>
        </div>
      </div>

      <nav className="flex flex-1 flex-col gap-1">
        {visibleLinks.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            onClick={() => onClose?.()}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all ${
                isActive
                  ? "bg-brand/15 text-brand"
                  : "text-slate-400 hover:bg-ink-700 hover:text-slate-100"
              }`
            }
          >
            <Icon size={18} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="mt-4 flex items-center gap-2 rounded-xl border border-ink-border px-3 py-2 text-xs">
        <Activity size={14} className={connected ? "text-brand" : "text-rose-400"} />
        <span className="text-slate-400">
          Télémétrie {connected ? "en direct" : "déconnectée"}
        </span>
        <span
          className={`ml-auto h-2 w-2 rounded-full ${
            connected ? "animate-pulse bg-brand" : "bg-rose-500"
          }`}
        />
      </div>
    </aside>
  );
}
