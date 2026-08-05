import ctypes
import os
import shutil
import sys
import zipfile
from pathlib import Path


def msg(text, title="会议准备工作台 安装程序", icon=0x40):
    ctypes.windll.user32.MessageBoxW(0, text, title, icon)


def create_shortcut(exe):
    from win32com.client import Dispatch

    ws = Dispatch("WScript.Shell")
    desktop = ws.SpecialFolders("Desktop")
    lnk = ws.CreateShortcut(str(Path(desktop) / "会议准备工作台.lnk"))
    lnk.TargetPath = str(exe)
    lnk.WorkingDirectory = str(exe.parent)
    lnk.Save()


def find_zip():
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(getattr(sys, "_MEIPASS", "")) / "meeting_prep_pkg.zip")
        candidates.append(Path(sys.executable).parent / "meeting_prep_pkg.zip")
    candidates.append(Path(__file__).resolve().parent / "meeting_prep_pkg.zip")
    for c in candidates:
        if c.exists():
            return c
    return None


def main():
    target = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "meeting_prep"
    zip_path = find_zip()
    if zip_path is None:
        msg("未找到安装数据包，安装失败。", icon=0x10)
        return 1
    try:
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(target)
        exe = target / "meeting_prep.exe"
        if not exe.exists():
            msg("程序文件缺失，安装失败。", icon=0x10)
            return 1
        create_shortcut(exe)
        msg("安装完成！已创建桌面快捷方式「会议准备工作台」。\n\n"
            "桌面窗口 + Web 端 http://127.0.0.1:8780\n"
            "手机联动端口 8781（鸿蒙端对接）")
        try:
            import subprocess
            subprocess.Popen([str(exe)])
        except Exception:
            pass
        return 0
    except Exception as e:
        msg(f"安装失败：{e}", icon=0x10)
        return 1


if __name__ == "__main__":
    sys.exit(main())
