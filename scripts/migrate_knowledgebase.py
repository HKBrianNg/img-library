import json
import os
import sys
import shutil
import tempfile
from pathlib import Path
from slugify import slugify  # 若未安装：pip install python-slugify

def load_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))

def save_json(p, data):
    s = json.dumps(data, ensure_ascii=False, indent=2)
    # 原子写：同目录临时文件 + os.replace
    fd, tmp = tempfile.mkstemp(dir=Path(p).parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(s)
            f.flush()
            os.fsync(f.fileno())
        # 备份原文件
        if Path(p).exists():
            bak = str(p) + ".bak"
            if not Path(bak).exists():
                shutil.copy2(p, bak)
        os.replace(tmp, p)
    except Exception:
        if os.path.exists(tmp): os.unlink(tmp)
        raise

def slug(en):
    return slugify(en or "", lowercase=True, separator="-")[:60] or "item"

def dry_run(root):
    root = Path(root)
    data = load_json(root / "data.json")
    print(f"📋 Dry-run: {root.name}")
    if "groups" in data:
        print("⚠️  仍含 groups（旧格式）")
    chs = data.get("chapters", [])
    print(f"   章节数: {len(chs)}")
    img_dir = root / "content" / "images"
    jpgs = list((root / "content").glob("*.jpg")) if (root / "content").exists() else []
    print(f"   content/ 下 jpg: {len(jpgs)} 张（将移入 images/）")
    for ch in chs:
        print(f"   - {ch.get('name')} ({ch.get('contentLink')})")
    print("✅ Dry-run 完成（未修改文件）")
    return True

def apply_migration(root):
    root = Path(root)
    data_path = root / "data.json"
    data = load_json(data_path)
    content_dir = root / "content"
    images_dir = content_dir / "images"
    images_dir.mkdir(exist_ok=True)

    # 1) 图片迁移
    for jpg in content_dir.glob("*.jpg"):
        shutil.move(str(jpg), str(images_dir / jpg.name))
    print(f"🖼  图片已移入 {images_dir.relative_to(root)}")

    # 2) 章节文件处理
    seen_slug = set()
    for ch in data.get("chapters", []):
        fname = ch.get("contentLink")
        if not fname: continue
        fpath = content_dir / fname
        if not fpath.exists():
            print(f"⚠️  缺章节文件: {fname}")
            continue
        items = load_json(fpath)
        new_items = []
        for it in items:
            en = (it.get("title", {}) or {}).get("en", "")
            s = slug(en)
            base = s
            i = 2
            while (fname, s) in seen_slug:
                s = f"{base}_{i}"; i += 1
            seen_slug.add((fname, s))
            # 移除 imageUrl
            it.pop("imageUrl", None)
            new_items.append(it)
        save_json(fpath, new_items)
        print(f"   ✓ {fname}: {len(new_items)} 条")

    # 3) data.json 移除 groups（若有）
    data.pop("groups", None)
    save_json(data_path, data)
    print("✅ --apply 完成（已备份 .bak）")
    return True

def verify(root):
    root = Path(root)
    data = load_json(root / "data.json")
    if "groups" in data:
        print("❌ 仍含 groups"); return False
    if "chapters" not in data:
        print("❌ 缺 chapters"); return False
    chs = data["chapters"]
    print(f"📋 校验: {len(chs)} 章")
    images_dir = root / "content" / "images"
    print(f"   images/: {len(list(images_dir.glob('*.jpg')))} 张")
    err = []
    all_slugs = []
    for ch in chs:
        fname = ch.get("contentLink")
        fpath = root / "content" / fname
        if not fpath.exists():
            err.append(f"缺文件 {fname}"); continue
        items = load_json(fpath)
        slugs = []
        for j, it in enumerate(items):
            if "imageUrl" in it:
                err.append(f"{fname}[{j}] 仍含 imageUrl")
            en = (it.get("title", {}) or {}).get("en", "")
            slugs.append(slug(en))
        # 同章重复
        for s in set(slugs):
            if slugs.count(s) > 1:
                err.append(f"{fname} 重复 slug: {s}")
        all_slugs.extend([(fname, s) for s in slugs])
        print(f"   ✓ {fname}: {len(items)} 条")
    # 跨章同句（仅警告）
    cross = {}
    for fn, s in all_slugs:
        cross.setdefault(s, set()).add(fn)
    for s, fns in cross.items():
        if len(fns) > 1:
            print(f"⚠️  跨章同 slug '{s}': {fns}")
    if err:
        print("\n❌ 错误:"); [print("   ", e) for e in err]; return False
    print("\n✅ 校验通过")
    return True

def main():
    if len(sys.argv) < 2:
        print("Usage: python migrate_knowledgebase.py <root> [--apply|--verify]")
        sys.exit(1)
    root = Path(sys.argv[1]).resolve()
    mode = sys.argv[2] if len(sys.argv) > 2 else "dry"
    if mode == "--verify": ok = verify(root)
    elif mode == "--apply": ok = apply_migration(root)
    else: ok = dry_run(root)
    sys.exit(0 if ok else 1)

# ========== 沙盒测试（仅本地模拟，不碰真实数据） ==========
def run_sandbox():
    print("🧪 启动沙盒测试...")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "KnowledgeBase"
        root.mkdir()
        (root / "content").mkdir()
        # 模拟 data.json
        data = {
            "groups": [{"name": "旧组"}],
            "chapters": [
                {"name": "常用表达", "contentLink": "chapter-01.json"},
                {"name": "日常对话", "contentLink": "chapter-02.json"}
            ]
        }
        (root / "data.json").write_text(json.dumps(data, ensure_ascii=False), "utf-8")
        # 模拟图片
        (root / "content" / "a.jpg").write_text("fake")
        # 章节 1
        items1 = [
            {"title":{"zh":"加油","en":"Go ahead."}, "content":{"zh":"加油","en":"Go ahead."}, "imageUrl":"a.jpg"},
            {"title":{"zh":"再试","en":"Go ahead."}, "content":{"zh":"再试","en":"Go ahead."}}  # 同章重复
        ]
        (root / "content" / "chapter-01.json").write_text(json.dumps(items1, ensure_ascii=False), "utf-8")
        # 章节 2（跨章同句）
        items2 = [
            {"title":{"zh":"前进","en":"Go ahead."}, "content":{"zh":"前进","en":"Go ahead."}}
        ]
        (root / "content" / "chapter-02.json").write_text(json.dumps(items2, ensure_ascii=False), "utf-8")

        print("\n--- [1] Dry-run ---")
        dry_run(root)
        print("\n--- [2] Apply ---")
        apply_migration(root)
        print("\n--- [3] Verify ---")
        ok = verify(root)
        print("\n🏁 沙盒结果:", "✅ 通过" if ok else "❌ 失败")
        # 展示结构
        print("\n📂 沙盒最终结构:")
        for p in sorted(root.rglob("*")):
            print("  ", p.relative_to(root))

if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--sandbox":
        run_sandbox()
    else:
        main()