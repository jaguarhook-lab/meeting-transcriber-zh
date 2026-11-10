# -*- coding: utf-8 -*-
"""共用工具：程式資料夾位置、設定檔、不覆蓋的檔名、時間格式。"""
import json
import sys
from pathlib import Path


def base_dir() -> Path:
    """程式所在資料夾：打包後是 exe 所在位置，開發時是本檔所在位置。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


GLOSSARY = base_dir() / "對照表.tsv"
GLOSSARY_EXAMPLE = base_dir() / "對照表.範例.tsv"
CONTEXT = base_dir() / "情境說明.txt"
SETTINGS = base_dir() / "設定.json"
DEFAULT_CONTEXT = "一場公司內部會議"


def context_text() -> str:
    """會議情境說明（給語音辨識與 AI 參考）：讀程式資料夾的 情境說明.txt，沒有就用通用說明。"""
    try:
        lines = [l.strip() for l in CONTEXT.read_text(encoding="utf-8").splitlines()
                 if l.strip() and not l.lstrip().startswith("#")]
        return "".join(lines) or DEFAULT_CONTEXT
    except Exception:
        return DEFAULT_CONTEXT


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(d: dict) -> None:
    try:
        SETTINGS.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def unique_path(p: Path) -> Path:
    """目標檔已存在就另存 (2)、(3)…，不覆蓋。"""
    p = Path(p)
    if not p.exists():
        return p
    i = 2
    while True:
        q = p.with_name(f"{p.stem} ({i}){p.suffix}")
        if not q.exists():
            return q
        i += 1


def hms(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def safe_name(s: str) -> str:
    """去掉 Windows 檔名不允許的字元。"""
    for ch in '\\/:*?"<>|':
        s = s.replace(ch, "_")
    return s.strip() or "會議"
