"""Bộ kiểm thử toàn diện cho Thiết kế & Giao diện Android Material Design 3 (KAS v1.8.0):
- Phiên bản thống nhất `1.8.0` trên Python package, PWA Service Worker, Gradle (`versionCode 10800`), và `MainActivity.java`
- Thanh Điều Hướng Đáy Material 3 (`.mobile-nav-pill`), Chip chế độ Máy chủ Android (`#androidTopbarModeBtn`) & Ngăn kéo điều khiển nhanh (`#androidDrawerQuickBar`)
- Trình Duyệt Kho Di Động: Ngăn kéo Cây Thư Mục (`#expTreeToggleBtn`, `#explorerTreePanel`) & Khung Xem Trước Bottom Sheet (`#explorerPreviewSheet`, `#explorerPreviewHandle`, `#explorerSheetBackdrop`)
- CSS Responsive di động chuẩn Material 3: 2x2 KPIs, 1-cột chống tràn ngang, hàng Explorer 2 dòng (`.explorer-table`, `.explorer-mobile-sub`, `.explorer-row-chevron`), Bottom Sheet modals, không màu tím cliché
- JavaScript Engine: đồng bộ thanh hệ thống (`syncAndroidSystemChrome`), rung chạm (`triggerAndroidHaptic`), cử chỉ vuốt (`initMobileTouchGestures`), điều khiển Bottom Sheet / Tree Drawer & chuỗi nút Back Android 6 tầng ưu tiên
- Native Android Shell (`MainActivity.java`, `styles.xml`, `AndroidManifest.xml`, `ic_launcher_background.xml`): nền Obsidian Ink `#0C0E12` không nháy trắng, Splash Screen có thương hiệu + nút Wi-Fi PC, `WindowInsetsController` / `SYSTEM_UI_FLAG_LIGHT_*`, cầu nối `syncSystemTheme` / `hapticTick` / `getDeviceInfo` / `openExternalUrl`
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from karius_academic_system import __version__

REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = REPO_ROOT / "src" / "karius_academic_system" / "web" / "static"
ANDROID_DIR = REPO_ROOT / "packaging" / "android" / "app" / "src" / "main"


class TestV18AndroidMaterialUi(unittest.TestCase):
    def test_v18_version_alignment_across_web_pwa_and_android(self) -> None:
        self.assertEqual(__version__, "1.8.0")

        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        self.assertIn("v1.8.0", html)
        self.assertIn('/static/styles.css?v=1.8.0', html)
        self.assertIn('/static/app.js?v=1.8.0', html)
        self.assertIn('id="themeColorMeta"', html)
        self.assertIn('content="#0c0e12"', html)

        manifest = json.loads((STATIC_DIR / "manifest.webmanifest").read_text(encoding="utf-8"))
        self.assertEqual(manifest["background_color"], "#0c0e12")
        self.assertEqual(manifest["theme_color"], "#0c0e12")

        sw = (STATIC_DIR / "sw.js").read_text(encoding="utf-8")
        self.assertIn("kas-pwa-v1.8.0", sw)
        self.assertIn("/static/styles.css?v=1.8.0", sw)
        self.assertIn("/static/app.js?v=1.8.0", sw)

        gradle = (REPO_ROOT / "packaging" / "android" / "app" / "build.gradle").read_text(encoding="utf-8")
        self.assertIn("versionCode 10800", gradle)
        self.assertIn('versionName "1.8.0"', gradle)

    def test_android_material3_html_shell_structure(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

        # 1. Material 3 Bottom Navigation Bar with active pill indicators (5 destinations)
        self.assertIn('id="mobileBottomNav"', html)
        self.assertEqual(html.count('class="mobile-nav-pill"'), 5)

        # 2. Android Top App Bar server mode chip & Drawer quick controls
        self.assertIn('id="androidTopbarModeBtn"', html)
        self.assertIn('id="androidTopbarModeLabel"', html)
        self.assertIn('id="androidDrawerQuickBar"', html)

        # 3. Mobile Explorer Tree Drawer + Modal Bottom Sheet Previewer (persistent drag handle outside #explorerPreviewPane)
        for dom_id in (
            'id="expTreeToggleBtn"',
            'id="explorerSheetBackdrop"',
            'id="explorerTreePanel"',
            'id="explorerPreviewSheet"',
            'id="explorerPreviewHandle"',
            'id="explorerPreviewCloseBtn"',
            'id="explorerPreviewPane"',
        ):
            self.assertIn(dom_id, html)

        # Ensure #explorerPreviewHandle sits before #explorerPreviewPane inside #explorerPreviewSheet
        sheet_pos = html.index('id="explorerPreviewSheet"')
        handle_pos = html.index('id="explorerPreviewHandle"')
        pane_pos = html.index('id="explorerPreviewPane"')
        self.assertLess(sheet_pos, handle_pos)
        self.assertLess(handle_pos, pane_pos)

    def test_android_material3_responsive_css_rules(self) -> None:
        css = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")

        for selector in (
            ".android-mode-chip",
            ".android-drawer-quick",
            ".exp-tree-toggle-btn",
            ".explorer-sheet-backdrop",
            ".preview-sheet-bar",
            ".preview-sheet-handle",
            ".explorer-mobile-sub",
            ".explorer-row-chevron",
            ".mobile-nav-pill",
            "@media (max-width: 1200px)",
            "@media (max-width: 860px)",
            "@media (max-width: 640px)",
            ".explorer-tree.drawer-open",
            ".explorer-preview.sheet-open",
            ".explorer-table thead",
            ".explorer-table td:nth-child(2)",
            "grid-template-columns: repeat(2, minmax(0, 1fr))",
            "100dvh",
        ):
            self.assertIn(selector, css, f"Missing expected Android Material 3 CSS token: {selector}")

        for forbidden_hex in ("#6366f1", "#8b5cf6", "#a855f7", "#4f46e5"):
            self.assertNotIn(forbidden_hex, css.lower())

    def test_android_material3_js_handlers_and_back_priority(self) -> None:
        js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

        for fn in (
            "function syncAndroidSystemChrome(",
            "function triggerAndroidHaptic(",
            "function openExplorerPreviewSheet(",
            "function closeExplorerPreviewSheet(",
            "function toggleExplorerTreeDrawer(",
            "function closeExplorerMobileSheets(",
            "function initMobileTouchGestures(",
        ):
            self.assertIn(fn, js, f"Missing Android UI JS handler: {fn}")

        # Verify native bridge integration & Back priority chain order
        self.assertIn("window.KASAndroid.syncSystemTheme", js)
        self.assertIn("window.KASAndroid.hapticTick", js)
        self.assertIn("window.KASAndroid.getDeviceInfo", js)
        self.assertIn("window.KASAndroid.openExternalUrl", js)

        back_idx = js.index("window.kasHandleAndroidBack")
        back_block = js[back_idx : back_idx + 1200]
        p_confirm = back_block.index("confirmOverlay")
        p_palette = back_block.index("paletteOverlay")
        p_sheet = back_block.index("explorerPreviewSheet")
        p_tree = back_block.index("explorerTreePanel")
        p_drawer = back_block.index("mobile-nav-open")
        self.assertLess(p_confirm, p_palette)
        self.assertLess(p_palette, p_sheet)
        self.assertLess(p_sheet, p_tree)
        self.assertLess(p_tree, p_drawer)

    def test_native_android_java_shell_and_zero_flash_theme(self) -> None:
        java_src = (
            ANDROID_DIR / "java" / "io" / "github" / "kariusnocr" / "kas" / "MainActivity.java"
        ).read_text(encoding="utf-8")

        for token in (
            'KAS_VERSION = "1.8.0"',
            "#0C0E12",
            "#F6F5F1",
            "WindowInsetsController",
            "APPEARANCE_LIGHT_STATUS_BARS",
            "APPEARANCE_LIGHT_NAVIGATION_BARS",
            "SYSTEM_UI_FLAG_LIGHT_STATUS_BAR",
            "SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR",
            "HapticFeedbackConstants.CLOCK_TICK",
            "public void syncSystemTheme(String theme)",
            "public void hapticTick()",
            "public String getDeviceInfo()",
            "public void openExternalUrl(String url)",
            "Kết nối PC qua Wi-Fi",
            'trimmed.startsWith("https://")',
        ):
            self.assertIn(token, java_src, f"Missing native Android v1.8.0 feature in MainActivity.java: {token}")

        styles_xml = (ANDROID_DIR / "res" / "values" / "styles.xml").read_text(encoding="utf-8")
        self.assertIn('name="KasAppTheme"', styles_xml)
        self.assertIn("#0C0E12", styles_xml)

        manifest_xml = (ANDROID_DIR / "AndroidManifest.xml").read_text(encoding="utf-8")
        self.assertIn('android:theme="@style/KasAppTheme"', manifest_xml)

        icon_bg = (ANDROID_DIR / "res" / "drawable" / "ic_launcher_background.xml").read_text(encoding="utf-8")
        self.assertIn("#0C0E12", icon_bg)


if __name__ == "__main__":
    unittest.main()
