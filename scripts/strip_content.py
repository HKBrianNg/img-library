# img-library/scripts/strip_content.py
import json
from pathlib import Path

# 从 scripts 目录向上一级(img-library)，再进 openEDU 数据目录
HERE = Path(__file__).resolve().parent
content_dir = HERE.parent / "openEDU" / "BasicEnglish300" / "content"

files = sorted(content_dir.glob("chapter-*.json"))
if not files:
    print("❌ 没找到 chapter-*.json，检查路径：")
    print(f"   期望位置: {content_dir}")
    raise SystemExit(1)

for f in files:
    items = json.loads(f.read_text(encoding="utf-8"))
    changed = 0
    for it in items:
        if "content" in it:
            del it["content"]
            changed += 1
    f.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ {f.name}：处理 {len(items)} 条，删除 content {changed} 个")

print("\n完成，content 字段已全部移除，文字未改动。")