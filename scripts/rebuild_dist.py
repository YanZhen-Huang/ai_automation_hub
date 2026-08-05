import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

root = Path(r"C:\Users\hzy12\ai_automation_hub")
app = root / "dist" / "meeting_prep"
green_zip = root / "dist" / "meeting_prep_绿色版.zip"
pkg_zip = root / "build" / "meeting_prep_pkg.zip"

# 确保文档随包分发
for name in ("使用手册.pdf", "guide.md", "FULL_ANALYSIS.md"):
    src = root / "docs" / name
    if src.exists():
        shutil.copy2(src, app / name)
        print("分发文档:", name)


def make_zip(src_dir, out_zip):
    if out_zip.exists():
        out_zip.unlink()
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        for p in sorted(src_dir.rglob("*")):
            if p.is_dir():
                continue
            if "\\data\\" in str(p) or str(p).endswith("\\data"):
                continue
            z.write(p, p.relative_to(src_dir))
    print(f"zip: {out_zip.name} {out_zip.stat().st_size/1048576:.1f} MB")


make_zip(app, green_zip)
make_zip(app, pkg_zip)

r = subprocess.run(
    [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile",
     "--windowed", "--name", "meeting_prep_setup",
     "--add-data", f"{pkg_zip};.", "build/installer_setup.py"],
    cwd=str(root), capture_output=True, text=True, timeout=900)
print("setup rc:", r.returncode)
print((r.stdout or r.stderr)[-200:])
