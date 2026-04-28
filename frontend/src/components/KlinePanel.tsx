import { useState } from "react";
import { Button, Select, Space, Tag, Typography, Modal, Descriptions, Empty } from "antd";
const { Text } = Typography;
import type { PricePointView } from "../types";
import { KlineChart } from "./KlineChart";
import { PnlStack } from "./PnlStack";
import { formatDate, formatPercent, formatNumber, formatSignedNumber } from "../utils/format";
import { formatMarketFreshness, sanitizeDisplayText } from "../utils/labels";
import { numberFormatter } from "../utils/constants";
import { valueTone } from "../utils/format";



export function KlinePanel({
  title,
  points,
  lastUpdated,
  stockName,
  isMobile = false,
}: {
  title: string;
  points: PricePointView[];
  lastUpdated?: string | null;
  stockName?: string | null;
  isMobile?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const latest = points[points.length - 1];
  const previous = points[points.length - 2];
  const changePct = latest && previous && previous.close_price
    ? latest.close_price / previous.close_price - 1
    : null;
  const periodHigh = points.length > 0 ? Math.max(...points.map((point) => point.high_price)) : null;
  const periodLow = points.length > 0 ? Math.min(...points.map((point) => point.low_price)) : null;
  const periodChange = latest && points[0]?.close_price
    ? latest.close_price / points[0].close_price - 1
    : null;
  const avgVolume = points.length > 0
    ? points.reduce((sum, point) => sum + point.volume, 0) / points.length
    : null;

  return (
    <>
      <div className="chart-shell compact-chart">
        <KlineChart points={points} compact />
      </div>
      <div className="chart-meta-row chart-meta-row-split">
        <div className="chart-meta-group">
          <span>{stockName ?? "--"}</span>
          <span>{`K 线刷新 ${formatDate(lastUpdated)}`}</span>
          {latest ? <span>{`最新 ${formatNumber(latest.close_price)}`}</span> : null}
        </div>
        <Button type="link" onClick={() => setOpen(true)}>
          弹窗查看
        </Button>
      </div>
      <Modal
        open={open}
        centered
        wrapClassName="workspace-modal workspace-modal-kline"
        width={isMobile ? "calc(100vw - 16px)" : 1280}
        footer={null}
        title={title}
        onCancel={() => setOpen(false)}
      >
        <div className="kline-modal-stack">
          <div className="kline-summary-grid">
            <div className="kline-summary-card">
              <span>最新价</span>
              <strong>{formatNumber(latest?.close_price)}</strong>
            </div>
            <div className="kline-summary-card">
              <span>日变化</span>
              <strong className={`value-${valueTone(changePct)}`}>{formatPercent(changePct)}</strong>
            </div>
            <div className="kline-summary-card">
              <span>日内区间</span>
              <strong>{latest ? `${formatNumber(latest.low_price)} - ${formatNumber(latest.high_price)}` : "--"}</strong>
            </div>
            <div className="kline-summary-card">
              <span>成交量</span>
              <strong>{formatNumber(latest?.volume)}</strong>
            </div>
            <div className="kline-summary-card">
              <span>区间涨跌</span>
              <strong className={`value-${valueTone(periodChange)}`}>{formatPercent(periodChange)}</strong>
            </div>
            <div className="kline-summary-card">
              <span>区间高低</span>
              <strong>{`${formatNumber(periodHigh)} / ${formatNumber(periodLow)}`}</strong>
            </div>
            <div className="kline-summary-card">
              <span>平均成交量</span>
              <strong>{formatNumber(avgVolume)}</strong>
            </div>
            <div className="kline-summary-card">
              <span>交互</span>
              <strong>悬浮 OHLC 与成交量</strong>
            </div>
          </div>
          <div className="chart-shell chart-shell-modal">
            <KlineChart points={points} />
          </div>
          {latest ? (
            <Descriptions size="small" column={{ xs: 1, md: 2, xl: 4 }} className="info-grid">
              <Descriptions.Item label="开盘">{formatNumber(latest.open_price)}</Descriptions.Item>
              <Descriptions.Item label="收盘">{formatNumber(latest.close_price)}</Descriptions.Item>
              <Descriptions.Item label="最高">{formatNumber(latest.high_price)}</Descriptions.Item>
              <Descriptions.Item label="最低">{formatNumber(latest.low_price)}</Descriptions.Item>
              <Descriptions.Item label="成交量">{formatNumber(latest.volume)}</Descriptions.Item>
              <Descriptions.Item label="均量">{formatNumber(avgVolume)}</Descriptions.Item>
              <Descriptions.Item label="区间涨跌">{formatPercent(periodChange)}</Descriptions.Item>
              <Descriptions.Item label="区间高低">{`${formatNumber(periodHigh)} / ${formatNumber(periodLow)}`}</Descriptions.Item>
              <Descriptions.Item label="刷新时间">{formatDate(lastUpdated)}</Descriptions.Item>
              <Descriptions.Item label="鼠标联动">价格与成交量联动十字准星</Descriptions.Item>
              <Descriptions.Item label="均线">保留现有配色并叠加 MA5 / MA10</Descriptions.Item>
              <Descriptions.Item label="交互">悬浮查看 OHLC、缩放区间、按轴联动</Descriptions.Item>
            </Descriptions>
          ) : null}
        </div>
      </Modal>
    </>
  );
}

