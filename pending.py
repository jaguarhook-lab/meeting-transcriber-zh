# -*- coding: utf-8 -*-
"""待確認清單（_待確認.md）解析，以及在會議記錄中找詞、替換、拿掉（?）。

清單每項格式（AI 產生，寫法會有差異）：
  - 王先生（?）：說明…（01:58:57、01:59:18）
  - 小明、小華、阿美（?）：…          ← 一項多個詞
  - ABC（?）DEF：…／大華（輪（?））：…   ← （?）在詞中間
  - 某某等船：…                          ← 沒有（?）
  - 「X123」「Y45」：…                   ← 加引號
冒號前是詞（label），之後是說明；時間點取 HH:MM:SS。
"""
import re

Q = "（?）"
TS = re.compile(r"\b(\d{1,2}):(\d{2}):(\d{2})\b")


def _secs(h, m, s):
    return int(h) * 3600 + int(m) * 60 + int(s)


def parse(text: str) -> list:
    """→ [{cat, label, alts, note, times[秒], line}]；cat＝所屬 ## 標題。"""
    items, cat = [], "其他"
    for line in text.splitlines():
        h = re.match(r"^\s*#{2,}\s*(.+?)\s*$", line)
        if h:
            cat = h.group(1)
            continue
        m = re.match(r"^\s*[-*]\s+(.+)$", line)
        if not m:
            continue
        body = m.group(1).replace("**", "")
        if re.match(r"^(錄音檔|說明|整理工具)[：:]", body):           # 檔頭說明，不是待確認項
            continue
        k = body.find("：")
        if k < 0:
            mm = re.search(r"(?<!\d):(?!\d)", body)             # 半形冒號，但不是時間裡的冒號
            k = mm.start() if mm else -1
        if k <= 0:                                                # 整句說明，沒有「詞：」
            items.append(dict(cat=cat, kind="note", label=body[:24] + ("…" if len(body) > 24 else ""), alts=[],
                              note=body, times=[_secs(*t) for t in TS.findall(body)], line=line.strip()))
            continue
        label, note = body[:k].strip(), body[k + 1:].strip()
        if re.fullmatch(r"[\d:：–\-~～、，, ]+", label) and TS.search(label):   # 「01:17:20：…」時間點項目
            items.append(dict(cat=cat, kind="time", label=label, alts=[], note=note,
                              times=[_secs(*t) for t in TS.findall(label)], line=line.strip()))
            continue
        plain = label.replace(Q, "").replace("(?)", "")
        alts = [a.strip(" 「」『』\"'") for a in re.split(r"[／/、]|」「", plain)]
        alts = [a for a in alts if a]
        items.append(dict(cat=cat, kind="term", label=label, alts=alts, note=note,
                          times=[_secs(*t) for t in TS.findall(note)], line=line.strip()))
    return items


def spans(text: str, item: dict) -> list:
    """記錄中這一項的出現位置 → [(start, end, marked)]；marked＝帶（?）的。不重疊，依位置排序。
    時間點項目：找正文裡同樣的時間字串（記錄各段標有時間範圍），只供跳轉。"""
    if item.get("kind") == "time":
        out = []
        for t in dict.fromkeys(m.group(0) for m in TS.finditer(item["label"])):
            i = text.find(t)
            while i >= 0:
                out.append((i, i + len(t), False))
                i = text.find(t, i + 1)
        return sorted(set(out))
    if item.get("kind") == "note":
        return []
    cands = []
    if Q in item["label"]:
        cands.append((item["label"], True))                         # 例「ABC（?）DEF」整段
    for a in item["alts"]:
        cands.append((a + Q, True))
    for a in item["alts"]:
        if len(a) >= 2:
            cands.append((a, False))
    found = []
    for pat, marked in sorted(cands, key=lambda c: (-c[1], -len(c[0]))):   # 先帶（?）、長的
        i = text.find(pat)
        while i >= 0:
            e = i + len(pat)
            if not any(s < e and i < ee for s, ee, _ in found):
                found.append((i, e, marked))
            i = text.find(pat, i + 1)
    return sorted(found)


def counts(text: str, item: dict) -> tuple:
    sp = spans(text, item)
    return sum(1 for *_x, m in sp if m), sum(1 for *_x, m in sp if not m)


def replace_span(text: str, span: tuple, new: str) -> str:
    s, e, _m = span
    return text[:s] + new + text[e:]


def replace_all(text: str, item: dict, new: str, include_plain: bool = False) -> tuple:
    """標（?）的處（include_plain 時連沒標的）換成 new。→ (新文字, 換了幾處)。從後往前換，位置不亂。"""
    n = 0
    for sp in reversed(spans(text, item)):
        if sp[2] or include_plain:
            text = replace_span(text, sp, new)
            n += 1
    return text, n


def confirm(text: str, item: dict) -> tuple:
    """確認無誤：保留原詞，只拿掉帶（?）處的（?）。→ (新文字, 處數)。"""
    n = 0
    for s, e, m in reversed(spans(text, item)):
        if m:
            text = text[:s] + text[s:e].replace(Q, "") + text[e:]
            n += 1
    return text, n


# ── 記錄開頭的基本資料表格 ──────────────────────────────────────────────
FIELDS = ("日期／時間", "地點", "主持人", "記錄人", "出席人員")


def header_get(text: str) -> dict:
    out = {}
    for line in text.splitlines()[:40]:
        m = re.match(r"^\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*$", line)
        if m and m.group(1) in FIELDS:
            out[m.group(1)] = m.group(2)
    return out


def header_set(text: str, values: dict) -> str:
    lines = text.split("\n")
    for i, line in enumerate(lines[:40]):
        m = re.match(r"^\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*$", line)
        if m and m.group(1) in values:
            lines[i] = f"| {m.group(1)} | {values[m.group(1)].replace('|', '／')} |"
    return "\n".join(lines)
