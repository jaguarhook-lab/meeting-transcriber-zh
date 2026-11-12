# -*- coding: utf-8 -*-
"""會議記錄與專題整理的提示詞。"""
import re

import engines
from common import context_full, known_prompt, load_known

SPLIT = "<<<待確認>>>"

COMMON_RULES = """寫作規則：
- 繁體中文（台灣用字），Markdown 格式，只輸出文件內容本身，不要前言、不要程式碼框。
- 只寫逐字稿中實際講到的內容，不臆測、不補充會議沒講的事。
- 錄音沒有區分發言者：以職務、角色或人名描述。背景資料可用來判斷「指的是誰、哪家公司、彼此關係」，但不要寫出逐字稿沒講的事。
- 每個議題的討論要點都附錄音時間點（hh:mm:ss 或 hh:mm:ss–hh:mm:ss，放在全形括號內），方便回查。
- 聽不清楚或判斷不出的內容加「（?）」；寧可標待確認，不要寫錯。
- 疑似同一人（或同一名稱）的多種音近寫法，正文統一用其中出現最多的一種寫法加「（?）」，不要並列多種；各種寫法列在待確認清單。
- 閒聊、與會議無關的段落省略。"""

MINUTES_PROMPT = """請依下方逐字稿，寫一份正式的會議記錄。
會議名稱：{name}
錄音檔名：{audio}
{context}
輸出分成兩部分，中間用單獨一行「{split}」分隔。

【第一部分：正式會議記錄】結構如下：
# {name} 會議記錄
| 項目 | 內容 |
|---|---|
| 日期／時間 | 從會議名稱或錄音檔名中的 8 位數日期取得，寫成 YYYY-MM-DD；取不到就留空。時間留空 |
| 地點 | 逐字稿有明講才寫，否則留空 |
| 主持人 | 逐字稿能明確判斷才寫，否則留空 |
| 記錄人 | 留空 |
| 出席人員 | 依發言內容列出確定在場的人名，最後加「（依錄音整理，請補齊）」 |

## 重點摘要
（3～5 條，每條一句話：最重要的決議、時程與風險）

## 議題一：＜標題＞（hh:mm:ss–hh:mm:ss）

**背景**：一兩句說明為什麼討論這件事

**討論**：

- 條列要點，每條結尾附錄音時間點

**決議**：明確的結論；沒有結論就寫「未決，見未決事項」

**待辦**：

- ＜負責人＞：＜做什麼＞（期限：＜日期或「未定」＞）；負責人不明寫「待確認」；沒有待辦寫「無」
（背景、討論、決議、待辦之間，以及清單前後，都要空一行）

## 議題二：…
（依討論順序；同一件事的前後段落合併成同一議題；議題數以 6～15 個為原則；議題標題用中文數字編號）

## 未決事項
（有爭議、沒定案、需要再決定的事；每項列出各方意見與下一步；沒有就寫「無」）

## 待辦追蹤表
| # | 事項 | 負責 | 期限 | 狀態 |
|---|---|---|---|---|
（彙整各議題的待辦；狀態一律寫「待辦」）

【第二部分：待確認清單（給整理者核對，不放進正式記錄）】結構如下：
# {name} 會議記錄－待確認事項
- 錄音檔：{audio}；逐字稿：{transcript}
- 說明：逐字稿由語音辨識產生，可能有錯字或漏字，內容以錄音為準；正式記錄中標「（?）」的地方表示聽不清楚、判斷不出，或寫法待確認。
- 整理工具：本記錄由 {engine} 依逐字稿整理
## 人名
## 公司名、船名
## 專有名詞
（列出正式記錄中所有加了（?）的詞與指定的待確認詞：寫法、時間點、可能的正確寫法；某類沒有就寫「無」）
## 內容待確認
（聽不清楚、前後矛盾、數字或日期不確定、錄音是否中途截止等需要回查錄音的地方，附時間點）
{topic_note}
{rules}

逐字稿：
"""

