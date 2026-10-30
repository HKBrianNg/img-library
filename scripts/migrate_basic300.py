# migrate_basic300.py
# 用法:
#   python migrate_basic300.py <BasicEnglish300目录>              # dry-run，只打印
#   python migrate_basic300.py <BasicEnglish300目录> --apply       # 执行迁移
#   python migrate_basic300.py <BasicEnglish300目录> --verify      # 校验结果
#
# 行为:
#   1. 备份 data.json → data.json.bak（仅不存在时）
#   2. 建 content/images/，把 content/*.jpg 移进去
#   3. 按章节拆 items → content/chapter-N-{en}.json（无 imageUrl）
#   4. 重写 data.json 为轻量索引（groups→chapters）
#   5. 建 audio/ 目录（空）
#   6. 同章 slug 冲突自动加 _2 _3 后缀去重
#   7. 跨章节同句英文会警告（音频会互盖）

import json, re, sys, os, shutil, hashlib
from pathlib import Path

def slug(en: str) -> str:
    """英文短句转 kebab-case"""
    s = en.strip()
    s = re.sub(r"[’'\"“”(),.!?;:—\-]", "", s)
    s = re.sub(r"\s+", "-", s).lower().strip("-")
    return s or "item"

def en_slug(en: str) -> str:
    """同 slug()，别名保持兼容"""
    return slug(en)

def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def write_json(path, data):
    """原子写入：先写 .tmp 再替换"""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)

def convert_items(items):
    """
    items: [{name, en, lessonImage}]
    → [{title:{zh,en}, content:{zh,en}}]
    同时返回 slug 列表供校验
    """
    out = []
    seen = {}          # stem → count（用于同章去重）
    for it in items:
        en = (it.get("en") or "").strip()
        zh = (it.get("name") or "").strip()
        if not en:
            continue
        stem = slug(en)
        # 同章去重
        if stem in seen:
            seen[stem] += 1
            s = f"{stem}_{seen[stem]}"
        else:
            seen[stem] = 1
            s = stem
        out.append({
            "title":   {"zh": zh, "en": en},
            "content": {"zh": zh, "en": en}
        })
    return out

def dry_run(root):
    """预演模式：打印将要做什么，不修改任何文件"""
    data_path = root / "data.json"
    if not data_path.exists():
        print(f"❌ 找不到 {data_path}")
        return False

    data = load_json(data_path)
    chapters = data.get("chapters", [])
    print(f"📋 预演模式 — BasicEnglish300")
    print(f"   章节数: {len(chapters)}")
    print()

    # 统计图片
    content_dir = root / "content"
    jpgs = list(content_dir.glob("*.jpg")) if content_dir.exists() else []
    print(f"   图片: content/ 下有 {len(jpgs)} 张 .jpg")
    print(f"   将移动到: content/images/")
    print()

    # 统计每章条目
    total = 0
    for i, ch in enumerate(chapters):
        items = ch.get("items", [])
        total += len(items)
        en_name = ch.get("en", ch.get("name", f"chapter-{i+1}"))
        safe_en = re.sub(r"[^\w\s-]", "", en_name).strip().lower()
        safe_en = re.sub(r"\s+", "-", safe_en)
        fname = f"chapter-{i+1:02d}-{safe_en}.json"
        print(f"   [{i+1:2d}] {ch.get('name','')} ({len(items)} 条) → content/{fname}")

    print()
    print(f"   合计: {total} 条")
    print(f"   data.json 将重写为轻量索引")
    print(f"   原文件备份为 data.json.bak")
    print()
    print("✅ 预演完成，未修改任何文件。加 --apply 执行。")
    return True

