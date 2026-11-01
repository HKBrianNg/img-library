# openEDU/admin/config.py
import os
import requests

# ─── 路径配置 ─────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# 强制指向 openEDU（admin 的上级目录）
LOCAL_BASE = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

# ─── CDN 配置 ─────────────────────────────────────────────
CDN_PATH_PREFIX = "openEDU"
GITHUB_USER = "HKBrianNg"
REPO_NAME = "img-library"
BRANCH = "main"

CDN_BASE = f"https://cdn.jsdelivr.net/gh/{GITHUB_USER}/{REPO_NAME}@{BRANCH}"
PURGE_BASE = "https://purge.jsdelivr.net"

# ─── 扫描排除项 ───────────────────────────────────────────
SCAN_SKIP = {
    ".git", ".vscode", "admin", ".venv", "node_modules",
    "__pycache__", "public", "tts_admin", "readme.md"
}

# ─── 工具函数 ─────────────────────────────────────────────
def local_to_cdn_url(local_path: str) -> str:
    """本地路径 → CDN 访问 URL"""
    rel = os.path.relpath(local_path, LOCAL_BASE).replace(os.sep, "/").strip("/")
    return f"{CDN_BASE}/{CDN_PATH_PREFIX}/{rel}"


def local_to_purge_url(local_path: str) -> str:
    """本地路径 → CDN 清缓存 URL"""
    return local_to_cdn_url(local_path).replace(
        "https://cdn.jsdelivr.net",
        "https://purge.jsdelivr.net"
    )


def is_skipped(entry: str) -> bool:
    """判断目录/文件是否应被扫描跳过（大小写不敏感 + 隐藏文件）"""
    if entry.startswith("."):
        return True
    return entry.lower() in {s.lower() for s in SCAN_SKIP}


# ─── CDN 操作函数 ─────────────────────────────────────────
def probe_cdn(url: str) -> dict:
    """HEAD 探测 CDN 文件是否存在"""
    try:
        r = requests.head(url, timeout=10, allow_redirects=True)
        return {
            "ok": r.status_code == 200,
            "status": r.status_code,
            "size": r.headers.get("content-length", "0"),
        }
    except Exception as e:
        return {"ok": False, "status": 0, "error": str(e)}


def purge_cdn(purge_url: str) -> bool:
    """提交 jsDelivr 清缓存请求"""
    try:
        r = requests.get(purge_url, timeout=10)
        return r.status_code in (200, 204)
    except Exception:
        return False