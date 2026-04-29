import { FilterOutlined, PlusOutlined, ReloadOutlined, SearchOutlined, SyncOutlined } from "@ant-design/icons";
import { Button, Empty, Input, Popover, Space, Tag, Typography } from "antd";
import { useMemo, useState } from "react";
import type { MobileAppShellProps, MobileListFilter } from "./types";
import { MobileMetric } from "./MobileMetric";
import { MobileStockRow } from "./MobileStockRow";
import { directionColor, formatDate, formatNumber, formatPercent, valueTone } from "../../utils/format";
import { claimGateStatusLabel, sanitizeDisplayText, validationStatusLabel } from "../../utils/labels";

const { Text, Title } = Typography;

export function MobileHome(props: MobileAppShellProps) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<MobileListFilter>("all");
  const holdingSymbols = useMemo(
    () => new Set(props.simulation?.manual_track.portfolio.holdings.filter((item) => item.quantity > 0).map((item) => item.symbol) ?? []),
    [props.simulation],
  );
  const rows = useMemo(() => {
    const normalized = query.trim().toUpperCase();
    return props.candidateRows.filter((row) => {
      const matchesQuery = !normalized
        || row.symbol.toUpperCase().includes(normalized)
        || row.name.toUpperCase().includes(normalized);
      if (!matchesQuery) return false;
      if (filter === "candidate") return Boolean(row.candidate);
      if (filter === "holding") return holdingSymbols.has(row.symbol);
      if (filter === "risk") {
        const text = `${row.candidate?.display_direction_label ?? ""}${row.candidate?.claim_gate.status ?? ""}${row.analysis_status}`;
        return text.includes("谨慎") || text.includes("风险") || text.includes("观察") || text.includes("insufficient");
      }
      return true;
    });
  }, [filter, holdingSymbols, props.candidateRows, query]);
  const activeCandidate = props.activeRow?.candidate ?? null;

  return (
    <main className="mobile-page mobile-page-home">
      <header className="mobile-page-head">
        <div>
          <Text className="mobile-kicker">A-Share Advisory</Text>
          <Title level={2}>工作台</Title>
          <Text>{`自选与候选合并 · ${props.candidateRows.length} 只`}</Text>
        </div>
        <Button shape="circle" icon={<ReloadOutlined />} onClick={() => void props.onRefresh()} />
      </header>

      <section className="mobile-hero-card">
        <div className="mobile-card-kicker">当前焦点</div>
        <div className="mobile-focus-title">
          <div>
            <Title level={3}>{props.activeRow?.name ?? "暂无标的"}</Title>
            <Text>{props.activeRow?.symbol ?? "--"}</Text>
          </div>
          <div className="mobile-focus-price">
            <strong>{formatNumber(activeCandidate?.last_close)}</strong>
            <span className={`value-${valueTone(activeCandidate?.price_return_20d)}`}>
              {formatPercent(activeCandidate?.price_return_20d)}
            </span>
          </div>
        </div>
        <Space wrap className="mobile-chip-row">
          {activeCandidate ? <Tag color={directionColor(activeCandidate.display_direction)}>{activeCandidate.display_direction_label}</Tag> : <Tag>等待分析</Tag>}
          {activeCandidate ? <Tag>{claimGateStatusLabel(activeCandidate.claim_gate.status)}</Tag> : null}
          {activeCandidate ? <Tag>{validationStatusLabel(activeCandidate.validation_status)}</Tag> : null}
        </Space>
        <p>{activeCandidate?.summary ? sanitizeDisplayText(activeCandidate.summary) : "当前没有最新候选信号，可刷新自选池后查看。"}</p>
        <div className="mobile-metric-grid">
          <MobileMetric label="20日" value={formatPercent(activeCandidate?.price_return_20d)} tone={valueTone(activeCandidate?.price_return_20d)} />
          <MobileMetric label="置信" value={activeCandidate?.confidence_label ?? "--"} />
          <MobileMetric label="刷新" value={formatDate(props.activeRow?.last_analyzed_at ?? props.activeRow?.updated_at)} />
        </div>
        <div className="mobile-action-row">
          <Button type="primary" onClick={() => props.activeRow && props.onSelectSymbol(props.activeRow.symbol, "stock")}>
            打开单票
          </Button>
          <Button
            icon={<SyncOutlined />}
            disabled={!props.activeRow || props.activeRow.source_kind === "candidate_only"}
            loading={props.mutatingWatchlist && props.watchlistMutationSymbol === props.activeRow?.symbol}
            onClick={() => props.activeRow && void props.onRefreshWatchlist(props.activeRow.symbol)}
          >
            重分析
          </Button>
          <Popover
            open={props.addPopoverOpen}
            onOpenChange={props.setAddPopoverOpen}
            trigger="click"
            placement="bottomRight"
            content={props.addWatchlistOverlay}
          >
            <Button icon={<PlusOutlined />}>添加</Button>
          </Popover>
        </div>
      </section>

      <section className="mobile-list-panel">
        <div className="mobile-section-head">
          <div>
            <Title level={4}>候选与自选</Title>
            <Text>{`${rows.length} 只符合筛选`}</Text>
          </div>
          <FilterOutlined />
        </div>
        <Input
          className="mobile-search"
          prefix={<SearchOutlined />}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索股票 / 代码"
        />
        <div className="mobile-segmented">
          {([
            ["all", "全部"],
            ["candidate", "候选"],
            ["holding", "持仓"],
            ["risk", "风险"],
          ] as Array<[MobileListFilter, string]>).map(([key, label]) => (
            <button key={key} type="button" className={filter === key ? "active" : ""} onClick={() => setFilter(key)}>
              {label}
            </button>
          ))}
        </div>
        <div className="mobile-stock-list">
          {rows.length > 0 ? rows.map((row) => (
            <MobileStockRow
              key={row.symbol}
              row={row}
              active={row.symbol === props.selectedSymbol}
              holding={holdingSymbols.has(row.symbol)}
              onOpen={() => props.onSelectSymbol(row.symbol, "stock")}
            />
          )) : <Empty description="没有符合条件的标的" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
        </div>
      </section>
    </main>
  );
}
