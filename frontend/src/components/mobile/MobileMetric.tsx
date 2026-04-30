import type { ReactNode } from "react";

export function MobileMetric({
  label,
  value,
  tone,
}: {
  label: string;
  value: ReactNode;
  tone?: "positive" | "negative" | "neutral";
}) {
  return (
    <div className="mobile-metric">
      <span>{label}</span>
      <strong className={tone ? `value-${tone}` : undefined}>{value}</strong>
    </div>
  );
}
