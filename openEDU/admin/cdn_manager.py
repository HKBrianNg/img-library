# openEDU/admin/cdn_manager.py
# ──────────────────────────────────────────────────────────────
import os
import sys
import json
import threading
import webbrowser
import urllib.request
from io import BytesIO

import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    LOCAL_BASE, is_skipped, local_to_cdn_url,
    local_to_purge_url, probe_cdn, purge_cdn,
)

# ─── 音頻播放 ────────────────────────────────────────────────
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

# ─── JSON 深度比對（僅 JSON 用）─────────────────────────────
def compare_json(data1, data2, path=""):
    diffs = []
    if isinstance(data1, dict) and isinstance(data2, dict):
        for k in sorted(set(data1.keys()) | set(data2.keys())):
            if k not in data1:
                diffs.append(f"本地缺少鍵: {path}.{k}" if path else f"本地缺少鍵: {k}")
            elif k not in data2:
                diffs.append(f"CDN 缺少鍵: {path}.{k}" if path else f"CDN 缺少鍵: {k}")
            else:
                d, sub = compare_json(data1[k], data2[k], f"{path}.{k}" if path else str(k))
                diffs.extend(sub)
    elif isinstance(data1, list) and isinstance(data2, list):
        if len(data1) != len(data2):
            diffs.append(f"列表長度不同: {path} (本地 {len(data1)} vs CDN {len(data2)})")
        for i in range(min(len(data1), len(data2))):
            d, sub = compare_json(data1[i], data2[i], f"{path}[{i}]")
            diffs.extend(sub)
    else:
        if data1 != data2:
            diffs.append(f"值不一致: {path} (本地: {repr(data1)[:40]} | CDN: {repr(data2)[:40]})")
    return (len(diffs) == 0, diffs)

