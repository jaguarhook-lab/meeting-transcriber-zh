# -*- coding: utf-8 -*-
"""對照表與專有名詞校正。"""
import json
import re
import shutil
from pathlib import Path

import engines
from common import GLOSSARY, GLOSSARY_EXAMPLE, context_full, context_text, hms, known_pairs, known_prompt, load_known


def ensure_glossary(path: Path = GLOSSARY) -> None:
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
    """回傳新增筆數。"""
    have = {b for b, _ in load_glossary(path)}
    new = [(b, g) for b, g in pairs if b and g and b != g and b not in have]
    if new:
        with path.open("a", encoding="utf-8") as f:
            for b, g in new:
                f.write(f"{b}\t{g}\n")
    return len(new)


def apply(rows: list, pairs: list) -> tuple[list, dict]:
    """長詞先換。"""
    pairs = sorted({(b, g) for b, g in pairs if b and b != g}, key=lambda p: -len(p[0]))
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
    """只保留逐字稿裡真的有的詞。"""
    log(f"請 {engine} 找疑似誤辨識的專有名詞（約需數分鐘）…")
    known = load_known()
    note = ("以下是寫法已確認正確的已知名詞（括號內為說明），不要列出；但逐字稿中它們的音近錯字仍要列，"
            "建議寫法用這裡的寫法：\n" + known_prompt() + "\n\n") if known else ""
    bg = context_full()
    if "\n" in bg:
        note = "背景資料：\n" + bg + "\n\n" + note
    out = engines.run(engine, TERMS_PROMPT.replace("{情境}", context_text()).replace("逐字稿：\n", note + "逐字稿：\n")
                         + to_text(rows))
    m = re.search(r"\[.*\]", out, re.S)
    if not m:
        raise RuntimeError(f"{engine} 回傳的內容不是 JSON：{out[:200]}")
    try:
        data = json.loads(m.group(0))
    except ValueError as e:
        raise RuntimeError(f"{engine} 回傳的 JSON 格式有誤（{e}）：{out[:200]}")
    if not isinstance(data, list):
        raise RuntimeError(f"{engine} 回傳的不是清單：{out[:200]}")

    def text(v) -> str:
        # null、清單、物件都當空白，免得 "None" 被當成建議寫法
        return str(v).strip() if isinstance(v, (str, int, float)) and not isinstance(v, bool) else ""

    items, seen, bad = [], set(), 0
    for it in data:
        if not isinstance(it, dict):
            bad += 1
            continue
        w = text(it.get("原詞"))
        if not w or w in seen or w in known:
            continue
        n, ex = occurrences(rows, w)
        if n == 0:
            continue
        seen.add(w)
        items.append({"原詞": w, "建議": text(it.get("建議")), "類別": text(it.get("類別")),
                      "理由": text(it.get("理由")), "次數": n, "例句": ex})
    if bad:
        log(f"注意：{engine} 的回覆有 {bad} 筆格式不對，已略過。")
    log(f"{engine} 列出 {len(items)} 個疑問詞")
    return items


def write_record(path: Path, applied: dict, pending: list) -> None:
    md = ["# 逐字稿校正紀錄", "", "| 原辨識 | 校正為 | 次數 |", "|---|---|---|"]
    md += [f"| {b} | {g} | {c} |" for (b, g), c in applied.items() if c]
    md += ["", f"合計替換 {sum(applied.values())} 處。", ""]
    if pending:
        md += ["## 待確認（未替換）", ""] + [f"- {w}" for w in pending]
    path.write_text("\n".join(md) + "\n", encoding="utf-8")
