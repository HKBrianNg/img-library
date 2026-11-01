# openEDU/admin/main.py
# -*- coding: utf-8 -*-
import os
import sys

# ─── 必須在導入 PySide6 之前設定 Chromium 參數 ─────────────
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--ignore-certificate-errors "
    "--log-level=3 "
    "--disable-gpu "
    "--no-sandbox"
)

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter,
    QTreeWidget, QTreeWidgetItem, QTextBrowser,
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QStatusBar, QComboBox
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import Qt, QUrl, QThread, Signal

# ─── 隱藏名單 ─────────────────────────────────────────────
HIDDEN_NAMES = {
    ".vscode", "admin", "public", "readme.md", "tts_admin",
    ".venv", "__pycache__", ".git", ".idea", "node_modules"
}

# ─── Repo 基礎設定 ───────────────────────────────────────
GITHUB_USER = "HKBrianNg"
REPO_NAME = "img-library"
BRANCH = "main"
CDN_PATH_PREFIX = "openEDU"
PURGE_BASE = "https://purge.jsdelivr.net"

# ✅ 只保留你測試可用的兩個 jsdelivr 節點，均支援清緩存
CDN_OPTIONS = [
    ("fastly.jsdelivr.net", f"https://fastly.jsdelivr.net/gh/{GITHUB_USER}/{REPO_NAME}@{BRANCH}"),
    ("gcore.jsdelivr.net", f"https://gcore.jsdelivr.net/gh/{GITHUB_USER}/{REPO_NAME}@{BRANCH}")
]

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://github.com/",
    "Sec-Fetch-Mode": "no-cors",
    "Sec-Fetch-Site": "cross-site",
    "Connection": "keep-alive"
}

LOCAL_BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def local_to_cdn_url(local_path, cdn_base):
    rel = os.path.relpath(local_path, LOCAL_BASE).replace("\\", "/").strip("/")
    return f"{cdn_base}/{CDN_PATH_PREFIX}/{rel}"

def local_to_purge_url(local_path, cdn_base):
    cdn_url = local_to_cdn_url(local_path, cdn_base)
    if "jsdelivr.net" in cdn_base:
        return f"{PURGE_BASE}/{cdn_url}"
    return ""

def purge_cdn(purge_url):
    if not purge_url:
        return False
    try:
        r = requests.get(purge_url, headers=BROWSER_HEADERS, timeout=10, verify=False)
        return r.status_code in (200, 204)
    except Exception:
        return False

# ─── 自定義 WebPage ───────────────────────────────────────
class CustomWebPage(QWebEnginePage):
    def certificateError(self, error):
        return True

# ─── CDN 探測線程 ─────────────────────────────────────────
class CdnProbeThread(QThread):
    result_signal = Signal(str, str, int)

    def __init__(self, url):
        super().__init__()
        self.url = url
        self.max_retry = 2

    def run(self):
        retry = 0
        while retry <= self.max_retry:
            try:
                head_r = requests.head(
                    self.url,
                    headers=BROWSER_HEADERS,
                    timeout=8,
                    verify=False,
                    allow_redirects=True
                )
                if head_r.status_code != 200:
                    self.result_signal.emit(self.url, f"⚠️ HTTP {head_r.status_code}", head_r.status_code)
                    return

                with requests.get(
                    self.url,
                    headers=BROWSER_HEADERS,
                    timeout=10,
                    verify=False,
                    stream=True
                ) as r:
                    r.raise_for_status()
                    chunk_count = 0
                    for _ in r.iter_content(chunk_size=4096):
                        chunk_count += 1
                        if chunk_count >= 8:
                            break
                self.result_signal.emit(self.url, "✅ 成功（HEAD+Stream驗證）", 200)
                return

            except requests.exceptions.ConnectionError:
                retry += 1
                if retry > self.max_retry:
                    self.result_signal.emit(self.url, "❌ 連線被重置/中斷", 0)
            except requests.exceptions.Timeout:
                retry += 1
                if retry > self.max_retry:
                    self.result_signal.emit(self.url, "❌ 逾時", 0)
            except requests.exceptions.SSLError:
                retry += 1
                if retry > self.max_retry:
                    self.result_signal.emit(self.url, "❌ SSL錯誤", 0)
            except Exception as e:
                retry += 1
                if retry > self.max_retry:
                    self.result_signal.emit(self.url, f"❌ {str(e)[:40]}", 0)