def apply_migration(root):
    """执行迁移"""
    data_path = root / "data.json"
    if not data_path.exists():
        print(f"❌ 找不到 {data_path}")
        return False

    # 检查是否已迁移过
    if (root / "content" / "images").exists() and any((root / "content").glob("chapter-*.json")):
        print("❌ 看起来已经迁移过了（content/images/ 存在且有 chapter-*.json）")
        print("   如需重新迁移，请先恢复原 data.json.bak 并删除 content/chapter-*.json")
        return False

    data = load_json(data_path)
    chapters = data.get("chapters", [])

    # 1. 备份
    bak = data_path.with_suffix(".json.bak")
    if not bak.exists():
        bak.write_bytes(data_path.read_bytes())
        print(f"✓ 备份: data.json.bak")
    else:
        print(f"  (已有备份，跳过)")

    # 2. 建 content/images/，移 jpg
    content_dir = root / "content"
    images_dir = content_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    jpgs = list(content_dir.glob("*.jpg"))
    moved = 0
    for jpg in jpgs:
        dst = images_dir / jpg.name
        if not dst.exists():
            shutil.move(str(jpg), str(dst))
            moved += 1
    print(f"✓ 移动 {moved} 张图片 → content/images/")

    # 3. 拆章节
    total = 0
    new_chapters = []
    seen_slugs_global = {}   # 跨章节 slug 统计（检测音频互盖）

    for i, ch in enumerate(chapters):
        items = ch.get("items", [])
        en_name = ch.get("en", ch.get("name", f"chapter-{i+1}"))
        safe_en = re.sub(r"[^\w\s-]", "", en_name).strip().lower()
        safe_en = re.sub(r"\s+", "-", safe_en)
        fname = f"chapter-{i+1:02d}-{safe_en}.json"

        converted = convert_items(items)

        # 记录 slug 供跨章检测
        for it in ch.get("items", []):
            en = (it.get("en") or "").strip()
            if en:
                s = slug(en)
                seen_slugs_global[s] = seen_slugs_global.get(s, 0) + 1

        # 写章节文件
        chapter_path = content_dir / fname
        write_json(chapter_path, converted)
        total += len(converted)

        new_chapters.append({
            "name": ch.get("name"),
            "en": ch.get("en"),
            "contentLink": fname
        })
        print(f"  {fname:40s} {len(converted):3d} 条")

    # 4. 重写 data.json
    new_index = {
        "title": data.get("title", "基础英语300句"),
        "titleEn": data.get("titleEn", "Basic 300 English Sentences"),
        "chapters": new_chapters
    }
    write_json(data_path, new_index)
    print(f"\n✓ data.json 已重写为轻量索引 ({len(new_chapters)} 章)")

    # 5. 建 audio/ 目录
    audio_dir = root / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    print(f"✓ audio/ 目录已建")

    # 6. 跨章节警告
    dupes = {s: c for s, c in seen_slugs_global.items() if c > 1}
    if dupes:
        print(f"\n⚠️  跨章节同句英文（音频会互盖，需留意）:")
        for s, c in dupes.items():
            print(f"   {s} ({c} 处)")

    print(f"\n✅ 迁移完成: {len(chapters)} 章, 共 {total} 条")
    return True

def verify(root):
    """校验迁移结果"""
    data_path = root / "data.json"
    if not data_path.exists():
        print("❌ 找不到 data.json")
        return False

    data = load_json(data_path)

    # 检查是否是轻量索引
    if "groups" in data:
        print("❌ data.json 仍是旧格式（含 groups），迁移未完成")
        return False
    if "chapters" not in data:
        print("❌ data.json 缺少 chapters 字段")
        return False

    chapters = data["chapters"]
    print(f"📋 校验模式 — {len(chapters)} 章")

    content_dir = root / "content"
    errors = []
    warnings = []
    total = 0

    # 检查 content/images/
    images_dir = content_dir / "images"
    if not images_dir.exists():
        errors.append("content/images/ 不存在")
    else:
        img_count = len(list(images_dir.glob("*.jpg")))
        print(f"   content/images/: {img_count} 张 jpg")

    # 逐章校验
    all_slugs = []
    for ch in chapters:
        fname = ch.get("contentLink")
        if not fname:
            errors.append(f"章节缺少 contentLink: {ch.get('name')}")
            continue
        fpath = content_dir / fname
        if not fpath.exists():
            errors.append(f"找不到章节文件: {fname}")
            continue
        try:
            items = load_json(fpath)
        except json.JSONDecodeError as e:
            errors.append(f"{fname} JSON 解析失败: {e}")
            continue

        if not isinstance(items, list):
            errors.append(f"{fname} 内容不是数组")
            continue

        total += len(items)
        # 检查字段
        for j, it in enumerate(items):
            if "title" not in it or "content" not in it:
                errors.append(f"{fname}[{j}] 缺少 title 或 content")
            if "imageUrl" in it:
                warnings.append(f"{fname}[{j}] 含 imageUrl（应已移除）")
            # 收集 slug（从 title.en 生成）
            en = it.get("title", {}).get("en", "")
            if en:
                all_slugs.append((fname, slug(en)))

        print(f"   ✓ {fname:40s} {len(items):3d} 条")

    # 检查 slug 唯一性（同章内）
    by_file = {}
    for fname, s in all_slugs:
        by_file.setdefault(fname, []).append(s)
    for fname, slugs in by_file.items():
        dupes = [s for s in slugs if slugs.count(s) > 1]
        if dupes:
            errors.append(f"{fname} 内有重复 slug: {set(dupes)}")

    print(f"\n   合计: {total} 条")

    if warnings:
        print(f"\n⚠️  警告 ({len(warnings)}):")
        for w in warnings[:10]:
            print(f"   {w}")

    if errors:
        print(f"\n❌ 错误 ({len(errors)}):")
        for e in errors[:10]:
            print(f"   {e}")
        return False

    print(f"\n✅ 校验通过")
    return True

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    root = Path(sys.argv[1]).resolve()

    if not root.exists() or not root.is_dir():
        print(f"❌ 目录不存在: {root}")
        sys.exit(1)

    if len(sys.argv) >= 3 and sys.argv[2] == "--verify":
        ok = verify(root)
        sys.exit(0 if ok else 1)
    elif len(sys.argv) >= 3 and sys.argv[2] == "--apply":
        ok = apply_migration(root)
        sys.exit(0 if ok else 1)
    else:
        ok = dry_run(root)
        sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()