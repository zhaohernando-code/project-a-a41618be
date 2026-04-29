import { Tag, Typography } from "antd";
import { useRef, useState, type PointerEvent } from "react";
import type { CandidateWorkspaceRow } from "../../types";
import { directionColor, formatDate, formatNumber, formatPercent, valueTone } from "../../utils/format";
import { claimGateStatusLabel, sanitizeDisplayText } from "../../utils/labels";
import { MobileMiniTrendChart } from "./MobileMiniTrendChart";

const { Text } = Typography;

export function MobileStockRow({
  row,
  active,
  holding,
  onOpen,
  onRemove,
  removing,
}: {
  row: CandidateWorkspaceRow;
  active: boolean;
  holding: boolean;
  onOpen: () => void;
  onRemove?: () => void;
  removing?: boolean;
}) {
  const [revealed, setRevealed] = useState(false);
  const dragStartX = useRef<number | null>(null);
  const dragDeltaX = useRef(0);
  const suppressNextClick = useRef(false);
  const canRemove = Boolean(onRemove);
  const candidate = row.candidate;
  const directionLabel = candidate?.display_direction_label ?? row.latest_direction ?? row.analysis_status;
  const closeSwipe = () => {
    if (revealed) {
      setRevealed(false);
    }
  };
  const handlePointerDown = (event: PointerEvent<HTMLButtonElement>) => {
    if (!canRemove) return;
    dragStartX.current = event.clientX;
    dragDeltaX.current = 0;
  };
  const handlePointerMove = (event: PointerEvent<HTMLButtonElement>) => {
    if (dragStartX.current === null) return;
    dragDeltaX.current = event.clientX - dragStartX.current;
  };
  const handlePointerUp = () => {
    if (!canRemove || dragStartX.current === null) return;
    if (dragDeltaX.current < -42) {
      setRevealed(true);
      suppressNextClick.current = true;
    } else if (dragDeltaX.current > 24) {
      setRevealed(false);
      suppressNextClick.current = true;
    }
    dragStartX.current = null;
    dragDeltaX.current = 0;
  };
  const handleOpen = () => {
    if (suppressNextClick.current) {
      suppressNextClick.current = false;
      return;
    }
    if (revealed) {
      setRevealed(false);
      return;
    }
    onOpen();
  };
  const rowTags = (
    <div className="mobile-stock-row-tags">
      <Tag color={candidate ? directionColor(candidate.display_direction) : "default"}>{directionLabel}</Tag>
      {candidate ? <Tag>{claimGateStatusLabel(candidate.claim_gate.status)}</Tag> : null}
      {holding ? <Tag color="blue">持仓</Tag> : null}
    </div>
  );
  return (
    <div className={`mobile-stock-swipe${revealed ? " mobile-stock-swipe-open" : ""}`}>
      {canRemove ? (
        <button
          type="button"
          className="mobile-stock-remove-action"
          disabled={removing}
          tabIndex={revealed ? 0 : -1}
          aria-hidden={!revealed}
          onClick={(event) => {
            event.stopPropagation();
            closeSwipe();
            onRemove?.();
          }}
        >
          {removing ? "移除中" : "移除"}
        </button>
      ) : null}
      <button
        type="button"
        className={`mobile-stock-row${active ? " mobile-stock-row-active" : ""}`}
        onClick={handleOpen}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
      >
        <div className="mobile-stock-row-layout">
          <div className="mobile-stock-row-copy">
            <div className="mobile-stock-row-meta">
              <Text className="mobile-stock-rank">{candidate?.rank ? `#${candidate.rank}` : row.source_kind === "candidate_only" ? "候选" : "关注"}</Text>
              {rowTags}
            </div>
            <div className="mobile-stock-name-line">
              <strong>{row.name}</strong>
              <span>{row.symbol}</span>
            </div>
            <p>{candidate?.summary ? sanitizeDisplayText(candidate.summary) : "等待候选分析结果。"}</p>
          </div>
          <div className="mobile-stock-row-price" aria-label="20日表现">
            <strong className={`value-${valueTone(candidate?.price_return_20d)}`}>{formatPercent(candidate?.price_return_20d)}</strong>
            <span className={`value-${valueTone(candidate?.price_return_20d)}`}>
              {formatNumber(candidate?.last_close)}
            </span>
            <MobileMiniTrendChart row={row} />
          </div>
        </div>
        <div className="mobile-row-foot">
          <span>{candidate?.sector ?? row.exchange}</span>
          <span>{formatDate(row.last_analyzed_at ?? row.updated_at)}</span>
        </div>
      </button>
    </div>
  );
}
