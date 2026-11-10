# -*- coding: utf-8 -*-
"""專有名詞：共用對照表、套用校正、請 AI 找疑問詞。"""
import json
import re
import shutil
from pathlib import Path

import ai_engines
from common import GLOSSARY, GLOSSARY_EXAMPLE, context_text, hms


def ensure_glossary(path: Path = GLOSSARY) -> None:
    """沒有對照表時，從範例複製一份開始用。"""
    if not path.exists() and GLOSSARY_EXAMPLE.exists():
        shutil.copyfile(GLOSSARY_EXAMPLE, path)


def load_glossary(path: Path = GLOSSARY) -> list:
    ensure_glossary(path)
    pairs = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#") and "\t" in line:
                bad, good = line.split("\t")[:2]
                if bad and bad != good:
                    pairs.append((bad, good))
    return pairs


def add_to_glossary(pairs: list, path: Path = GLOSSARY) -> int:
    """把新對照加到共用對照表最後面（已有的原詞不重複加）。回傳新增筆數。"""
    have = {b for b, _ in load_glossary(path)}
    new = [(b, g) for b, g in pairs if b and g and b != g and b not in have]
    if new:
        with path.open("a", encoding="utf-8") as f:
            for b, g in new:
                f.write(f"{b}\t{g}\n")
    return len(new)


def apply(rows: list, pairs: list) -> tuple[list, dict]:
    """依序替換（長詞優先），回傳新段落與各對照的替換次數。"""
    pairs = sorted(pairs, key=lambda p: -len(p[0]))
    counts = {p: 0 for p in pairs}
    out = []
    for r in rows:
        t = r["text"]
        for bad, good in pairs:
            n = t.count(bad)
            if n:
                counts[(bad, good)] += n
                t = t.replace(bad, good)
        out.append({**r, "text": t})
    return out, counts


def to_text(rows: list) -> str:
    return "".join(f"[{hms(r['start'])}] {r['text']}\n" for r in rows)


def occurrences(rows: list, word: str, limit: int = 3) -> tuple[int, list]:
    """回傳出現次數與前幾個 (秒, 該段文字)。"""
    n, ex = 0, []
    for r in rows:
        c = r["text"].count(word)
        if c:
            n += c
            if len(ex) < limit:
                ex.append((r["start"], r["text"]))
    return n, ex


TERMS_PROMPT = """以下是{情境}的語音辨識逐字稿，繁體中文，每行開頭是時間點。
語音辨識常把人名、公司名、產品或設備名、專有名詞辨識成音近的錯字。請找出「疑似誤辨識」且對理解會議重要的詞。

規則：
- 只列逐字稿中實際出現的原詞（原詞必須能在逐字稿中原樣找到）。
- 同一個人名或名稱的不同錯誤寫法，各列一項，建議寫法要一致。
- 不確定正確寫法時，「建議」填空字串，不要臆測。
- 最多 60 項，依重要性排序。
- 只輸出 JSON 陣列，不要任何說明文字或程式碼框。格式：
[{"原詞": "...", "建議": "...", "類別": "人名|公司|產品或設備|專有名詞|其他", "理由": "一句話"}]

逐字稿：
"""


def find_suspects(rows: list, log, engine: str = "Claude Code") -> list:
    """請 Claude Code 找疑問詞，回傳 [{原詞, 建議, 類別, 理由, 次數, 例句}]（只保留逐字稿真的有的詞）。"""
    log(f"請 {engine} 找疑似誤辨識的專有名詞（約需數分鐘）…")
    out = ai_engines.run(engine, TERMS_PROMPT.replace("{情境}", context_text()) + to_text(rows))
    m = re.search(r"\[.*\]", out, re.S)
    if not m:
        raise RuntimeError(f"{engine} 回傳的內容不是 JSON：{out[:200]}")
    items, seen = [], set()
    for it in json.loads(m.group(0)):
        w = str(it.get("原詞", "")).strip()
        if not w or w in seen:
            continue
        n, ex = occurrences(rows, w)
        if n == 0:
            continue
        seen.add(w)
        items.append({"原詞": w, "建議": str(it.get("建議", "")).strip(), "類別": it.get("類別", ""),
                      "理由": it.get("理由", ""), "次數": n, "例句": ex})
    log(f"{engine} 列出 {len(items)} 個疑問詞")
    return items


def write_record(path: Path, applied: dict, pending: list) -> None:
    """校正紀錄：套用的對照與次數、待確認詞。"""
    md = ["# 逐字稿校正紀錄", "", "| 原辨識 | 校正為 | 次數 |", "|---|---|---|"]
    md += [f"| {b} | {g} | {c} |" for (b, g), c in applied.items() if c]
    md += ["", f"合計替換 {sum(applied.values())} 處。", ""]
    if pending:
        md += ["## 待確認（未替換）", ""] + [f"- {w}" for w in pending]
    path.write_text("\n".join(md) + "\n", encoding="utf-8")
