# -*- coding: utf-8 -*-
"""會議記錄與專題整理的提示詞。"""
import re

import engines
import prompts
from common import context_full, known_prompt, load_known

SPLIT = "<<<待確認>>>"

# 範本（寫作規則、會議記錄、專題整理）改由 prompts.py 管理：原廠預設 → 我的預設 → 本次送出


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


def minutes_prompt(name: str, audio: str, transcript_name: str, pending: list, topic: str,
                   engine: str = "Claude Code", confirmed: list = (), override: str | None = None,
                   materials: str = "") -> str:
    """組好的會議記錄提示（不含逐字稿本文）。override＝本次送出時改過的範本。"""
    note = f"（另有專題整理「{topic}」，正式記錄中該主題只需簡述並註明見專題。）" if topic else ""
    return prompts.build("會議記錄", {"會議名稱": name, "錄音檔名": audio, "逐字稿檔名": transcript_name,
                                     "背景資料": _context(pending, confirmed), "專題說明": note,
                                     "AI名稱": engine, "分隔線": SPLIT, "會議資料": materials}, override)


def topic_prompt(name: str, topic: str, pending: list, engine: str = "Claude Code", confirmed: list = (),
                 override: str | None = None, materials: str = "") -> str:
    return prompts.build("專題整理", {"主題": topic, "會議名稱": name, "背景資料": _context(pending, confirmed),
                                     "AI名稱": engine, "會議資料": materials}, override)


def minutes(name: str, audio: str, transcript_name: str, text: str, pending: list, topic: str, log,
            engine: str = "Claude Code", confirmed: list = (), prompt: str | None = None) -> str:
    """回傳原始輸出，用 split_minutes() 拆開。prompt＝已組好的提示（送出前檢視過的）。"""
    log(f"請 {engine} 撰寫會議記錄（約需數分鐘）…")
    p = prompt if prompt is not None else minutes_prompt(name, audio, transcript_name, pending, topic, engine, confirmed)
    return _clean(engines.run(engine, p + text))


def topic_report(name: str, topic: str, text: str, pending: list, log, engine: str = "Claude Code",
                 confirmed: list = (), prompt: str | None = None) -> str:
    log(f"請 {engine} 撰寫專題「{topic}」（約需數分鐘）…")
    p = prompt if prompt is not None else topic_prompt(name, topic, pending, engine, confirmed)
    return _clean(engines.run(engine, p + text))
