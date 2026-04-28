import { formatSignedNumber, formatPercent, valueTone } from "../utils/format";

export function PnlStack({
  amount,
  percent,
}: {
  amount?: number | null;
  percent?: number | null;
}) {
  const tone = valueTone(amount ?? percent);
  return (
    <div className={`stacked-value stacked-value-${tone}`}>
      <strong>{formatSignedNumber(amount)}</strong>
      <span>{formatPercent(percent)}</span>
    </div>
  );
}

