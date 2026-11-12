# -*- coding: utf-8 -*-
"""python build.py → dist\\錄音轉文字\\（不含語音模型）

PyInstaller 會清空輸出資料夾，所以先備份裡面的對照表與已知名詞，打包後放回。
"""
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIST = HERE / "dist" / "錄音轉文字"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    backup = None
    if (DIST / "對照表.tsv").exists():
        backup = HERE / f"對照表_打包前備份_{time.strftime('%Y%m%d_%H%M%S')}.tsv"
        shutil.copy2(DIST / "對照表.tsv", backup)
        print("已備份可攜版對照表：", backup.name)
    known_bak = None
    if (DIST / "已知名詞.txt").exists():
        known_bak = HERE / f"已知名詞_打包前備份_{time.strftime('%Y%m%d_%H%M%S')}.txt"
        shutil.copy2(DIST / "已知名詞.txt", known_bak)
        print("已備份可攜版已知名詞：", known_bak.name)

    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--windowed", "--name", "錄音轉文字",
           "--distpath", str(HERE / "dist"), "--workpath", str(HERE / "build"), "--specpath", str(HERE),
           "--collect-data", "faster_whisper", "--collect-binaries", "ctranslate2", "--collect-all", "onnxruntime",
           "--collect-data", "opencc", "--collect-all", "av", "--collect-all", "pymupdf", "--hidden-import", "tokenizers",
           "--hidden-import", "markdown.extensions.tables", "--hidden-import", "markdown.extensions.sane_lists"]
    # 環境裡有但用不到的大套件
    for m in ("matplotlib", "pandas", "scipy", "sqlalchemy", "PIL", "lxml", "cryptography", "bcrypt", "aiohttp",
              "pydantic", "pydantic_core", "orjson", "greenlet", "kiwisolver", "contourpy", "email_validator",
              "IPython", "jupyter", "notebook", "pytest", "win32com", "pythoncom"):
        cmd += ["--exclude-module", m]
    cmd.append(str(HERE / "app.py"))
    if subprocess.run(cmd).returncode != 0:
        print("打包失敗")
        return 1

    if backup or (HERE / "對照表.tsv").exists():
        shutil.copy2(backup or HERE / "對照表.tsv", DIST / "對照表.tsv")
    shutil.copy2(HERE / "情境說明.txt" if (HERE / "情境說明.txt").exists() else HERE / "情境說明.範例.txt",
                 DIST / "情境說明.txt")
    if known_bak or (HERE / "已知名詞.txt").exists():
        shutil.copy2(known_bak or HERE / "已知名詞.txt", DIST / "已知名詞.txt")
    for f in ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "對照表.範例.tsv", "情境說明.範例.txt", "已知名詞.範例.txt"):
        if (HERE / f).exists():
            shutil.copy2(HERE / f, DIST / f)
    size = sum(p.stat().st_size for p in DIST.rglob("*") if p.is_file()) / 1024 ** 2
    print(f"完成：{DIST}（{size:,.0f} MB）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
