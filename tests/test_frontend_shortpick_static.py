import unittest
from pathlib import Path


class FrontendShortpickStaticTests(unittest.TestCase):
    def test_shortpick_lab_is_independent_research_surface(self) -> None:
        frontend_root = Path(__file__).resolve().parents[1] / "frontend" / "src"
        app_source = (frontend_root / "App.tsx").read_text(encoding="utf-8")
        component_source = (frontend_root / "components" / "ShortpickLabView.tsx").read_text(encoding="utf-8")
        api_source = (frontend_root / "api" / "shortpick.ts").read_text(encoding="utf-8")

        self.assertIn('label: "试验田"', app_source)
        self.assertIn("<ShortpickLabView canTrigger={isRootUser}", app_source)
        self.assertIn("独立研究课题，不进入主推荐评分", component_source)
        self.assertIn("模型一致性只代表研究优先级，不代表交易建议", component_source)
        self.assertIn("后验验证完成前不得显示为已验证能力", component_source)
        self.assertIn("/shortpick-lab/runs", api_source)
        self.assertIn("/shortpick-lab/candidates", api_source)
        self.assertNotIn("addWatchlist", component_source)
        self.assertNotIn("getStockDashboard", component_source)


if __name__ == "__main__":
    unittest.main()
