import shutil
from pathlib import Path

root = Path(r"C:\Users\hzy12\ai_automation_hub")
docs = root / "docs"
dist_app = root / "dist" / "meeting_prep"

# 清理 docs 下非使用手册的 pdf（测试残留）
for p in docs.glob("*.pdf"):
    if p.name != "使用手册.pdf":
        p.unlink()

# 分发文档到绿色版目录
for name in ("使用手册.pdf", "guide.md"):
    src = docs / name
    if src.exists():
        shutil.copy2(src, dist_app / name)
        print("已分发:", name)

print("docs 目录:", [p.name for p in docs.iterdir()])
print("dist 内文档:", [p.name for p in dist_app.iterdir() if p.name in ("使用手册.pdf", "guide.md")])
