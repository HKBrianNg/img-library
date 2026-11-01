# openEDU/admin/cdn_manager.py
# ──────────────────────────────────────────────────────────────
import os
import sys
import json
import threading
import webbrowser
from io import BytesIO

import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    LOCAL_BASE, is_skipped, local_to_cdn_url,
    local_to_purge_url, purge_cdn,
)

# ─── WebView2 檢查 ──────────────────────────────────────────
_tkwebview2_available = False
WebView2 = None
try:
    from tkwebview2.tkwebview2 import WebView2, have_runtime
    _tkwebview2_available = True
except ImportError:
    pass

# ─── 音頻播放（本地用）─────────────────────────────────────
_audio_initialized = False

def _init_audio():
    global _audio_initialized
    if not _audio_initialized:
        try:
            import pygame
            pygame.mixer.init()
            _audio_initialized = True
        except Exception:
            pass

def _play_local_audio(path):
    _init_audio()
    try:
        import pygame
        pygame.mixer.music.stop()
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
        return True
    except Exception:
        return False

def _stop_audio():
    try:
        import pygame
        pygame.mixer.music.stop()
    except Exception:
        pass

# ─── 主程式 ──────────────────────────────────────────────────
class CdnManager(tk.Frame):
    def __init__(self, master=None):
        super().__init__(master)
        self.master = master
        self.master.title("openEDU · CDN Manager")
        self.master.geometry("1500x900")
        self.pack(fill=tk.BOTH, expand=True)

        self.local_node_map: dict[str, str] = {}
        self.status_map: dict[str, str] = {}
        self.img_cache: list = []
        self.preview_img = None
        self._current_cdn_url = None
        self._current_local_path = None
        self._probe_success = False
        self._webview = None

        self._build_ui()
        self._scan_local()

    # ─── UI ──────────────────────────────────────────────────
    def _build_ui(self):
        # ── 頂部工具列 ──
        top = tk.Frame(self)
        top.pack(side=tk.TOP, fill=tk.X, padx=6, pady=4)

        ttk.Button(top, text="🔍 探測 CDN", command=self.on_probe).pack(side=tk.LEFT, padx=3)
        self.purge_btn = ttk.Button(top, text="🗑 清緩存 (Purge)", command=self.on_purge, state=tk.DISABLED)
        self.purge_btn.pack(side=tk.LEFT, padx=3)
        ttk.Button(top, text="🌐 瀏覽器打開", command=self.on_open).pack(side=tk.LEFT, padx=3)
        ttk.Button(top, text="▶ 播放本地音頻", command=self.on_play_local).pack(side=tk.LEFT, padx=3)
        ttk.Button(top, text="⏹ 停止播放", command=lambda: _stop_audio()).pack(side=tk.LEFT, padx=3)

        # ── 主體 ──
        body = tk.Frame(self)
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=6, pady=(4, 0))

        # 左：樹
        left = tk.LabelFrame(body, text="本地目錄")
        left.pack(side=tk.LEFT, fill=tk.Y, expand=False, padx=2)
        self.local_tree = ttk.Treeview(left, show="tree")
        self.local_tree.column("#0", width=300, minwidth=180, stretch=True)
        self.local_tree.pack(fill=tk.BOTH, expand=True)
        self.local_tree.bind("<<TreeviewSelect>>", self.on_select)

        # 中：本地文件
        mid = tk.LabelFrame(body, text="本地文件")
        mid.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        self.info_text = tk.Text(mid, height=6, wrap=tk.WORD, font=("Consolas", 10))
        self.info_text.pack(fill=tk.X, padx=4, pady=4)
        self.local_view = tk.Frame(mid, relief=tk.SUNKEN, bd=1)
        self.local_view.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.local_preview_lbl = tk.Label(self.local_view, text="（選中文件預覽）", justify=tk.LEFT)
        self.local_preview_lbl.pack(expand=True)

        # 右：CDN 內容（WebView2）
        right = tk.LabelFrame(body, text="CDN 內容")
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)

        # CDN URL 顯示
        cdn_url_frame = tk.Frame(right)
        cdn_url_frame.pack(fill=tk.X, padx=4, pady=(4, 2))
        tk.Label(cdn_url_frame, text="CDN URL:", font=("微軟正黑體", 9, "bold")).pack(side=tk.LEFT, padx=(0, 4))
        self.cdn_url_var = tk.StringVar(value="（尚未探測）")
        self.cdn_url_entry = tk.Entry(cdn_url_frame, textvariable=self.cdn_url_var, state="readonly",
                                       font=("Consolas", 9), fg="#0066CC", relief=tk.FLAT)
        self.cdn_url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # CDN 狀態
        self.cdn_status_lbl = tk.Label(right, text="CDN: 等待探測", anchor=tk.W,
                                        font=("微軟正黑體", 9, "bold"), fg="#888")
        self.cdn_status_lbl.pack(fill=tk.X, padx=4, pady=(0, 2))

        # CDN 預覽區（WebView2 或 fallback Label）
        self.cdn_view = tk.Frame(right, relief=tk.SUNKEN, bd=1)
        self.cdn_view.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))

        if _tkwebview2_available:
            try:
                if have_runtime():
                    self._webview = WebView2(self.cdn_view, width=480, height=400)
                    self._webview.pack(fill=tk.BOTH, expand=True)
                    self._webview.load_html(
                        "<html><body style='font-family:微軟正黑體;color:#999;display:flex;"
                        "justify-content:center;align-items:center;height:100%;margin:0;'>"
                        "（選中文件後點「🔍 探測 CDN」）"
                        "</body></html>"
                    )
                else:
                    self.cdn_preview_lbl = tk.Label(self.cdn_view,
                        text="⚠️ WebView2 Runtime 未安裝\n\n請安裝 Microsoft Edge WebView2 Runtime\n或點「瀏覽器打開」按鈕",
                        justify=tk.CENTER)
                    self.cdn_preview_lbl.pack(expand=True)
            except Exception as e:
                self.cdn_preview_lbl = tk.Label(self.cdn_view,
                    text=f"⚠️ WebView2 初始化失敗:\n{e}\n\n請使用「瀏覽器打開」",
                    justify=tk.CENTER)
                self.cdn_preview_lbl.pack(expand=True)
        else:
            self.cdn_preview_lbl = tk.Label(self.cdn_view,
                text="⚠️ tkwebview2 未安裝\n\npip install tkwebview2\n\n安裝後重啟即可內嵌預覽",
                justify=tk.CENTER)
            self.cdn_preview_lbl.pack(expand=True)

        # ── 底部 message 欄 ──
        bottom = tk.Frame(self, relief=tk.SUNKEN, bd=1)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=6, pady=(4, 6))
        tk.Label(bottom, text="📋 Message:", font=("微軟正黑體", 9, "bold")).pack(side=tk.LEFT, padx=6, pady=4)
        self.msg_lbl = tk.Label(bottom, text="就緒", anchor=tk.W, font=("微軟正黑體", 10), fg="#333")
        self.msg_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6), pady=4)

    # ─── 底部 message ───────────────────────────────────────
    def _set_msg(self, text, color="#333"):
        self.msg_lbl.config(text=text, fg=color)

    # ─── 掃描 ──────────────────────────────────────────────
    def _scan_local(self):
        self.local_tree.delete(*self.local_tree.get_children())
        self.local_node_map.clear()
        root_name = os.path.basename(LOCAL_BASE)
        root_id = self.local_tree.insert("", "end", text=root_name, open=True)
        self.local_node_map[root_id] = LOCAL_BASE
        try:
            for name in sorted(os.listdir(LOCAL_BASE)):
                if is_skipped(name):
                    continue
                self._scan_recursive(os.path.join(LOCAL_BASE, name), root_id)
        except Exception as e:
            print(f"掃描失敗: {e}")

    def _scan_recursive(self, path, parent_id):
        name = os.path.basename(path)
        if is_skipped(name):
            return
        is_dir = os.path.isdir(path)
        icon = "📁 " if is_dir else "📄 "
        iid = self.local_tree.insert(parent_id, "end", text=f"{icon}{name}", open=False)
        self.local_node_map[iid] = path
        if is_dir:
            try:
                for child in sorted(os.listdir(path)):
                    if is_skipped(child):
                        continue
                    self._scan_recursive(os.path.join(path, child), iid)
            except PermissionError:
                pass

    # ─── 選中 ──────────────────────────────────────────────
    def on_select(self, event=None):
        item = self.local_tree.focus()
        path = self.local_node_map.get(item)
        if not path:
            return

        # 重置
        self._current_cdn_url = None
        self._current_local_path = None
        self._probe_success = False
        self.purge_btn.config(state=tk.DISABLED)
        self.cdn_url_var.set("（尚未探測）")
        self.cdn_status_lbl.config(text="CDN: 等待探測", fg="#888")

        if os.path.isdir(path):
            cnt = sum(len(fs) for _, _, fs in os.walk(path))
            self.info_text.delete("1.0", tk.END)
            self.info_text.insert("1.0", f"本地: {path}\n類型: 目錄\n包含: {cnt} 個文件\n\n（選中具體文件進行探測）")
            self.local_preview_lbl.config(image="", text=f"📁 目錄\n{cnt} 個文件")
            if self._webview:
                self._webview.load_html(
                    f"<html><body style='font-family:微軟正黑體;color:#999;display:flex;"
                    f"justify-content:center;align-items:center;height:100%;margin:0;'>"
                    f"📁 目錄無 CDN 預覽<br><br>包含 {cnt} 個文件"
                    f"</body></html>"
                )
            self._set_msg("就緒")
            return

        ext = path.lower().split(".")[-1] if "." in path else ""
        cdn_url = local_to_cdn_url(path)
        local_size = os.path.getsize(path)

        self._current_cdn_url = cdn_url
        self._current_local_path = path

        # 中間：只顯示本地
        self.info_text.delete("1.0", tk.END)
        self.info_text.insert("1.0",
            f"本地: {path}\n"
            f"類型: {ext}  |  大小: {local_size:,} bytes"
        )

        self.cdn_url_var.set(cdn_url)
        self.cdn_status_lbl.config(text="CDN: 等待探測", fg="#888")

        IMG = ("jpg", "jpeg", "png", "gif", "webp")
        AUD = ("mp3", "wav", "ogg", "m4a")
        VID = ("mp4", "webm", "mov")

        if ext in IMG:
            self._preview_image_local(path)
            if self._webview:
                self._webview.load_html(
                    "<html><body style='font-family:微軟正黑體;color:#999;display:flex;"
                    "justify-content:center;align-items:center;height:100%;margin:0;'>"
                    "（點「🔍 探測 CDN」載入圖片）"
                    "</body></html>"
                )
        elif ext == "lrc":
            self._preview_text_local(path, 200)
            if self._webview:
                self._webview.load_html("<html><body style='font-family:微軟正黑體;color:#999;display:flex;justify-content:center;align-items:center;height:100%;margin:0;'>（點「🔍 探測 CDN」載入歌詞）</body></html>")
        elif ext in AUD:
            self._preview_audio_local(path, local_size)
            if self._webview:
                self._webview.load_html("<html><body style='font-family:微軟正黑體;color:#999;display:flex;justify-content:center;align-items:center;height:100%;margin:0;'>（點「🔍 探測 CDN」驗證）</body></html>")
        elif ext in VID:
            self.local_preview_lbl.config(image="", text=f"🎬 {os.path.basename(path)}\n大小: {local_size:,} bytes")
            if self._webview:
                self._webview.load_html("<html><body style='font-family:微軟正黑體;color:#999;display:flex;justify-content:center;align-items:center;height:100%;margin:0;'>（點「🔍 探測 CDN」載入影片）</body></html>")
        elif ext == "json":
            self._preview_text_local(path, 60)
            if self._webview:
                self._webview.load_html("<html><body style='font-family:微軟正黑體;color:#999;display:flex;justify-content:center;align-items:center;height:100%;margin:0;'>（點「🔍 探測 CDN」載入 JSON）</body></html>")
        else:
            self.local_preview_lbl.config(image="", text=f"📄 {os.path.basename(path)}")
            if self._webview:
                self._webview.load_html("<html><body style='font-family:微軟正黑體;color:#999;display:flex;justify-content:center;align-items:center;height:100%;margin:0;'>（不支援預覽）</body></html>")

        self._set_msg("就緒 — 點「🔍 探測 CDN」")

    # ─── 探測（WebView2 直接載入 URL）──────────────────────
    def on_probe(self):
        item = self.local_tree.focus()
        path = self.local_node_map.get(item)
        if not path or os.path.isdir(path):
            messagebox.showinfo("提示", "請選中具體文件")
            return
        url = local_to_cdn_url(path)
        self._current_cdn_url = url
        self._current_local_path = path
        self.purge_btn.config(state=tk.DISABLED)
        self._probe_success = False
        self.cdn_url_var.set(url)
        self.cdn_status_lbl.config(text="CDN: 載入中...", fg="#E67E22")
        self._set_msg(f"載入中: {os.path.basename(path)}", "#E67E22")

        if self._webview:
            # WebView2 直接載入 CDN URL → 能渲染 = 存在
            self._webview.load_url(url)
            # WebView2 沒有回調告訴我們 HTTP code，所以用 requests 輕量探一次只為拿狀態
            threading.Thread(target=self._check_status_only, args=(path, url, item), daemon=True).start()
        else:
            # fallback: 沒有 WebView2 就走舊邏輯
            threading.Thread(target=self._do_probe_fallback, args=(path, url, item), daemon=True).start()

    def _check_status_only(self, path, url, iid):
        """WebView2 已經在載了，這裡只拿狀態更新樹節點和底部 message"""
        ext = path.lower().split(".")[-1] if "." in path else ""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36"
            }
            r = requests.get(url, headers=headers, timeout=10, stream=True)
            if ext in ("mp4", "webm", "mov"):
                r.close()
            code = r.status_code
        except Exception as e:
            code = 0
            msg = str(e)[:60]

        if code in (200, 206):
            self._probe_success = True
            self.after(0, lambda: self.cdn_status_lbl.config(text="CDN: ✅ 內容已載入", fg="#27AE60"))
            self.after(0, lambda: self._set_msg(f"✅ 已載入: {os.path.basename(path)}", "#27AE60"))
            self.after(0, lambda: self.purge_btn.config(state=tk.NORMAL))
            self.after(0, lambda ii=iid: self._update_node_status(ii, "✅"))
        elif code == 404:
            self.after(0, lambda: self.cdn_status_lbl.config(text="CDN: ⚠️ 不存在 (404)", fg="#E74C3C"))
            self.after(0, lambda: self._set_msg(f"⚠️ CDN 不存在: {os.path.basename(path)}", "#E74C3C"))
            self.after(0, lambda ii=iid: self._update_node_status(ii, "⚠️"))
        else:
            self.after(0, lambda c=code: self.cdn_status_lbl.config(
                text=f"CDN: ⚠️ 異常 (HTTP {c})", fg="#E74C3C"))
            self.after(0, lambda c=code: self._set_msg(f"⚠️ CDN 異常 HTTP {c}: {os.path.basename(path)}", "#E74C3C"))
            self.after(0, lambda ii=iid: self._update_node_status(ii, "⚠️"))

    def _do_probe_fallback(self, path, url, iid):
        """沒有 WebView2 時的舊邏輯"""
        ext = path.lower().split(".")[-1] if "." in path else ""
        IMG = ("jpg", "jpeg", "png", "gif", "webp")
        AUD = ("mp3", "wav", "ogg", "m4a")
        VID = ("mp4", "webm", "mov")
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            r = requests.get(url, headers=headers, timeout=12, allow_redirects=True, stream=(ext in VID))
            if ext in VID:
                r.close()
            if r.status_code in (200, 206):
                self._probe_success = True
                if ext in IMG:
                    self.after(0, lambda u=url: self._show_cdn_image_fallback(u))
                    msg = "✅ 圖片存在"
                elif ext == "json":
                    self.after(0, lambda t=r.text[:8000]: self._show_cdn_text_fallback(t))
                    msg = "✅ JSON 存在"
                elif ext == "lrc":
                    self.after(0, lambda t=r.text: self._show_cdn_text_fallback(t))
                    msg = "✅ 歌詞存在"
                elif ext in AUD:
                    self.after(0, lambda u=url: self._show_cdn_audio_fallback(u))
                    msg = "✅ 音頻存在"
                elif ext in VID:
                    self.after(0, lambda u=url: self._show_cdn_video_fallback(u))
                    msg = "✅ 影片存在"
                else:
                    self.after(0, lambda t=r.text[:3000]: self._show_cdn_text_fallback(t))
                    msg = "✅ 文件存在"
                self.after(0, lambda m=msg: self.cdn_status_lbl.config(text=f"CDN: {msg}", fg="#27AE60"))
                self.after(0, lambda m=msg: self._set_msg(f"{msg}: {os.path.basename(path)}", "#27AE60"))
                self.after(0, lambda: self.purge_btn.config(state=tk.NORMAL))
                self.after(0, lambda ii=iid: self._update_node_status(ii, "✅"))
            elif r.status_code == 404:
                self.after(0, lambda: self.cdn_status_lbl.config(text="CDN: ⚠️ 不存在 (404)", fg="#E74C3C"))
                self.after(0, lambda: self._set_msg(f"⚠️ 不存在: {os.path.basename(path)}", "#E74C3C"))
                self.after(0, lambda ii=iid: self._update_node_status(ii, "⚠️"))
            else:
                self.after(0, lambda c=r.status_code: self.cdn_status_lbl.config(text=f"CDN: ⚠️ HTTP {c}", fg="#E74C3C"))
                self.after(0, lambda c=r.status_code: self._set_msg(f"⚠️ HTTP {c}: {os.path.basename(path)}", "#E74C3C"))
                self.after(0, lambda ii=iid: self._update_node_status(ii, "⚠️"))
        except Exception as e:
            self.after(0, lambda: self.cdn_status_lbl.config(text=f"CDN: ⚠️ 錯誤", fg="#E74C3C"))
            self.after(0, lambda e=e: self._set_msg(f"⚠️ {str(e)[:50]}", "#E74C3C"))
            self.after(0, lambda ii=iid: self._update_node_status(ii, "⚠️"))

    def _update_node_status(self, iid, mark):
        try:
            if mark:
                self.status_map[iid] = mark
            mk = self.status_map.get(iid, "")
            old = self.local_tree.item(iid, "text")
            if old and old[0] in ("✅", "❌", "⚠️"):
                base = old.split(" ", 1)[1]
            else:
                base = old
            self.local_tree.item(iid, text=f"{mk} {base}" if mk else base)
        except tk.TclError:
            pass

    # ─── 本地預覽 ────────────────────────────────────────
    def _preview_image_local(self, path):
        try:
            img = Image.open(path)
            img.thumbnail((420, 320))
            self.preview_img = ImageTk.PhotoImage(img)
            self.local_preview_lbl.config(image=self.preview_img, text="")
        except Exception:
            self.local_preview_lbl.config(image="", text="（本地圖片預覽失敗）")

    def _preview_text_local(self, path, max_lines):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = [f.readline() for _ in range(max_lines)]
            self.local_preview_lbl.config(image="", text="".join(lines) or "(空文件)")
        except Exception as e:
            self.local_preview_lbl.config(image="", text=str(e))

    def _preview_audio_local(self, path, size):
        self.local_preview_lbl.config(
            image="",
            text=f"🎵 {os.path.basename(path)}\n大小: {size:,} bytes\n\n點上方「▶ 播放本地音頻」"
        )

    # ─── Fallback 顯示（無 WebView2 時）────────────────────
    def _show_cdn_image_fallback(self, url):
        if not hasattr(self, 'cdn_preview_lbl'):
            return
        self.cdn_preview_lbl.config(image="", text="圖片載入中...")
        def load():
            try:
                r = requests.get(url, timeout=10)
                img = Image.open(BytesIO(r.content))
                img.thumbnail((420, 320))
                ph = ImageTk.PhotoImage(img)
                self.img_cache.append(ph)
                self.after(0, lambda ph=ph: self.cdn_preview_lbl.config(image=ph, text=""))
            except Exception as e:
                self.after(0, lambda e=e: self.cdn_preview_lbl.config(image="", text=f"失敗:\n{e}"))
        threading.Thread(target=load, daemon=True).start()

    def _show_cdn_text_fallback(self, text, max_chars=5000):
        if not hasattr(self, 'cdn_preview_lbl'):
            return
        self.cdn_preview_lbl.config(image="", text=text[:max_chars])

    def _show_cdn_audio_fallback(self, url):
        if not hasattr(self, 'cdn_preview_lbl'):
            return
        for w in self.cdn_view.winfo_children():
            if isinstance(w, (tk.Button, ttk.Button)):
                w.destroy()
        self.cdn_preview_lbl.config(image="", text=f"🎵 CDN 音頻\n\n✅ 已確認存在")
        ttk.Button(self.cdn_view, text="🌐 瀏覽器播放", command=lambda u=url: webbrowser.open(u)) \
            .pack(side=tk.BOTTOM, pady=4)

    def _show_cdn_video_fallback(self, url):
        if not hasattr(self, 'cdn_preview_lbl'):
            return
        for w in self.cdn_view.winfo_children():
            if isinstance(w, (tk.Button, ttk.Button)):
                w.destroy()
        self.cdn_preview_lbl.config(image="", text=f"🎬 CDN 影片\n\n✅ 已確認存在")
        ttk.Button(self.cdn_view, text="🌐 瀏覽器打開", command=lambda u=url: webbrowser.open(u)) \
            .pack(side=tk.BOTTOM, pady=4)

    # ─── 按鈕操作 ────────────────────────────────────────
    def on_play_local(self):
        item = self.local_tree.focus()
        path = self.local_node_map.get(item)
        if not path or os.path.isdir(path):
            messagebox.showinfo("提示", "請先選中音頻文件")
            return
        ext = path.lower().split(".")[-1]
        if ext not in ("mp3", "wav", "ogg", "m4a"):
            messagebox.showinfo("提示", f"不支援播放 .{ext}")
            return
        if _play_local_audio(path):
            self._set_msg(f"▶ 播放中: {os.path.basename(path)}", "#2980B9")
        else:
            self._set_msg("播放失敗（pygame 未安裝或檔案無效）", "#E74C3C")

    def on_purge(self):
        if not self._current_cdn_url or not self._probe_success:
            return
        purge_url = local_to_purge_url(self._current_local_path or self._current_cdn_url)
        self._set_msg(f"清緩存中: {os.path.basename(self._current_local_path or '')}...", "#E67E22")
        def do_purge():
            try:
                ok = purge_cdn(purge_url)
                if ok:
                    self.after(0, lambda: self._set_msg(f"🗑 已提交清緩存: {os.path.basename(self._current_local_path or '')}", "#27AE60"))
                    self.after(0, lambda: messagebox.showinfo("清緩存", f"已提交:\n{purge_url}"))
                else:
                    self.after(0, lambda: self._set_msg("清緩存失敗", "#E74C3C"))
                    self.after(0, lambda: messagebox.showwarning("清緩存", "請求失敗"))
            except Exception as e:
                self.after(0, lambda: self._set_msg(f"錯誤: {e}", "#E74C3C"))
        threading.Thread(target=do_purge, daemon=True).start()

    def on_open(self):
        item = self.local_tree.focus()
        path = self.local_node_map.get(item)
        if not path or os.path.isdir(path):
            return
        webbrowser.open(local_to_cdn_url(path))


if __name__ == "__main__":
    root = tk.Tk()
    app = CdnManager(master=root)
    root.mainloop()