# ─── 主程式 ──────────────────────────────────────────────────
class CdnManager(tk.Frame):
    def __init__(self, master=None):
        super().__init__(master)
        self.master = master
        self.master.title("openEDU · CDN Manager")
        self.master.geometry("1500x850")
        self.pack(fill=tk.BOTH, expand=True)

        self.local_node_map: dict[str, str] = {}
        self.status_map: dict[str, str] = {}
        self.img_cache: list = []
        self.preview_img = None
        self.cdn_img = None
        self._current_audio_path = None

        self._build_ui()
        self._scan_local()

    # ─── UI ──────────────────────────────────────────────────
    def _build_ui(self):
        top = tk.Frame(self)
        top.pack(side=tk.TOP, fill=tk.X, padx=6, pady=4)

        ttk.Button(top, text="🔍 探測 CDN", command=self.on_probe).pack(side=tk.LEFT, padx=3)
        ttk.Button(top, text="🗑 清緩存 (Purge)", command=self.on_purge).pack(side=tk.LEFT, padx=3)
        ttk.Button(top, text="🌐 瀏覽器打開", command=self.on_open).pack(side=tk.LEFT, padx=3)
        ttk.Button(top, text="▶ 播放本地音頻", command=self.on_play_local).pack(side=tk.LEFT, padx=3)
        ttk.Button(top, text="⏹ 停止播放", command=lambda: _stop_audio()).pack(side=tk.LEFT, padx=3)

        self.status_lbl = tk.Label(top, text="就緒", anchor=tk.W, fg="#888")
        self.status_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=12)

        body = tk.Frame(self)
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=6, pady=4)

        # 左：樹
        left = tk.LabelFrame(body, text="本地目錄")
        left.pack(side=tk.LEFT, fill=tk.Y, expand=False, padx=2)
        self.local_tree = ttk.Treeview(left, show="tree")
        self.local_tree.column("#0", width=300, minwidth=180, stretch=True)
        self.local_tree.pack(fill=tk.BOTH, expand=True)
        self.local_tree.bind("<<TreeviewSelect>>", self.on_select)

        # 中：本地
        mid = tk.LabelFrame(body, text="本地文件")
        mid.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        self.info_text = tk.Text(mid, height=7, wrap=tk.WORD, font=("Consolas", 10))
        self.info_text.pack(fill=tk.X, padx=4, pady=4)
        self.local_view = tk.Frame(mid, relief=tk.SUNKEN, bd=1)
        self.local_view.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.local_preview_lbl = tk.Label(self.local_view, text="（選中文件預覽）", justify=tk.LEFT)
        self.local_preview_lbl.pack(expand=True)

        # 右：CDN
        right = tk.LabelFrame(body, text="CDN 內容")
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        self.cdn_info = tk.Text(right, height=7, wrap=tk.WORD, font=("Consolas", 10))
        self.cdn_info.pack(fill=tk.X, padx=4, pady=4)
        self.cdn_view = tk.Frame(right, relief=tk.SUNKEN, bd=1)
        self.cdn_view.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.cdn_preview_lbl = tk.Label(self.cdn_view, text="（CDN 預覽）", justify=tk.LEFT)
        self.cdn_preview_lbl.pack(expand=True)

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

        if os.path.isdir(path):
            cnt = sum(len(fs) for _, _, fs in os.walk(path))
            self.info_text.delete("1.0", tk.END)
            self.info_text.insert("1.0", f"本地: {path}\n類型: 目錄\n包含: {cnt} 個文件\n\n（選中具體文件進行探測/預覽）")
            self.local_preview_lbl.config(image="", text=f"📁 目錄\n{cnt} 個文件")
            self.cdn_preview_lbl.config(image="", text="（目錄無 CDN 預覽）")
            self.cdn_info.delete("1.0", tk.END)
            return

        ext = path.lower().split(".")[-1] if "." in path else ""
        cdn_url = local_to_cdn_url(path)
        local_size = os.path.getsize(path)

        self.info_text.delete("1.0", tk.END)
        self.info_text.insert("1.0",
            f"本地: {path}\n"
            f"CDN : {cdn_url}\n"
            f"類型: {ext}  |  大小: {local_size:,} bytes"
        )

        self.cdn_info.delete("1.0", tk.END)
        self.cdn_info.insert("1.0", f"CDN URL:\n{cdn_url}\n\n狀態: 等待探測（點「🔍 探測 CDN」）")

        IMG = ("jpg", "jpeg", "png", "gif", "webp")
        AUD = ("mp3", "wav", "ogg", "m4a")

        if ext in IMG:
            self._preview_image_local(path)
            self.cdn_preview_lbl.config(image="", text="（點「探測 CDN」載入圖片）")
        elif ext == "lrc":
            self._preview_text_local(path, 200)
            self.cdn_preview_lbl.config(image="", text="（點「探測 CDN」載入歌詞）")
        elif ext in AUD:
            self._preview_audio_local(path, local_size)
            self.cdn_preview_lbl.config(image="", text="（點「探測 CDN」驗證 + 瀏覽器播放）")
        elif ext == "json":
            self._preview_text_local(path, 60)
            self.cdn_preview_lbl.config(image="", text="（點「探測 CDN」比對 JSON）")
        else:
            self.local_preview_lbl.config(image="", text=f"📄 {os.path.basename(path)}")
            self.cdn_preview_lbl.config(image="", text="（不支援預覽）")

    # ─── 探測（HEAD → GET 降級）──────────────────────────────
    def on_probe(self):
        item = self.local_tree.focus()
        path = self.local_node_map.get(item)
        if not path or os.path.isdir(path):
            messagebox.showinfo("提示", "請選中具體文件")
            return
        url = local_to_cdn_url(path)
        self.status_lbl.config(text="探測中...")
        self.cdn_info.delete("1.0", tk.END)
        self.cdn_info.insert("1.0", f"CDN URL:\n{url}\n\n狀態: 探測中...")
        threading.Thread(target=self._do_probe, args=(path, url, item), daemon=True).start()

    def _do_probe(self, path, url, iid):
        ext = path.lower().split(".")[-1]
        IMG = ("jpg", "jpeg", "png", "gif", "webp")
        AUD = ("mp3", "wav", "ogg", "m4a")

        # ── 實際拿：HEAD → GET 降級 ──
        headers = {"User-Agent": "Mozilla/5.0"}
        code = 0
        msg = ""

        try:
            # 1) HEAD
            try:
                r = requests.head(url, timeout=8, allow_redirects=True, headers=headers)
                code = r.status_code
            except Exception:
                code = 0

            # 2) HEAD 失敗 → GET 降級
            if code not in (200, 206):
                try:
                    if ext in AUD:
                        # 音頻：Range GET
                        r2 = requests.get(url, headers={**headers, "Range": "bytes=0-0"}, timeout=10, allow_redirects=True, stream=True)
                        r2.close()
                        code = r2.status_code
                    else:
                        r2 = requests.get(url, timeout=10, allow_redirects=True, headers=headers, stream=True)
                        r2.close()
                        code = r2.status_code
                except Exception as e:
                    code = 0
                    msg = str(e)[:50]

        except Exception as e:
            code = 0
            msg = str(e)[:50]

        # ── 結果判定 ──
        if code in (200, 206):
            if ext in IMG:
                label = "圖片"
                self.after(0, lambda u=url: self._preview_image_cdn(u))
            elif ext == "lrc":
                label = "歌詞"
                self.after(0, lambda u=url: self._preview_text_cdn(u, 3000))
            elif ext in AUD:
                label = "音頻"
                self.after(0, lambda u=url: self._preview_audio_cdn(u))
            elif ext == "json":
                label = "JSON"
                # JSON 深度比對
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        local_data = json.load(f)
                    rj = requests.get(url, timeout=10)
                    rj.raise_for_status()
                    cdn_data = rj.json()
                    ok, diffs = compare_json(local_data, cdn_data)
                    if ok:
                        result_msg = "✅ JSON 存在且內容完全一致"
                        mark = "✅"
                    else:
                        result_msg = f"❌ JSON 內容不一致 ({len(diffs)} 處)"
                        mark = "❌"
                        self.after(0, lambda d=diffs[:5]: self.cdn_preview_lbl.config(
                            image="", text="🔍 錯位詳情:\n" + "\n".join(f"  • {x}" for x in d)))
                    self.after(0, lambda iid=iid, rm=result_msg, mk=mark: (
                        self.status_lbl.config(text=rm),
                        self._update_node_status(iid, mk),
                        self.cdn_info.insert("end", f"\n{rm}")
                    ))
                    return
                except Exception as e:
                    result_msg = f"⚠️ JSON 處理失敗: {e}"
                    mark = "⚠️"
                    self.after(0, lambda iid=iid, rm=result_msg, mk=mark: (
                        self.status_lbl.config(text=rm),
                        self._update_node_status(iid, mk)
                    ))
                    return
            else:
                label = "文件"

            result_msg = f"✅ CDN {label}存在 (HTTP {code}) — 不比對大小"
            mark = "✅"
            self.after(0, lambda iid=iid, rm=result_msg, mk=mark: (
                self.status_lbl.config(text=rm),
                self._update_node_status(iid, mk),
                self.cdn_info.insert("end", f"\n{rm}")
            ))

        elif code == 404:
            result_msg = "⚠️ CDN 不存在 (404) — 需上傳｜檢查 GitHub 推送與路徑大小寫"
            mark = "⚠️"
            self.after(0, lambda iid=iid, rm=result_msg, mk=mark: (
                self.status_lbl.config(text=rm),
                self._update_node_status(iid, mk),
                self.cdn_info.insert("end", f"\n{rm}")
            ))

        else:
            # HTTP 0 或其他異常
            result_msg = f"⚠️ 網路/超時 (HTTP {code}) — {msg}｜非不存在，可能是 CDN 暫時性問題"
            mark = "⚠️"
            self.after(0, lambda iid=iid, rm=result_msg, mk=mark: (
                self.status_lbl.config(text=rm),
                self._update_node_status(iid, mk),
                self.cdn_info.insert("end", f"\n{rm}")
            ))

    def _update_node_status(self, iid):
        try:
            path = self.local_node_map.get(iid, "")
            if not path or os.path.isdir(path):
                return
            mark = self.status_map.get(iid, "")
            old = self.local_tree.item(iid, "text")
            if old and old[0] in ("✅", "❌", "⚠️"):
                base = old.split(" ", 1)[1]
            else:
                base = old
            self.local_tree.item(iid, text=f"{mark} {base}" if mark else base)
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
        self._current_audio_path = path
        self.local_preview_lbl.config(
            image="",
            text=f"🎵 {os.path.basename(path)}\n大小: {size:,} bytes\n\n點上方「▶ 播放本地音頻」"
        )

    # ─── CDN 預覽 ────────────────────────────────────────
    def _preview_image_cdn(self, url):
        self.cdn_preview_lbl.config(image="", text="CDN 圖片載入中...")
        def load():
            try:
                with urllib.request.urlopen(url, timeout=8) as resp:
                    data = resp.read()
                img = Image.open(BytesIO(data))
                img.thumbnail((420, 320))
                ph = ImageTk.PhotoImage(img)
                self.img_cache.append(ph)
                self.after(0, lambda ph=ph, name=os.path.basename(url):
                            self.cdn_preview_lbl.config(image=ph, text=name))
            except Exception as e:
                self.after(0, lambda e=e: self.cdn_preview_lbl.config(image="", text=f"CDN 圖片失敗:\n{e}"))
        threading.Thread(target=load, daemon=True).start()

    def _preview_text_cdn(self, url, max_chars=3000):
        self.cdn_preview_lbl.config(image="", text="CDN 內容載入中...")
        def load():
            try:
                r = requests.get(url, timeout=8)
                r.raise_for_status()
                txt = r.text[:max_chars]
                self.after(0, lambda txt=txt: self.cdn_preview_lbl.config(image="", text=txt or "(空)"))
            except Exception as e:
                self.after(0, lambda e=e: self.cdn_preview_lbl.config(image="", text=f"CDN 讀取失敗:\n{e}"))
        threading.Thread(target=load, daemon=True).start()

    def _preview_audio_cdn(self, url):
        for w in self.cdn_view.winfo_children():
            if isinstance(w, (tk.Button, ttk.Button)):
                w.destroy()
        self.cdn_preview_lbl.config(image="", text=f"🎵 CDN 音頻\n\n✅ 已確認存在\n\n點下方按鈕在瀏覽器播放")
        ttk.Button(self.cdn_view, text="🌐 瀏覽器播放", command=lambda u=url: webbrowser.open(u)) \
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
            self.status_lbl.config(text=f"▶ 播放中: {os.path.basename(path)}")
        else:
            self.status_lbl.config(text="播放失敗（pygame 未安裝或檔案無效）")

    def on_purge(self):
        item = self.local_tree.focus()
        path = self.local_node_map.get(item)
        if not path or os.path.isdir(path):
            messagebox.showinfo("提示", "請選中具體文件")
            return
        url = local_to_purge_url(path)
        if purge_cdn(url):
            self.status_lbl.config(text=f"🗑 已提交清緩存: {os.path.basename(path)}")
            messagebox.showinfo("清緩存", f"已提交:\n{url}")
        else:
            self.status_lbl.config(text="清緩存失敗")
            messagebox.showwarning("清緩存", "請求失敗，請檢查網路或 API")

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