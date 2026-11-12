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
KNOWN = base_dir() / "已知名詞.txt"
KNOWN_EXAMPLE = base_dir() / "已知名詞.範例.txt"
DEFAULT_CONTEXT = "一場公司內部會議"


def load_known_entries() -> list:
    """已知名詞：一行一筆「名詞｜說明｜常被誤寫成」，後兩欄可省略；誤寫用頓號或逗號分隔。# 開頭為註解。
    回傳 [{"詞", "說明", "誤寫": [...]}]（同一詞只留第一筆）。沒有檔案時從範例建立。"""
    import re
    try:
        if not KNOWN.exists() and KNOWN_EXAMPLE.exists():
            KNOWN.write_text(KNOWN_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
        out, seen = [], set()
        for line in KNOWN.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            cols = [c.strip() for c in re.split(r"[｜|]", line)]
            word = cols[0]
            if not word or word in seen:
                continue
            seen.add(word)
            wrong = [w.strip() for w in re.split(r"[、,，]", cols[2])] if len(cols) > 2 else []
            out.append({"詞": word, "說明": cols[1] if len(cols) > 1 else "",
                        "誤寫": [w for w in wrong if w and w != word]})
        return out
    except Exception:
        return []


def load_known() -> list:
    """已知名詞的詞本身（寫法確定正確的人名、公司、船名等）。"""
    return [e["詞"] for e in load_known_entries()]


def known_pairs() -> list:
    """已知名詞的「常被誤寫成」→ 正確寫法，當成對照表使用。"""
    return [(w, e["詞"]) for e in load_known_entries() for w in e["誤寫"]]


def known_prompt() -> str:
    """給 AI 的已知名詞說明文字（每行：詞（說明；常被誤寫成：…））。"""
    lines = []
    for e in load_known_entries():
        extra = "；".join(x for x in (e["說明"], ("常被誤寫成：" + "、".join(e["誤寫"])) if e["誤寫"] else "") if x)
        lines.append(f"- {e['詞']}" + (f"（{extra}）" if extra else ""))
    return "\n".join(lines)


def merge_known(word: str, desc: str = "", wrong: list = ()) -> str:
    """新增或更新一筆已知名詞：已有就把新的誤寫加到第三欄、說明空白時補上；沒有就加到最後。
    回傳「新增」「更新」或「不變」。"""
    import re
    word = word.strip()
    wrong = [w.strip() for w in wrong if w and w.strip() and w.strip() != word]
    if not word:
        return "不變"
    lines = KNOWN.read_text(encoding="utf-8").splitlines() if KNOWN.exists() else []
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#") or not line.strip():
            continue
        cols = [c.strip() for c in re.split(r"[｜|]", line)]
        if cols[0] != word:
            continue
        old_desc = cols[1] if len(cols) > 1 else ""
        old_wrong = [w.strip() for w in re.split(r"[、,，]", cols[2])] if len(cols) > 2 else []
        new_wrong = [w for w in wrong if w not in old_wrong]
        new_desc = old_desc or desc.strip()
        if not new_wrong and new_desc == old_desc:
            return "不變"
        all_wrong = [w for w in old_wrong if w] + new_wrong
        lines[i] = "｜".join([word, new_desc] + (["、".join(all_wrong)] if all_wrong else [])).rstrip("｜")
        KNOWN.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return "更新"
    entry = "｜".join([word, desc.strip()] + (["、".join(wrong)] if wrong else [])).rstrip("｜")
    add_known([entry])
    return "新增"


def add_known(words: list) -> int:
    """把詞加到已知名詞最後面（已有的不重複加）。words 的元素可以是「詞」或「詞｜說明｜誤寫」。回傳新增筆數。"""
    import re
    have = set(load_known())
    new, seen = [], set()
    for w in words:
        w = (w or "").strip()
        key = re.split(r"[｜|]", w)[0].strip()
        if key and key not in have and key not in seen:
            seen.add(key)
            new.append(w)
    if new:
        text = KNOWN.read_text(encoding="utf-8") if KNOWN.exists() else ""
        if text and not text.endswith("\n"):
            text += "\n"
        KNOWN.write_text(text + "\n".join(new) + "\n", encoding="utf-8")
    return len(new)


def _context_lines() -> list:
    try:
        return [l.strip() for l in CONTEXT.read_text(encoding="utf-8").splitlines()
                if l.strip() and not l.lstrip().startswith("#")]
    except Exception:
        return []


def context_text() -> str:
    """會議類型（一句話，給語音辨識提示與找詞提示）：情境說明.txt 的第一行，沒有就用通用說明。"""
    lines = _context_lines()
    return lines[0] if lines else DEFAULT_CONTEXT


def context_full() -> str:
    """完整情境說明（多行：公司關係、「我方」是誰等），給寫會議記錄的 AI 參考。"""
    return "\n".join(_context_lines())


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
