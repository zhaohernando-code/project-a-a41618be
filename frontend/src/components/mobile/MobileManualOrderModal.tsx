import { Button, Col, Form, Input, InputNumber, Modal, Row, Select } from "antd";
import type { Dispatch, SetStateAction } from "react";
import type { ManualSimulationOrderRequest, PortfolioHoldingView, SimulationModelAdviceView } from "../../types";
import { formatNumber, formatSignedNumber, simulationAdviceActionLabel, valueTone } from "../../utils/format";

const { TextArea } = Input;

export function MobileManualOrderModal({
  open,
  themeMode,
  title,
  watchSymbols,
  symbolNameMap,
  draft,
  setDraft,
  activeHolding,
  activeAdvice,
  submitting,
  onCancel,
  onSubmit,
}: {
  open: boolean;
  themeMode: "light" | "dark";
  title: string;
  watchSymbols: string[];
  symbolNameMap: Map<string, string>;
  draft: ManualSimulationOrderRequest;
  setDraft: Dispatch<SetStateAction<ManualSimulationOrderRequest>>;
  activeHolding: PortfolioHoldingView | null | undefined;
  activeAdvice: SimulationModelAdviceView | null | undefined;
  submitting: boolean;
  onCancel: () => void;
  onSubmit: () => void;
}) {
  const getModalPopupContainer = (trigger: HTMLElement) => trigger.closest(".ant-modal-content") as HTMLElement ?? trigger.parentElement ?? document.body;

  return (
    <Modal
      open={open}
      centered
      zIndex={3200}
      width="calc(100vw - 20px)"
      footer={null}
      rootClassName={`mobile-manual-order-dialog ${themeMode === "dark" ? "mobile-dialog-dark" : ""}`}
      title={title}
      onCancel={onCancel}
    >
      <div className="manual-order-modal mobile-manual-order-modal">
        <div className="manual-order-summary-grid">
          <div className="kline-summary-card">
            <span>当前持股</span>
            <strong>{formatNumber(activeHolding?.quantity ?? 0)}</strong>
          </div>
          <div className="kline-summary-card">
            <span>现价 / 成本</span>
            <strong>{`${formatNumber(activeHolding?.last_price)} / ${activeHolding && activeHolding.avg_cost > 0 ? formatNumber(activeHolding.avg_cost) : "--"}`}</strong>
          </div>
          <div className="kline-summary-card">
            <span>持仓盈亏</span>
            <strong className={`value-${valueTone(activeHolding?.total_pnl)}`}>{formatSignedNumber(activeHolding?.total_pnl)}</strong>
          </div>
          <div className="kline-summary-card">
            <span>模型参考</span>
            <strong>{activeAdvice ? simulationAdviceActionLabel(activeAdvice) : "暂无"}</strong>
          </div>
        </div>
        <Form layout="vertical">
          <Form.Item label="标的">
            <Select
              getPopupContainer={getModalPopupContainer}
              popupClassName="mobile-manual-order-select-popup"
              value={draft.symbol || undefined}
              options={watchSymbols.map((symbol) => ({
                value: symbol,
                label: `${symbolNameMap.get(symbol) ?? symbol} · ${symbol}`,
              }))}
              onChange={(value) => setDraft((current) => ({ ...current, symbol: value }))}
            />
          </Form.Item>
          <Row gutter={[10, 0]}>
            <Col span={12}>
              <Form.Item label="方向">
                <Select
                  getPopupContainer={getModalPopupContainer}
                  popupClassName="mobile-manual-order-select-popup"
                  value={draft.side}
                  options={[
                    { value: "buy", label: "买入" },
                    { value: "sell", label: "卖出" },
                  ]}
                  onChange={(value) => setDraft((current) => ({ ...current, side: value }))}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="数量">
                <InputNumber
                  className="full-width"
                  min={100}
                  step={100}
                  value={draft.quantity}
                  onChange={(value) => setDraft((current) => ({ ...current, quantity: Number(value ?? current.quantity) }))}
                />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item label="限价（可选）">
            <InputNumber
              className="full-width"
              min={0}
              step={0.01}
              value={draft.limit_price ?? undefined}
              onChange={(value) => setDraft((current) => ({ ...current, limit_price: value === null ? null : Number(value) }))}
            />
          </Form.Item>
          <Form.Item label="交易理由">
            <TextArea
              rows={2}
              value={draft.reason}
              onChange={(event) => setDraft((current) => ({ ...current, reason: event.target.value }))}
              placeholder="记录这次模拟交易的理由"
            />
          </Form.Item>
        </Form>
        <Button
          className="mobile-manual-order-submit"
          type="primary"
          block
          loading={submitting}
          onClick={onSubmit}
        >
          提交模拟单
        </Button>
      </div>
    </Modal>
  );
}
