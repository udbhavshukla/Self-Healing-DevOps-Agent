import type { ReactNode } from "react";
import { stateTone, type Tone } from "../labels";

export function Card({
  id,
  title,
  eyebrow,
  action,
  children,
  wide,
}: {
  id?: string;
  title: string;
  eyebrow?: string;
  action?: ReactNode;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <section id={id} className={wide ? "panel wide" : "panel"}>
      <div className="card-head">
        <div>
          {eyebrow !== undefined && (
            <p className="card-eyebrow">{eyebrow}</p>
          )}
          <h2>{title}</h2>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

export function StatusBadge({
  tone,
  children,
}: {
  tone: Tone;
  children: ReactNode;
}) {
  return <span className={`status-badge tone-${tone}`}>{children}</span>;
}

export function StateStatusBadge({ state }: { state: string }) {
  return <StatusBadge tone={stateTone(state)}>{state}</StatusBadge>;
}

export function MetricCard({
  label,
  value,
  sub,
  tone = "neutral",
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: Tone;
}) {
  return (
    <div className={`metric tone-${tone}`}>
      <p className="metric-label">{label}</p>
      <p className="metric-value">{value}</p>
      {sub !== undefined && <p className="metric-sub">{sub}</p>}
    </div>
  );
}
