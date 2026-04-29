import unittest
from pathlib import Path


class FrontendMobileStaticTests(unittest.TestCase):
    def test_mobile_shell_uses_app_tabs_and_no_operations_wide_table(self) -> None:
        frontend_root = Path(__file__).resolve().parents[1] / "frontend" / "src"
        app_source = (frontend_root / "App.tsx").read_text(encoding="utf-8")
        main_source = (frontend_root / "main.tsx").read_text(encoding="utf-8")
        shell_source = (frontend_root / "components" / "mobile" / "MobileAppShell.tsx").read_text(encoding="utf-8")
        operations_source = (frontend_root / "components" / "mobile" / "MobileOperations.tsx").read_text(encoding="utf-8")
        mini_trend_source = (frontend_root / "components" / "mobile" / "MobileMiniTrendChart.tsx").read_text(encoding="utf-8")
        mobile_style_source = (frontend_root / "mobile.css").read_text(encoding="utf-8")
        mobile_style_source += "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((frontend_root / "styles" / "mobile").glob("*.css"))
        )

        self.assertIn('import "./mobile.css";', main_source)
        self.assertIn("if (isMobile) {", app_source)
        self.assertIn("<MobileAppShell", app_source)
        self.assertIn('"首页"', shell_source)
        self.assertIn('"单票"', shell_source)
        self.assertIn('"复盘"', shell_source)
        self.assertIn('"设置"', shell_source)
        self.assertNotIn('"自选"', shell_source)
        self.assertNotIn("TrackHoldingsTable", operations_source)
        self.assertNotIn("SimulationTrackCard", operations_source)
        self.assertIn(".mobile-bottom-nav", mobile_style_source)
        self.assertIn(".mobile-app-shell", mobile_style_source)
        self.assertIn("price_chart", mini_trend_source)
        self.assertNotIn("last / (1 + return20d)", mini_trend_source)
        self.assertNotIn("mobile-sparkline", mobile_style_source)
