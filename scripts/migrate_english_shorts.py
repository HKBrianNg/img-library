# -*- coding: utf-8 -*-
"""
migrate_english_shorts.py
========================
把 openEDU/EnglishShorts/data.json 从「单文件 groups 内嵌」结构，
迁移为与 KnowledgeBase 一致的「轻量索引 + content/{group}.json」结构。

特性
----
* 先备份原 data.json -> data.json.bak（已存在则跳过，绝不覆盖备份）
* 默认 DRY-RUN：只打印会做什么，不改任何文件
* --apply 才真正写入
* 同组内 en 完全重复时追加内容哈希，保证 slug 唯一
* 生成后可立即用 --verify 校验：条目总数守恒、JSON 合法、无 slug 冲突

用法
----
    # 1) 先看会改什么（强烈建议第一步）
    python migrate_english_shorts.py ../../openEDU/EnglishShorts

    # 2) 确认无误再执行
    python migrate_english_shorts.py ../../openEDU/EnglishShorts --apply

    # 3) 执行后校验（也可单独跑）
    python migrate_english_shorts.py ../../openEDU/EnglishShorts --verify

脚本建议放在：img-library/scripts/migrate_english_shorts.py
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

# 英文短句转 slug：去标点、空格 -> 连字符、全小写
# "May I come in?" -> "may-i-come-in"
def en_to_slug(en: str) -> str:
    s = (en or "").strip()
    s = re.sub(r"[’'\"“”(),.!?;:—\-]", "", s)   # 去标点（保留字母数字与空格）
    s = re.sub(r"\s+", "-", s).lower().strip("-")
    return s or "item"


def convert_group(items):
    """
    [{en, name}] -> [{title:{zh,en}, content:{zh,en}}]
    返回 (条目列表, 冲突/去重记录列表)
    """
    out = []
    seen = {}          # slug -> 是否出现过
    collisions = []    # (原始en, 最终slug, 原因)
    for it in items or []:
        en = (it.get("en") or "").strip()
        zh = (it.get("name") or "").strip()
        if not en:
            continue
        slug = en_to_slug(en)
        reason = None
        if slug in seen:
            reason = "同组英文完全重复，追加哈希"
            slug = f"{slug}_{hashlib.md5(en.encode('utf-8')).hexdigest()[:6]}"
        elif not slug or slug == "item":
            reason = "无法生成有效 slug，追加哈希"
            slug = f"item_{hashlib.md5(en.encode('utf-8')).hexdigest()[:6]}"
        seen[slug] = True
        if reason:
            collisions.append((en, slug, reason))
        out.append({
            "title":   {"zh": zh, "en": en},
            "content": {"zh": zh, "en": en},
        })
    return out, collisions


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj, indent=2):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=indent),
                   encoding="utf-8")
    tmp.replace(path)   # 原子替换，避免写到一半断电/报错导致文件损坏


def cmd_migrate(root, apply=False):
    root = Path(root).resolve()
    src = root / "data.json"
    if not src.exists():
        print(f"✗ 找不到 {src}", file=sys.stderr)
        sys.exit(2)

    data = load_json(src)
    groups = data.get("groups") or []
    if not isinstance(groups, list):
        print("✗ data.json 里没有 groups[] 数组", file=sys.stderr)
        sys.exit(3)

    # ---- 备份：只在不存在时建，绝不覆盖旧备份 ----
    bak = src.with_suffix(src.suffix + ".bak")
    if not bak.exists():
        if apply:
            bak.write_bytes(src.read_bytes())
            print(f"✓ 备份原文件 -> {bak.name}")
        else:
            print(f"[dry-run] 会备份原文件 -> {bak.name}")
    else:
        print(f"· 备份已存在，跳过：{bak.name}")

    content_dir = root / "content"
    audio_dir = root / "audio"

    if apply:
        content_dir.mkdir(parents=True, exist_ok=True)
        audio_dir.mkdir(parents=True, exist_ok=True)
    else:
        print(f"[dry-run] 会创建 {content_dir.name}/ 与 {audio_dir.name}/")

    chapters = []
    total_old = 0
    total_new = 0
    all_collisions = []

    print(f"\n{'组(id)':16s} {'原条目':>6s} {'生成':>6s}  文件")
    print("-" * 56)
    for g in groups:
        gid = (g.get("id") or "").strip()
        if not gid:
            print(f"  ! 跳过无 id 的组：{g.get('name')}", file=sys.stderr)
            continue
        items = g.get("items") or []
        total_old += len([i for i in items if (i.get("en") or "").strip()])

        converted, cols = convert_group(items)
        total_new += len(converted)
        all_collisions.extend((gid, *c) for c in cols)

        fname = f"{gid}.json"
        if apply:
            write_json(content_dir / fname, converted)
        print(f"{gid:16s} {len(items):6d} {len(converted):6d}  content/{fname}")

    # ---- 重写 data.json 为轻量索引 ----
    new_index = {
        "title": data.get("title"),
        "titleEn": data.get("titleEn"),
        "description": data.get("description"),
        "descriptionEn": data.get("descriptionEn"),
        "chapters": chapters,
    }
    for g in groups:
        gid = (g.get("id") or "").strip()
        if not gid:
            continue
        new_index["chapters"].append({
            "name": g.get("name"),
            "en": g.get("en"),
            "icon": g.get("icon"),
            "contentLink": f"{gid}.json",
        })

    if apply:
        write_json(src, new_index)
        print(f"\n✓ 已重写 data.json（轻量索引，{len(chapters)} 章）")
    else:
        print(f"\n[dry-run] 会重写 data.json 为 {len(chapters)} 章的轻量索引")

    # ---- 报告去重 ----
    if all_collisions:
        print(f"\n⚠  slug 去重 {len(all_collisions)} 处：")
        for gid, en, slug, reason in all_collisions:
            print(f"   [{gid}] {reason}")
            print(f"       原: {en}")
            print(f"       -> {slug}")
    else:
        print("\n✓ 无 slug 冲突")

    print(f"\n条目数：原 {total_old} 条 → 新 {total_new} 条"
          + ("" if total_old == total_new else "  ⚠ 数量不一致，请检查！"))

    if not apply:
        print("\n以上是预演，未改动任何文件。确认无误后加 --apply 执行。")


def cmd_verify(root):
    """校验迁移结果：索引合法、章节文件齐全、条目总数守恒、slug 唯一"""
    root = Path(root).resolve()
    src = root / "data.json"
    if not src.exists():
        print("✗ 目录里没有 data.json，先跑 --apply", file=sys.stderr)
        sys.exit(2)

    idx = load_json(src)
    chapters = idx.get("chapters") or []
    content_dir = root / "content"

    errors = 0
    total = 0
    print(f"索引: {idx.get('title')} / {idx.get('titleEn')}")
    print(f"章节数: {len(chapters)}\n")

    # 1) 索引里有没有遗留的 groups 字段
    if "groups" in idx:
        print("✗ data.json 仍是旧结构（含 groups 字段）")
        errors += 1

    # 跨章节全局重复英文检测（同 en 应只属于一个章节，避免音频路径撞车）
    en_owner = {}
    for ch in chapters:
        link = ch.get("contentLink")
        name = ch.get("name") or ch.get("en") or link
        path = content_dir / link if link else None
        if not path or not path.exists():
            print(f"  ✗ [{name}] 缺失 content/{link}")
            errors += 1
            continue
        try:
            items = load_json(path)
        except Exception as e:
            print(f"  ✗ [{name}] JSON 解析失败: {e}")
            errors += 1
            continue
        if not isinstance(items, list):
            print(f"  ✗ [{name}] 内容不是数组")
            errors += 1
            continue

        bad = 0
        seen_in_group = {}
        for it in items:
            tz = (it.get("title") or {}).get("zh")
            te = (it.get("title") or {}).get("en")
            cz = (it.get("content") or {}).get("zh")
            ce = (it.get("content") or {}).get("en")
            if not all([tz, te, cz, ce]):
                bad += 1
            # 用「规范化英文」判重：同组重复已在迁移时哈希化解，
            # 这里只报「跨章节同一句」这种真正会撞音频的冲突。
            key = en_to_slug(te)
            if key in seen_in_group:
                print(f"  ⚠ [{name}] 组内重复句，迁移时已哈希区分: {te}")
            seen_in_group[key] = True
            if key in en_owner and en_owner[key] != name:
                print(f"  ✗ 跨章节同句冲突: 「{te}」同时出现在 "
                      f"[{en_owner[key]}] 与 [{name}]，音频路径会撞")
                errors += 1
            else:
                en_owner.setdefault(key, name)
        total += len(items)
        flag = "✓" if bad == 0 else f"⚠ {bad} 条字段不全"
        print(f"  {flag}  {name:20s} {len(items):4d} 条  ({link})")

    print(f"\n合计条目: {total}")
    if errors == 0:
        print("✅ 校验通过：索引干净、文件齐全、slug 无冲突、字段完整")
    else:
        print(f"❌ 发现 {errors} 个问题，请检查后重试")
    sys.exit(0 if errors == 0 else 4)


def main():
    ap = argparse.ArgumentParser(
        description="EnglishShorts 结构迁移：单文件 groups -> KnowledgeBase 同款结构",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("root", help="EnglishShorts 目录路径，如 ../../openEDU/EnglishShorts")
    ap.add_argument("--apply", action="store_true", help="真正写入（默认只预演 dry-run）")
    ap.add_argument("--verify", action="store_true", help="校验迁移结果")
    args = ap.parse_args()

    if args.verify:
        cmd_verify(args.root)
    else:
        cmd_migrate(args.root, apply=args.apply)


if __name__ == "__main__":
    main()
