import React from "react";

export function Card({ children, className = "" }) {
  return <div className={`card p-5 ${className}`}>{children}</div>;
}

export function SectionTitle({ icon: Icon, title, subtitle, right }) {
  return (
    <div className="mb-4 flex items-center justify-between">
      <div className="flex items-center gap-3">
        {Icon && (
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-brand/15 text-brand">
            <Icon size={20} />
          </div>
        )}
        <div>
          <h2 className="text-lg font-bold text-white">{title}</h2>
          {subtitle && <p className="text-sm text-slate-400">{subtitle}</p>}
        </div>
      </div>
      {right}
    </div>
  );
}

export function StatCard({ icon: Icon, label, value, unit, accent = "brand", hint }) {
  const accents = {
    brand: "text-brand bg-brand/15",
    blue: "text-sky-400 bg-sky-400/15",
    violet: "text-violet-400 bg-violet-400/15",
    amber: "text-amber-400 bg-amber-400/15",
    rose: "text-rose-400 bg-rose-400/15",
  };
  return (
    <Card className="relative overflow-hidden">
      <div className="flex items-start justify-between">
        <div>
          <p className="label">{label}</p>
          <div className="mt-2 flex items-baseline gap-1">
            <span className="font-mono text-3xl font-bold text-white tabular-nums">
              {value}
            </span>
            {unit && <span className="text-sm text-slate-400">{unit}</span>}
          </div>
          {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
        </div>
        {Icon && (
          <div className={`grid h-11 w-11 place-items-center rounded-xl ${accents[accent]}`}>
            <Icon size={22} />
          </div>
        )}
      </div>
    </Card>
  );
}

export function Badge({ children, tone = "slate" }) {
  const tones = {
    slate: "bg-slate-700/40 text-slate-300",
    green: "bg-brand/20 text-brand",
    red: "bg-rose-500/20 text-rose-300",
    amber: "bg-amber-500/20 text-amber-300",
    blue: "bg-sky-500/20 text-sky-300",
  };
  return <span className={`badge ${tones[tone]}`}>{children}</span>;
}

export function Spinner({ size = 16 }) {
  return (
    <span
      className="inline-block animate-spin rounded-full border-2 border-slate-500 border-t-brand"
      style={{ width: size, height: size }}
    />
  );
}

export function Field({ label, children }) {
  return (
    <label className="block space-y-1.5">
      <span className="label">{label}</span>
      {children}
    </label>
  );
}