# ─── 主視窗 ───────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("openEDU · CDN Manager")
        self.resize(1400, 850)
        self.current_path = ""
        self.current_url = ""
        self.probe_thread = None
        self.selected_cdn_base = CDN_OPTIONS[0][1]

        self._build_top_bar()
        self._build_body()
        self._load_tree()

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("✅ 就緒")
        self._apply_style()

    def _build_top_bar(self):
        top_widget = QWidget()
        layout = QHBoxLayout(top_widget)
        layout.setContentsMargins(10, 6, 10, 6)

        self.cdn_combo = QComboBox()
        for name, url in CDN_OPTIONS:
            self.cdn_combo.addItem(name, url)
        self.cdn_combo.currentIndexChanged.connect(self.on_cdn_changed)

        self.btn_probe = QPushButton("🔍 探測 CDN")
        self.btn_purge = QPushButton("🗑 清緩存")
        self.btn_open = QPushButton("🌐 瀏覽器打開")
        self.btn_probe.setEnabled(False)
        self.btn_purge.setEnabled(False)

        self.btn_probe.clicked.connect(self.on_probe)
        self.btn_purge.clicked.connect(self.on_purge)
        self.btn_open.clicked.connect(self.on_open_browser)

        self.label_status = QLabel("狀態：等待選擇文件")
        self.label_status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.label_status.setStyleSheet("color:#aaa; font-weight:bold; padding-right:8px;")

        layout.addWidget(QLabel("CDN:"))
        layout.addWidget(self.cdn_combo)
        layout.addWidget(self.btn_probe)
        layout.addWidget(self.btn_purge)
        layout.addWidget(self.btn_open)
        layout.addStretch(1)
        layout.addWidget(self.label_status)

        self.setMenuWidget(top_widget)

    def on_cdn_changed(self):
        self.selected_cdn_base = self.cdn_combo.currentData()
        if self.current_path and not os.path.isdir(self.current_path):
            self.current_url = local_to_cdn_url(self.current_path, self.selected_cdn_base)
            self.info_cdn.setHtml(
                f"<b>☁️ CDN 鏡像</b><br>"
                f"<b>URL:</b> <a href='{self.current_url}'>{self.current_url}</a><br>"
                f"<b>狀態:</b> 等待探測"
            )
            self.view_cdn.setHtml("<center><p>點擊「🔍 探測 CDN」載入預覽</p></center>")
            self.btn_purge.setEnabled(False)

    def _build_body(self):
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("📁 本地目錄")
        self.tree.setMinimumWidth(220)
        self.tree.itemClicked.connect(self.on_item_click)
        self.tree.itemDoubleClicked.connect(self.on_item_double)

        widget_local = QWidget()
        lay_local = QVBoxLayout(widget_local)
        lay_local.setContentsMargins(4,4,4,4)
        self.info_local = QTextBrowser()
        self.info_local.setMaximumHeight(160)
        self.info_local.setHtml("<b>📄 本地資訊</b><br>請選擇檔案或資料夾")
        self.view_local = QWebEngineView()
        self.view_local.setPage(CustomWebPage(self))
        lay_local.addWidget(QLabel("📄 本地資訊"))
        lay_local.addWidget(self.info_local)
        lay_local.addWidget(QLabel("👁 本地預覽"))
        lay_local.addWidget(self.view_local, 1)

        widget_cdn = QWidget()
        lay_cdn = QVBoxLayout(widget_cdn)
        lay_cdn.setContentsMargins(4,4,4,4)
        self.info_cdn = QTextBrowser()
        self.info_cdn.setMaximumHeight(160)
        self.info_cdn.setOpenExternalLinks(True)
        self.info_cdn.setHtml("<b>☁️ CDN 鏡像資訊</b><br>等待選擇檔案")
        self.view_cdn = QWebEngineView()
        self.view_cdn.setPage(CustomWebPage(self))
        lay_cdn.addWidget(QLabel("☁️ CDN 鏡像資訊"))
        lay_cdn.addWidget(self.info_cdn)
        lay_cdn.addWidget(QLabel("🌐 CDN 預覽"))
        lay_cdn.addWidget(self.view_cdn, 1)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.tree)
        splitter.addWidget(widget_local)
        splitter.addWidget(widget_cdn)
        splitter.setStretchFactor(0,1)
        splitter.setStretchFactor(1,1)
        splitter.setStretchFactor(2,1)
        splitter.setSizes([400,500,500])

        self.setCentralWidget(splitter)

    def _load_tree(self):
        root_name = os.path.basename(LOCAL_BASE) or "openEDU"
        root_item = QTreeWidgetItem([f"📁 {root_name}"])
        root_item.setData(0, Qt.UserRole, LOCAL_BASE)
        self.tree.addTopLevelItem(root_item)
        self._scan_dir(LOCAL_BASE, root_item)
        root_item.setExpanded(True)

    def _scan_dir(self, path, parent_item):
        try:
            for name in sorted(os.listdir(path)):
                if name.lower() in HIDDEN_NAMES:
                    continue
                full = os.path.join(path, name)
                if os.path.isdir(full):
                    item = QTreeWidgetItem([f"📁 {name}"])
                    item.setData(0, Qt.UserRole, full)
                    parent_item.addChild(item)
                    self._scan_dir(full, item)
                else:
                    ext = name.split(".")[-1].lower()
                    icon = "📄"
                    if ext in ("jpg","png","gif","webp","svg"):
                        icon = "🖼️"
                    elif ext in ("mp3","wav","ogg","m4a"):
                        icon = "🎵"
                    elif ext in ("mp4","webm"):
                        icon = "🎬"
                    elif ext in ("json","lrc","txt","md"):
                        icon = "📋"
                    item = QTreeWidgetItem([f"{icon} {name}"])
                    item.setData(0, Qt.UserRole, full)
                    parent_item.addChild(item)
        except PermissionError:
            pass

    def on_item_click(self, item):
        self.current_path = item.data(0, Qt.UserRole)
        name = os.path.basename(self.current_path)
        is_dir = os.path.isdir(self.current_path)

        if is_dir:
            self.info_local.setHtml(f"<b>📁 資料夾</b><br>名稱:{name}<br>路徑:{self.current_path}")
            self.view_local.setHtml("<center><h3>📁 資料夾</h3></center>")
            self.current_url = ""
            self.info_cdn.setHtml("<b>☁️ CDN</b><br>請選擇檔案")
            self.view_cdn.setHtml("<center><h2>📁 資料夾</h2></center>")
            self.btn_probe.setEnabled(False)
            self.btn_purge.setEnabled(False)
            self.label_status.setText("狀態：已選資料夾")
        else:
            ext = name.split(".")[-1].lower()
            self.info_local.setHtml(f"<b>📄 檔案</b><br>名稱:{name}<br>類型:{ext}<br>路徑:{self.current_path}")
            self.view_local.setUrl(QUrl.fromLocalFile(self.current_path))
            self.current_url = local_to_cdn_url(self.current_path, self.selected_cdn_base)
            self.info_cdn.setHtml(
                f"<b>☁️ CDN 鏡像</b><br>"
                f"<b>URL:</b> <a href='{self.current_url}'>{self.current_url}</a><br>"
                f"<b>狀態:</b> 等待探測"
            )
            self.view_cdn.setHtml("<center><p>點擊「🔍 探測 CDN」載入預覽</p></center>")
            self.btn_probe.setEnabled(True)
            self.btn_purge.setEnabled(False)
            self.label_status.setText(f"狀態：已選檔案 ({ext})")

    def on_item_double(self, item):
        pass

    def on_probe(self):
        if not self.current_url:
            return
        self.label_status.setText("狀態：探測中...")
        self.info_cdn.setHtml(
            f"<b>☁️ CDN 鏡像</b><br>"
            f"<b>URL:</b> <a href='{self.current_url}'>{self.current_url}</a><br>"
            f"<b>狀態:</b> 探測中..."
        )
        self.view_cdn.setHtml("<center><p>探測驗證中...</p></center>")

        if self.probe_thread and self.probe_thread.isRunning():
            self.probe_thread.quit()
            self.probe_thread.wait(1000)

        self.probe_thread = CdnProbeThread(self.current_url)
        self.probe_thread.result_signal.connect(self.on_probe_done)
        self.probe_thread.start()

    def on_probe_done(self, url, msg, code):
        self.label_status.setText(f"狀態：{msg}")
        self.info_cdn.setHtml(
            f"<b>☁️ CDN 鏡像</b><br>"
            f"<b>URL:</b> <a href='{url}'>{url}</a><br>"
            f"<b>狀態:</b> {msg}<br>"
            f"<b>HTTP:</b> {code}"
        )
        self.btn_purge.setEnabled(code == 200 and "jsdelivr.net" in self.selected_cdn_base)
        if code == 200:
            self.view_cdn.setUrl(QUrl(url))
        else:
            self.view_cdn.setHtml("<center><h2>❌ 載入失敗</h2></center>")
        self.statusBar().showMessage(f"📋 探測完成：{msg}")

    def on_purge(self):
        purge_url = local_to_purge_url(self.current_path, self.selected_cdn_base)
        ok = purge_cdn(purge_url)
        text = "🗑 清緩存：成功" if ok else "🗑 清緩存：失敗"
        self.label_status.setText(f"狀態：{text}")
        self.statusBar().showMessage(text)

    def on_open_browser(self):
        if self.current_url:
            QDesktopServices.openUrl(QUrl(self.current_url))

    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color:#1e1e1e; color:#d4d4d4;
                font-family:"Segoe UI",sans-serif; font-size:13px;
            }
            QPushButton {
                background-color:#333; color:#fff; border:1px solid #555;
                padding:6px 12px; border-radius:3px;
            }
            QPushButton:hover { background-color:#444; }
            QPushButton:disabled { color:#888; border-color:#333; }
            QTreeWidget {
                background-color:#252526; color:#d4d4d4; border:1px solid #333;
            }
            QTreeWidget::item:selected { background-color:#094771; color:white; }
            QTreeWidget::item:hover { background-color:#2a2d2e; }
            QTextBrowser {
                background-color:#252526; color:#fff; border:1px solid #333;
            }
            QTextBrowser a { color:#66b3ff; }
            QSplitter::handle { background-color:#444; }
            QStatusBar { background-color:#007acc; color:white; padding:4px; }
            QComboBox {
                background-color:#333; color:#fff; border:1px solid #555;
                padding:4px; border-radius:3px;
            }
        """)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
