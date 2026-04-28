import { Button, Form, Input, Popover, Space, Typography } from "antd";
import { PlusOutlined } from "@ant-design/icons";

const { Text } = Typography;

export interface BuildAddWatchlistOverlayInput {
  addPopoverOpen: boolean;
  setAddPopoverOpen: (v: boolean) => void;
  watchlistSymbolDraft: string;
  setWatchlistSymbolDraft: (v: string) => void;
  watchlistNameDraft: string;
  setWatchlistNameDraft: (v: string) => void;
  handleAddWatchlist: (e?: React.MouseEvent) => Promise<void>;
  canMutateWatchlist: boolean;
  mutatingWatchlist: boolean;
}

export function buildAddWatchlistOverlay(input: BuildAddWatchlistOverlayInput) {
  const {
    addPopoverOpen, setAddPopoverOpen,
    watchlistSymbolDraft, setWatchlistSymbolDraft,
    watchlistNameDraft, setWatchlistNameDraft,
    handleAddWatchlist, canMutateWatchlist, mutatingWatchlist,
  } = input;

  return (
    <div className="watchlist-add-popover">
      <Form layout="vertical" size="small">
        <Form.Item label="股票代码">
          <Input
            value={watchlistSymbolDraft}
            onChange={(event) => setWatchlistSymbolDraft(event.target.value)}
            placeholder="如 600519 或 300750.SZ"
          />
        </Form.Item>
        <Form.Item label="显示名称">
          <Input
            value={watchlistNameDraft}
            onChange={(event) => setWatchlistNameDraft(event.target.value)}
            placeholder="可选：自定义显示名称"
          />
        </Form.Item>
      </Form>
      <div className="watchlist-add-actions">
        <Button size="small" onClick={() => setAddPopoverOpen(false)}>
          取消
        </Button>
        <Button
          type="primary"
          size="small"
          icon={<PlusOutlined />}
          loading={mutatingWatchlist}
          onClick={() => void handleAddWatchlist()}
        >
          加入并分析
        </Button>
      </div>
    </div>
  );
}
