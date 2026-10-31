# tts_admin/main.py
import os
import re
import json
import asyncio
import threading
from pathlib import Path
from datetime import datetime

import edge_tts
import pygame
import tkinter as tk
from tkinter import ttk, messagebox

# ── 路径 ────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
ALLOWED_PROJECTS = {"EnglishShorts", "BasicEnglish300", "KnowledgeBase"}
RATE_NORMAL = "-8%"

# ── 音色预设 ────────────────────────────────────────────
VOICE_PRESETS = {
    "zh": {
        "女声": ["zh-CN-XiaoxiaoNeural", "zh-CN-XiaohanNeural", "zh-CN-XiaoxuanNeural",
                 "zh-CN-XiaochenNeural", "zh-CN-XiaomengNeural", "zh-CN-XiaoruiNeural"],
        "男声": ["zh-CN-YunyangNeural", "zh-CN-YunjianNeural", "zh-CN-YunxiaNeural",
                 "zh-CN-YunfengNeural", "zh-CN-YunzeNeural"],
        "儿童": ["zh-CN-XiaoyiNeural", "zh-CN-YunxiNeural"],
    },
    "en": {
        "女声": ["en-US-JennyNeural", "en-US-AriaNeural", "en-US-EmmaNeural",
                 "en-US-MichelleNeural", "en-US-AnaNeural"],
        "男声": ["en-US-GuyNeural", "en-US-ChristopherNeural", "en-US-DavisNeural",
                 "en-US-BrianNeural", "en-US-EdwardNeural"],
        "儿童": ["en-US-JennyNeural", "en-US-EmmaNeural", "en-US-AnaNeural", "en-US-DavisNeural"],
    },
}

# ── 工具 ──────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'\s+', '-', text)
    return text.strip('-') or "item"

def play_tts(text, voice, rate="-8%", tmp="__preview.mp3"):
    async def _do():
        c = edge_tts.Communicate(text, voice, rate=rate)
        await c.save(tmp)
        pygame.mixer.pre_init(frequency=22050, size=-16, channels=2, buffer=512)
        pygame.mixer.init()
        pygame.mixer.music.load(tmp)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.wait(50)
        pygame.mixer.music.unload()
        pygame.mixer.quit()
        try:
            os.remove(tmp)
        except OSError:
            pass
    asyncio.run(_do())

# ── 主程序 ──────────────────────────────────────────────

class TTSAdminApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("TTS Admin · openEDU")
        self.root.geometry("1200x750")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._closing = False
        self._loading = False
        self._speaking = False
        self.current_project: Path | None = None
        self.projects = self._discover()
        self.all_entries = []
        self.generating = False

        self._build_ui()
        self._populate_projects()
        self._refresh_zh_voices()
        self._refresh_en_voices()

    def _build_ui(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="项目:", font=("", 11, "bold")).pack(side="left")
        self.project_var = tk.StringVar()
        self.project_combo = ttk.Combobox(top, textvariable=self.project_var, state="readonly", width=22)
        self.project_combo.pack(side="left", padx=(5, 15))
        self.project_combo.bind("<<ComboboxSelected>>", self._load_project)

        ttk.Label(top, text="章节:").pack(side="left")
        self.chapter_var = tk.StringVar(value="（全部章节）")
        self.chapter_combo = ttk.Combobox(top, textvariable=self.chapter_var, state="readonly", width=28)
        self.chapter_combo.pack(side="left", padx=(2, 15))
        self.chapter_combo.bind("<<ComboboxSelected>>", self._apply_chapter_filter)

        ttk.Label(top, text="中文:").pack(side="left")
        self.zh_gender_var = tk.StringVar(value="女声")
        self.zh_gender_combo = ttk.Combobox(top, textvariable=self.zh_gender_var,
                                             values=["女声", "男声", "儿童"], width=7, state="readonly")
        self.zh_gender_combo.pack(side="left", padx=(2, 4))
        self.zh_gender_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_zh_voices())
        self.zh_voice_var = tk.StringVar()
        self.zh_voice_combo = ttk.Combobox(top, textvariable=self.zh_voice_var, state="readonly", width=26)
        self.zh_voice_combo.pack(side="left", padx=(0, 10))

        ttk.Label(top, text="英文:").pack(side="left")
        self.en_gender_var = tk.StringVar(value="女声")
        self.en_gender_combo = ttk.Combobox(top, textvariable=self.en_gender_var,
                                             values=["女声", "男声", "儿童"], width=7, state="readonly")
        self.en_gender_combo.pack(side="left", padx=(2, 4))
        self.en_gender_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_en_voices())
        self.en_voice_var = tk.StringVar()
        self.en_voice_combo = ttk.Combobox(top, textvariable=self.en_voice_var, state="readonly", width=26)
        self.en_voice_combo.pack(side="left", padx=(0, 10))

        ttk.Button(top, text="刷新音色", command=self._reload_voices).pack(side="left")

        bar = ttk.Frame(self.root, padding=(10, 5))
        bar.pack(fill="x")
        ttk.Button(bar, text="全选", command=self._select_all).pack(side="left", padx=(0, 4))
        ttk.Button(bar, text="全不选", command=self._deselect_all).pack(side="left", padx=(0, 8))
        ttk.Button(bar, text="生成选中", command=self._start_generate).pack(side="left", padx=(0, 4))
        self.force_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="强制重生成", variable=self.force_var).pack(side="left", padx=(10, 0))

        main = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        main.pack(fill="both", expand=True)

        cols = ("chapter", "slug", "zh", "en", "zh_gen", "en_gen", "status")
        self.tree = ttk.Treeview(main, columns=cols, show="headings", height=22)
        widths = [("chapter", 140), ("slug", 160), ("zh", 150), ("en", 160),
                  ("zh_gen", 50), ("en_gen", 50), ("status", 80)]
        for c, w in widths:
            self.tree.heading(c, text={"zh_gen": "中文", "en_gen": "英文"}.get(c, c))
            self.tree.column(c, width=w,
                             anchor="center" if c in ("zh_gen", "en_gen", "status") else "w")

        vsb = ttk.Scrollbar(main, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.bind("<Button-1>", self._on_click_cell)

        bottom = ttk.Frame(self.root, padding=(10, 5))
        bottom.pack(fill="x", side="bottom")
        self.progress = ttk.Progressbar(bottom, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(0, 4))
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(bottom, textvariable=self.status_var, relief="sunken",
                  anchor="w", padding=(6, 3)).pack(fill="x")

    def _discover(self):
        return [d for d in sorted(ROOT.iterdir())
                if d.is_dir() and d.name in ALLOWED_PROJECTS and (d / "data.json").exists()]

    def _populate_projects(self):
        names = [p.name for p in self.projects]
        self.project_combo["values"] = names
        if names:
            self.project_combo.current(0)
            self._load_project()

    def _load_project(self, *_):
        if self._loading:
            return
        self._loading = True
        name = self.project_var.get()
        if not name:
            self._loading = False
            return
        self.current_project = next((p for p in self.projects if p.name == name), self.projects[0])
        base = self.current_project
        content_dir = base / "content"
        audio_dir = base / "audio"
        audio_dir.mkdir(exist_ok=True)

        self.all_entries.clear()
        self.tree.delete(*self.tree.get_children())
        chapter_options = ["（全部章节）"]

        data = json.loads((base / "data.json").read_text(encoding="utf-8"))

        if "chapters" in data and data["chapters"]:
            for ch in data["chapters"]:
                ch_name = ch.get("name", "")
                ch_en = ch.get("en", "")
                link = ch.get("contentLink", "")
                if not link:
                    continue
                ch_file = content_dir / link
                if not ch_file.exists():
                    continue
                stem = Path(link).stem
                chapter_options.append(f"{ch_name} / {ch_en}")

                try:
                    items = json.loads(ch_file.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if not isinstance(items, list):
                    items = [items]

                for i, it in enumerate(items):
                    title = it.get("title", {})
                    if isinstance(title, dict):
                        zh = (title.get("zh", "") or "").strip()
                        en = (title.get("en", "") or "").strip()
                    else:
                        zh = (it.get("zh", "") or "").strip()
                        en = (it.get("en", "") or "").strip()

                    if not zh and not en:
                        continue

                    slug = slugify(en) if en else (slugify(zh) if zh else f"{stem}_{i+1:03d}")
                    if not slug or slug == "-":
                        slug = f"{stem}_{i+1:03d}"

                    entry = {
                        "id": f"{stem}_{i}", "stem": stem, "index": i,
                        "chapter_name": ch_name, "slug": slug, "zh": zh, "en": en,
                    }
                    self.all_entries.append(entry)

                    ajson = audio_dir / stem / f"{stem}.audio.json"
                    st = "待生成"
                    if ajson.exists():
                        try:
                            meta = json.loads(ajson.read_text(encoding="utf-8"))
                            es = meta.get("entries", {}).get(str(i), {})
                            z = es.get("zh_normal", {}).get("ok")
                            e2 = es.get("en_normal", {}).get("ok")
                            if z and e2:
                                st = "✅ 已生成"
                            elif z or e2:
                                st = "⚠ 部分"
                        except Exception:
                            pass

                    self.tree.insert("", "end", iid=entry["id"], values=(
                        ch_name, slug[:25],
                        zh[:20] if zh else "（无）",
                        en[:25] if en else "（无）",
                        "☐", "☐", st
                    ))

        elif "groups" in data and data["groups"]:
            for g in data["groups"]:
                g_name = g.get("name", "") or g.get("title", {}).get("zh", "")
                g_en = g.get("en", "") or g.get("title", {}).get("en", "")
                g_stem = slugify(g_en) if g_en else slugify(g_name)
                chapter_options.append(f"{g_name} / {g_en}")
                for i, it in enumerate(g.get("items", [])):
                    title = it.get("title", {})
                    if isinstance(title, dict):
                        zh = (title.get("zh", "") or "").strip()
                        en = (title.get("en", "") or "").strip()
                    else:
                        zh = (it.get("zh", "") or "").strip()
                        en = (it.get("en", "") or "").strip()
                    if not zh and not en:
                        continue
                    slug = slugify(en) if en else (slugify(zh) if zh else f"{g_stem}_{i+1:03d}")
                    entry = {
                        "id": f"{g_stem}_{i}", "stem": g_stem, "index": i,
                        "chapter_name": g_name, "slug": slug, "zh": zh, "en": en,
                    }
                    self.all_entries.append(entry)
                    self.tree.insert("", "end", iid=entry["id"], values=(
                        g_name, slug[:25],
                        zh[:20] if zh else "（无）",
                        en[:25] if en else "（无）",
                        "☐", "☐", "待生成"
                    ))

        self.chapter_combo["values"] = chapter_options
        self.chapter_combo.current(0)
        self._loading = False
        self.status_var.set(f"✅ {base.name}：{len(self.all_entries)} 条，{len(chapter_options)-1} 章")

    def _apply_chapter_filter(self, *_):
        sel = self.chapter_var.get()
        self.tree.delete(*self.tree.get_children())
        for e in self.all_entries:
            if sel != "（全部章节）":
                prefix = sel.split(" / ")[0]
                if e["chapter_name"] != prefix:
                    continue
            ajson = self.current_project / "audio" / e["stem"] / f"{e['stem']}.audio.json"
            st = "待生成"
            if ajson.exists():
                try:
                    meta = json.loads(ajson.read_text(encoding="utf-8"))
                    es = meta.get("entries", {}).get(str(e["index"]), {})
                    z = es.get("zh_normal", {}).get("ok")
                    en2 = es.get("en_normal", {}).get("ok")
                    if z and en2:
                        st = "✅ 已生成"
                    elif z or en2:
                        st = "⚠ 部分"
                except Exception:
                    pass
            self.tree.insert("", "end", iid=e["id"], values=(
                e["chapter_name"], e["slug"][:25],
                e["zh"][:20] if e["zh"] else "（无）",
                e["en"][:25] if e["en"] else "（无）",
                "☐", "☐", st
            ))
        self.status_var.set(f"筛选：{sel}（{len(self.tree.get_children())} 条）")

    def _on_click_cell(self, ev):
        region = self.tree.identify("region", ev.x, ev.y)
        if region != "cell":
            return

        col = self.tree.identify_column(ev.x)
        ci = int(col.replace("#", ""))
        iid = self.tree.identify_row(ev.y)
        if not iid:
            return

        vals = list(self.tree.item(iid, "values"))
        e = next((x for x in self.all_entries if x["id"] == iid), None)
        if not e:
            return

        # 列 5 = 中文复选框, 列 6 = 英文复选框
        if ci in (5, 6):
            vals[ci - 1] = "☐" if vals[ci - 1] == "☑" else "☑"
            self.tree.item(iid, values=vals)
            return

        if ci == 3:
            if not e["zh"]:
                self.status_var.set("该条没有中文文本")
                return
            self._speak_zh(e)
            return

        if ci == 4:
            if not e["en"]:
                self.status_var.set("该条没有英文文本")
                return
            self._speak_en(e)
            return

    def _speak_zh(self, e):
        if self._speaking:
            self.status_var.set("⏳ 正在朗读中，请稍候...")
            return

        zh_v = self.zh_voice_var.get()
        self.status_var.set(f"🔊 朗读中文：{e['slug']}")

        def run():
            self._speaking = True
            try:
                if not self._closing:
                    self.root.after(0, lambda m=f"🔊 朗读中文：{e['slug']}": self.status_var.set(m))
                    play_tts(e["zh"], zh_v, RATE_NORMAL)
                self.root.after(0, lambda: self.status_var.set("✅ 朗读结束"))
            except Exception as exc:
                self.root.after(0, lambda m=f"❌ 朗读失败：{exc}": self.status_var.set(m))
            finally:
                self._speaking = False

        threading.Thread(target=run, daemon=True).start()

    def _speak_en(self, e):
        if self._speaking:
            self.status_var.set("⏳ 正在朗读中，请稍候...")
            return

        en_v = self.en_voice_var.get()
        self.status_var.set(f"🔊 朗读英文：{e['slug']}")

        def run():
            self._speaking = True
            try:
                if not self._closing:
                    self.root.after(0, lambda m=f"🔊 朗读英文：{e['slug']}": self.status_var.set(m))
                    play_tts(e["en"], en_v, RATE_NORMAL)
                self.root.after(0, lambda: self.status_var.set("✅ 朗读结束"))
            except Exception as exc:
                self.root.after(0, lambda m=f"❌ 朗读失败：{exc}": self.status_var.set(m))
            finally:
                self._speaking = False

        threading.Thread(target=run, daemon=True).start()

    def _select_all(self):
        for iid in self.tree.get_children():
            v = list(self.tree.item(iid, "values"))
            v[4] = "☑"   # 中文
            v[5] = "☑"   # 英文
            self.tree.item(iid, values=v)

    def _deselect_all(self):
        for iid in self.tree.get_children():
            v = list(self.tree.item(iid, "values"))
            v[4] = "☐"
            v[5] = "☐"
            self.tree.item(iid, values=v)

    def _refresh_zh_voices(self):
        vs = VOICE_PRESETS["zh"].get(self.zh_gender_var.get(), [])
        self.zh_voice_combo["values"] = vs
        if vs:
            self.zh_voice_var.set(vs[0])

    def _refresh_en_voices(self):
        vs = VOICE_PRESETS["en"].get(self.en_gender_var.get(), [])
        self.en_voice_combo["values"] = vs
        if vs:
            self.en_voice_var.set(vs[0])

    def _reload_voices(self):
        self.status_var.set("⏳ 从云端拉取音色...")
        def run():
            try:
                async def fetch():
                    return await edge_tts.list_voices()
                voices = asyncio.run(fetch())
                zh = [v["ShortName"] for v in voices if v["ShortName"].startswith("zh-CN")]
                en = [v["ShortName"] for v in voices if v["ShortName"].startswith("en-")]
                for v in zh:
                    if not any(v in VOICE_PRESETS["zh"][g] for g in VOICE_PRESETS["zh"]):
                        VOICE_PRESETS["zh"]["女声"].append(v)
                for v in en:
                    if not any(v in VOICE_PRESETS["en"][g] for g in VOICE_PRESETS["en"]):
                        VOICE_PRESETS["en"]["女声"].append(v)
                self.root.after(0, self._refresh_zh_voices)
                self.root.after(0, self._refresh_en_voices)
                self.root.after(0, lambda m=f"✅ 云端音色已刷新（中文{len(zh)}/英文{len(en)}）": self.status_var.set(m))
            except Exception as exc:
                err = f"❌ 刷新失败：{exc}"
                self.root.after(0, lambda m=err: self.status_var.set(m))
        threading.Thread(target=run, daemon=True).start()

    def _start_generate(self):
        if self.generating:
            messagebox.showinfo("提示", "正在生成中")
            return
        tasks = []
        for iid in self.tree.get_children():
            vals = self.tree.item(iid, "values")
            e = next((x for x in self.all_entries if x["id"] == iid), None)
            if not e:
                continue
            chk_zh = vals[4] == "☑"
            chk_en = vals[5] == "☑"
            if not chk_zh and not chk_en:
                continue
            tasks.append((e, chk_zh, chk_en))

        if not tasks:
            messagebox.showinfo("提示", "没有可生成的勾选项")
            return

        self.generating = True
        force = self.force_var.get()
        zh_v = self.zh_voice_var.get()
        en_v = self.en_voice_var.get()
        self.progress["value"] = 0
        self.status_var.set(f"🎙 开始生成 {len(tasks)} 条...")
        threading.Thread(target=self._worker, args=(tasks, force, zh_v, en_v), daemon=True).start()

    def _worker(self, tasks, force, zh_v, en_v):
        total = len(tasks)
        done = 0
        for e, chk_zh, chk_en in tasks:
            if self._closing:
                break
            stem = e["stem"]
            idx = e["index"]
            slug = e["slug"]
            adir = self.current_project / "audio" / stem
            adir.mkdir(parents=True, exist_ok=True)
            ajson = adir / f"{stem}.audio.json"

            meta = {}
            if ajson.exists():
                try:
                    meta = json.loads(ajson.read_text(encoding="utf-8"))
                except Exception:
                    meta = {}
            meta.setdefault("chapter", stem)
            meta.setdefault("entries", {})
            es = meta["entries"].setdefault(str(idx), {})

            if chk_zh and e["zh"]:
                p = adir / f"{slug}_zh.mp3"
                if force or not p.exists() or not es.get("zh_normal", {}).get("ok"):
                    try:
                        async def _do():
                            c = edge_tts.Communicate(e["zh"], zh_v, rate=RATE_NORMAL)
                            await c.save(str(p))
                        asyncio.run(_do())
                        es["zh_normal"] = {"ok": True, "voice": zh_v, "rate": RATE_NORMAL,
                                           "generated_at": datetime.now().isoformat()}
                    except Exception as exc:
                        es["zh_normal"] = {"ok": False, "error": str(exc)}

            if chk_en and e["en"]:
                p = adir / f"{slug}_en.mp3"
                if force or not p.exists() or not es.get("en_normal", {}).get("ok"):
                    try:
                        async def _do():
                            c = edge_tts.Communicate(e["en"], en_v, rate=RATE_NORMAL)
                            await c.save(str(p))
                        asyncio.run(_do())
                        es["en_normal"] = {"ok": True, "voice": en_v, "rate": RATE_NORMAL,
                                          "generated_at": datetime.now().isoformat()}
                    except Exception as exc:
                        es["en_normal"] = {"ok": False, "error": str(exc)}

            ajson.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

            done += 1
            self.root.after(0, lambda v=int(done / total * 100): self.progress.configure(value=v))
            self.root.after(0, lambda d=done, t=total, s=slug: self.status_var.set(f"生成中 {d}/{t}：{s}"))
            self.root.after(0, lambda iid=e["id"]: self._refresh_row_status(iid))

        self.generating = False
        if not self._closing:
            self.root.after(0, lambda: self.status_var.set(f"✅ 完成，共 {done} 条"))

    def _refresh_row_status(self, iid):
        if self._closing or not self.tree.exists(iid):
            return
        e = next((x for x in self.all_entries if x["id"] == iid), None)
        if not e:
            return
        ajson = self.current_project / "audio" / e["stem"] / f"{e['stem']}.audio.json"
        st = "待生成"
        if ajson.exists():
            try:
                meta = json.loads(ajson.read_text(encoding="utf-8"))
                s = meta.get("entries", {}).get(str(e["index"]), {})
                z = s.get("zh_normal", {}).get("ok")
                en2 = s.get("en_normal", {}).get("ok")
                if z and en2:
                    st = "✅ 已生成"
                elif z or en2:
                    st = "⚠ 部分"
            except Exception:
                pass
        vals = list(self.tree.item(iid, "values"))
        vals[6] = st
        self.tree.item(iid, values=vals)

    def _on_close(self):
        self._closing = True
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    r = tk.Tk()
    app = TTSAdminApp(r)
    app.run()