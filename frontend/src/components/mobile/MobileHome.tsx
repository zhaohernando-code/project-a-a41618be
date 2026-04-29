import { PlusOutlined, QuestionCircleOutlined, ReloadOutlined } from "@ant-design/icons";
import { Button, Empty, Popover, Space, Tag, Typography } from "antd";
import { useMemo } from "react";
import type { MobileAppShellProps } from "./types";
import { MobileMetric } from "./MobileMetric";
import { MobileStockRow } from "./MobileStockRow";
import { directionColor, formatDate, formatNumber, formatPercent, valueTone } from "../../utils/format";
import { claimGateStatusLabel, sanitizeDisplayText, validationStatusLabel } from "../../utils/labels";

const { Text, Title } = Typography;

export function MobileHome(props: MobileAppShellProps) {
  const holdingSymbols = useMemo(
    () => new Set(props.simulation?.manual_track.portfolio.holdings.filter((item) => item.quantity > 0).map((item) => item.symbol) ?? []),
    [props.simulation],
  );
  const rows = props.candidateRows;
  const activeCandidate = props.activeRow?.candidate ?? null;
  const openActive = () => {
    if (props.activeRow) {
      props.onSelectSymbol(props.activeRow.symbol, "stock");
    }
  };
  const openQuestionAssistant = () => {
    if (!props.activeRow) {
      return;
    }
    props.setStockPanel?.("question");
    props.onSelectSymbol(props.activeRow.symbol, "stock");
  };

  return (
    <main className="mobile-page mobile-page-home">
      <header className="mobile-app-top-bar">
        <span aria-hidden="true" />
        <strong>工作台</strong>
        <Button className="mobile-icon-button" type="text" icon={<ReloadOutlined />} onClick={() => void props.onRefresh()} />
      </header>

      <section
        className="mobile-hero-card mobile-focus-card"
        role={props.activeRow ? "button" : undefined}
        tabIndex={props.activeRow ? 0 : undefined}
        onClick={openActive}
        onKeyDown={(event) => {
          if ((event.key === "Enter" || event.key === " ") && props.activeRow) {
            openActive();
          }
        }}
      >
        <div className="mobile-card-kicker mobile-card-kicker-inverse">当前焦点</div>
        <div className="mobile-focus-title">
          <div>
            <Title level={3}>{props.activeRow?.name ?? "暂无标的"}</Title>
            <Text>{props.activeRow?.symbol ?? "--"} · {activeCandidate?.sector ?? props.activeRow?.exchange ?? "等待数据"}</Text>
          </div>
          <div className="mobile-focus-price">
            <strong>{formatNumber(activeCandidate?.last_close)}</strong>
          </div>
        </div>
        <Space wrap className="mobile-chip-row">
          {activeCandidate ? <Tag color={directionColor(activeCandidate.display_direction)}>{activeCandidate.display_direction_label}</Tag> : <Tag>等待分析</Tag>}
          {activeCandidate ? <Tag>{claimGateStatusLabel(activeCandidate.claim_gate.status)}</Tag> : null}
          {activeCandidate ? <Tag>{validationStatusLabel(activeCandidate.validation_status)}</Tag> : null}
        </Space>
        <p>{activeCandidate?.summary ? sanitizeDisplayText(activeCandidate.summary) : "当前没有最新候选信号，可刷新自选池后查看。"}</p>
        <div className="mobile-metric-grid mobile-metric-grid-glass">
          <MobileMetric label="20日" value={formatPercent(activeCandidate?.price_return_20d)} tone={valueTone(activeCandidate?.price_return_20d)} />
          <MobileMetric label="置信" value={activeCandidate?.confidence_label ?? "--"} />
          <MobileMetric label="刷新时间" value={formatDate(props.activeRow?.last_analyzed_at ?? props.activeRow?.updated_at)} />
        </div>
      </section>

      <section className="mobile-list-panel mobile-section-plain">
        <div className="mobile-section-head">
          <div>
            <Title level={4}>关注股票</Title>
            <Text>{`${rows.length} 只符合筛选`}</Text>
          </div>
          <span className="mobile-section-link">向上滑看全部</span>
        </div>
        <div className="mobile-stock-list">
          {rows.length > 0 ? rows.map((row) => (
            <MobileStockRow
              key={row.symbol}
              row={row}
              active={row.symbol === props.selectedSymbol}
              holding={holdingSymbols.has(row.symbol)}
              onOpen={() => props.onSelectSymbol(row.symbol, "stock")}
              onRemove={row.source_kind !== "candidate_only" ? () => props.onRequestRemoveWatchlist?.(row) : undefined}
              removing={props.mutatingWatchlist && props.watchlistMutationSymbol === row.symbol}
            />
          )) : <Empty description="没有符合条件的标的" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
        </div>
      </section>

      <section className="mobile-quick-actions mobile-section-plain">
        <div className="mobile-section-head">
          <div>
            <Title level={4}>快速操作</Title>
          </div>
        </div>
        <div className="mobile-quick-grid">
          <Popover
            open={props.addPopoverOpen}
            onOpenChange={props.setAddPopoverOpen}
            trigger="click"
            placement="top"
            content={props.addWatchlistOverlay}
          >
            <button type="button">
              <PlusOutlined />
              <span>添加自选</span>
            </button>
          </Popover>
          <button type="button" onClick={() => void props.onRefresh()}>
            <ReloadOutlined />
            <span>刷新数据</span>
          </button>
          <button type="button" onClick={openQuestionAssistant} disabled={!props.activeRow}>
            <QuestionCircleOutlined />
            <span>提问助手</span>
          </button>
        </div>
      </section>
    </main>
  );
}
