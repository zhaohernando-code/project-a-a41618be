// Display formatters and label maps
const numberFormatter = new Intl.NumberFormat("zh-CN", {
  maximumFractionDigits: 2,
});

const signedNumberFormatter = new Intl.NumberFormat("zh-CN", {
  maximumFractionDigits: 2,
  signDisplay: "always",
});

const percentFormatter = new Intl.NumberFormat("zh-CN", {
  style: "percent",
  maximumFractionDigits: 1,
  signDisplay: "always",
});

const directionLabels: Record<string, string> = {
  buy: "可建仓",
  add: "可加仓",
  watch: "继续观察",
  reduce: "减仓",
  sell: "建议离场",
  risk_alert: "风险提示",
};

const factorLabels: Record<string, string> = {
  price_baseline: "价格基线",
  news_event: "新闻事件",
  fundamental: "基本面",
  manual_review_layer: "人工研究层",
  llm_assessment: "人工研究参考",
  fusion: "融合评分",
};

const manualResearchVerdictOptions = [
  { value: "supports_current_recommendation", label: "支持当前建议" },
  { value: "mixed", label: "部分支持 / 部分保留" },
  { value: "contradicts_current_recommendation", label: "与当前建议冲突" },
  { value: "insufficient_evidence", label: "证据不足" },
];


export { numberFormatter, signedNumberFormatter, percentFormatter };
export { directionLabels, factorLabels, manualResearchVerdictOptions };