TOPIC_PROMPT = """請依下方逐字稿，針對主題「{topic}」寫一份專題整理。
會議名稱：{name}
{context}
要求：
- 說明中註明「本專題由 {engine} 依逐字稿整理」。
- 先找出逐字稿中討論此主題的段落，標明起訖時間；只整理這些段落實際講到的內容。
- 結構建議：說明（出處時間、說明文字）→ 為什麼要討論 → 現況與實例 → 討論出的做法或流程（依步驟條列，標出負責角色）→ **沒有定案、需要再決定的事（表格，列出各方意見與時間點）** → 會議中提到的待辦（- [ ] 清單）。
- 有爭議或沒定論的地方，一定要列在「沒有定案」那一節，不要寫成決議。
{rules}

逐字稿：
"""


def _clean(md: str) -> str:
    md = md.strip()
    m = re.match(r"^```(?:markdown|md)?\s*\n(.*)\n```$", md, re.S)
    return (m.group(1) if m else md).strip() + "\n"


def _context(words: list, confirmed: list = ()) -> str:
    out = []
    ctx = context_full()
    if ctx:
        out.append("背景資料（會議情境）：\n" + ctx)
    known = load_known()
    if known:
        out.append("已知名詞（寫法正確，照此寫法使用、不要加（?）；括號內是說明，可用來判斷所指的人或公司）：\n" + known_prompt())
    confirmed = [w for w in dict.fromkeys(confirmed) if w not in set(words) and w not in set(known)]
    if confirmed:
        out.append("以下寫法已經使用者在校正時確認，是正確的人名或名稱：請照此寫法使用，不要加（?），"
                   "也不要列入待確認清單：" + "、".join(confirmed))
    if words:
        out.append("以下詞語使用者已標為待確認，請在文中照原樣使用並加（?），並列入待確認清單：" + "、".join(words))
    return "\n\n".join(out) + ("\n" if out else "")


def split_minutes(md: str) -> tuple[str, str, str]:
    """回傳（正式記錄, 待確認清單, 問題）。分隔線要單獨一行、只出現一次、前後都有內容，否則「問題」非空。"""
    lines = md.splitlines()
    idx = [i for i, l in enumerate(lines) if l.strip() == SPLIT]
    if len(idx) != 1:
        if SPLIT in md:
            problem = f"分隔線「{SPLIT}」沒有單獨成行或出現 {md.count(SPLIT)} 次"
        else:
            problem = f"沒有分隔線「{SPLIT}」，待確認清單可能混在正式記錄裡"
        return _clean(md.replace(SPLIT, "")), "", problem
    main = "\n".join(lines[:idx[0]]).strip()
    pend = "\n".join(lines[idx[0] + 1:]).strip()
    if not main:
        return "", _clean(pend) if pend else "", "分隔線前面沒有正式記錄"
    if not pend:
        return _clean(main), "", "分隔線後面沒有待確認清單"
    return _clean(main), _clean(pend), ""


def minutes(name: str, audio: str, transcript_name: str, text: str, pending: list, topic: str, log,
            engine: str = "Claude Code", confirmed: list = ()) -> str:
    """回傳原始輸出，用 split_minutes() 拆開。"""
    log(f"請 {engine} 撰寫會議記錄（約需數分鐘）…")
    note = f"（另有專題整理「{topic}」，正式記錄中該主題只需簡述並註明見專題。）" if topic else ""
    p = MINUTES_PROMPT.format(name=name, audio=audio, transcript=transcript_name, context=_context(pending, confirmed),
                              topic_note=note, rules=COMMON_RULES, engine=engine, split=SPLIT)
    return _clean(engines.run(engine, p + text))


def topic_report(name: str, topic: str, text: str, pending: list, log, engine: str = "Claude Code",
                 confirmed: list = ()) -> str:
    log(f"請 {engine} 撰寫專題「{topic}」（約需數分鐘）…")
    p = TOPIC_PROMPT.format(name=name, topic=topic, context=_context(pending, confirmed), rules=COMMON_RULES, engine=engine)
    return _clean(engines.run(engine, p + text))
