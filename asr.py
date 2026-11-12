# -*- coding: utf-8 -*-
"""語音辨識（faster-whisper，CPU）與語音模型下載。

音檔先轉成 16k wav 放在工作資料夾，續跑和播放片段都用它。辨識結果邊跑邊寫 jsonl，
中斷後從最後一段接著跑。faster-whisper 1.2 指定 clip_timestamps 會忽略 VAD，
所以續跑時自己切音訊陣列，再把時間加回去。

模型找的順序：%LOCALAPPDATA%\\錄音轉文字\\models、程式資料夾的 models、使用者自選的資料夾。
"""
import json
import os
import time
import wave
from pathlib import Path

import numpy as np

from common import base_dir, context_text, hms

SR = 16000
FIXES = {"隻有": "只有", "隻是": "只是", "隻要": "只要", "隻能": "只能", "許可權": "權限"}

# 語言選單：顯示名稱 → (whisper 語言代碼, 是否多語逐段判斷)
LANGUAGES = {
    "中文（繁體輸出）": ("zh", False),
    "英文": ("en", False),
    "日文": ("ja", False),
    "自動偵測（整場同一語言）": (None, False),
    "多語混合（逐段判斷，較慢）": (None, True),
}

# 下載選單：名稱 → (Hugging Face 儲存庫, 約略大小, 說明)
DOWNLOADS = {
    "large-v3-turbo": ("mobiuslabsgmbh/faster-whisper-large-v3-turbo", "1.6 GB",
                       "【建議】一般會議記錄用這個。準確度接近 large-v3，速度快一倍以上。"),
    "small": ("Systran/faster-whisper-small", "0.5 GB",
              "最快，但中文人名、公司名、專有名詞錯字明顯較多。適合快速了解大概內容。"),
    "large-v3": ("Systran/faster-whisper-large-v3", "3.1 GB",
                 "最準，但速度約為 turbo 的一半以下。適合重要會議或錄音品質差時。建議記憶體 8 GB 以上。"),
}
REQUIRED = ("model.bin", "config.json", "tokenizer.json")


def user_models_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "錄音轉文字" / "models"


def model_dirs() -> list:
    return [user_models_dir(), base_dir() / "models"]


def check_model(path: Path) -> list:
    path = Path(path)
    missing = [f for f in REQUIRED if not (path / f).exists()]
    if not ((path / "vocabulary.json").exists() or (path / "vocabulary.txt").exists()):
        missing.append("vocabulary.json 或 vocabulary.txt")
    return missing


def list_models() -> list:
    out, seen = [], set()
    for d in model_dirs():
        if not d.exists():
            continue
        for sub in sorted(d.iterdir()):
            if sub.is_dir() and not check_model(sub) and sub.name not in seen:
                seen.add(sub.name)
                where = "本機" if d == user_models_dir() else "程式資料夾"
                out.append((f"{sub.name}（{where}）", str(sub)))
    return out


def download_model(name: str, progress, cancel, log) -> Path:
    """先存成 .part，取消時保留，下次接著下載。"""
    import requests
    from huggingface_hub import HfApi, hf_hub_url
    repo = DOWNLOADS[name][0]
    dest = user_models_dir() / name
    dest.mkdir(parents=True, exist_ok=True)
    files = [(s.rfilename, s.size or 0) for s in HfApi().model_info(repo, files_metadata=True).siblings
             if s.rfilename not in (".gitattributes", "README.md")]
    total = sum(sz for _, sz in files)
    done_before = sum(sz for f, sz in files if (dest / f).exists())
    got = done_before
    log(f"下載 {name}（{total / 1024 ** 3:.2f} GB）到 {dest}")
    for fname, size in files:
        target = dest / fname
        if target.exists():
            continue
        part = dest / (fname + ".part")
        start = part.stat().st_size if part.exists() else 0
        got += start
        headers = {"Range": f"bytes={start}-"} if start else {}
        with requests.get(hf_hub_url(repo, fname), headers=headers, stream=True, timeout=60) as r:
            r.raise_for_status()
            mode = "ab" if start and r.status_code == 206 else "wb"
            if mode == "wb":
                got -= start
            with part.open(mode) as f:
                for chunk in r.iter_content(1024 * 1024):
                    if cancel.is_set():
                        log("已取消下載；下次再按下載會從中斷處接著下載")
                        return dest
                    f.write(chunk)
                    got += len(chunk)
                    progress(got, total)
        part.replace(target)
    progress(total, total)
    miss = check_model(dest)
    if miss:
        raise RuntimeError(f"下載後檢查缺少：{'、'.join(miss)}")
    log(f"下載完成：{dest}")
    return dest


def ensure_wav(audio: Path, wav: Path, log) -> np.ndarray:
    if wav.exists():
        with wave.open(str(wav), "rb") as w:
            data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        return data.astype(np.float32) / 32768.0
    from faster_whisper import decode_audio
    log("音檔轉換中（轉成 16k 單聲道）…")
    a = decode_audio(str(audio), sampling_rate=SR)
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(a, -1, 1) * 32767).astype(np.int16).tobytes())
    return a


def read_rows(jsonl: Path) -> list:
    if not jsonl.exists():
        return []
    return [json.loads(l) for l in jsonl.read_text(encoding="utf-8").splitlines() if l.strip()]


def transcribe(audio: Path, workdir: Path, log, progress, cancel, model_dir: str,
               language: str = "中文（繁體輸出）", threads: int = 4) -> list:
    """progress(已辨識秒, 總秒, 預估剩餘秒)"""
    miss = check_model(Path(model_dir))
    if miss:
        raise RuntimeError(f"語音模型不完整（{model_dir}），缺少：{'、'.join(miss)}")
    lang, multi = LANGUAGES[language]
    workdir.mkdir(parents=True, exist_ok=True)
    wav = workdir / "audio_16k.wav"
    jsonl = workdir / "逐字稿_原始.jsonl"
    audio_arr = ensure_wav(audio, wav, log)
    duration = len(audio_arr) / SR

    rows = read_rows(jsonl)
    offset = rows[-1]["end"] if rows else 0.0
    if offset >= duration - 1:
        log(f"已辨識完成（{len(rows)} 段），不需重跑")
        progress(duration, duration, 0)
        return rows
    if rows:
        log(f"續跑：既有 {len(rows)} 段，從 {hms(offset)} 開始")

    from faster_whisper import WhisperModel
    from opencc import OpenCC
    log(f"載入語音模型（{Path(model_dir).name}），語言：{language}…")
    model = WhisperModel(model_dir, device="cpu", compute_type="int8", cpu_threads=threads)
    segments, info = model.transcribe(
        audio_arr[int(offset * SR):],
        language=lang, multilingual=multi, beam_size=2, vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        initial_prompt=f"以下是{context_text()}的繁體中文錄音。" if lang == "zh" else None,
        condition_on_previous_text=False,
    )
    to_trad = lang == "zh" or multi or (lang is None and info.language == "zh")
    cc = OpenCC("s2tw") if to_trad else None  # 不用 s2twp：會把「权限」轉成「許可權」
    if lang is None and not multi:
        log(f"自動偵測語言：{info.language}（信心 {info.language_probability:.0%}）")
    log(f"開始辨識，音檔長度 {hms(duration)}")
    t0 = time.time()
    with jsonl.open("a", encoding="utf-8") as f:
        for seg in segments:
            text = seg.text.strip()
            if cc:
                text = cc.convert(text)
                for bad, good in FIXES.items():
                    text = text.replace(bad, good)
            if text:
                row = {"id": len(rows) + 1, "start": round(seg.start + offset, 2),
                       "end": round(seg.end + offset, 2), "text": text}
                rows.append(row)
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                done = row["end"] - offset
                ratio = (time.time() - t0) / max(done, 1)
                progress(row["end"], duration, (duration - row["end"]) * ratio)
            if cancel.is_set():
                log(f"已取消，辨識到 {hms(rows[-1]['end']) if rows else '00:00:00'}；下次按「開始辨識」會續跑")
                return rows
    progress(duration, duration, 0)
    log(f"辨識完成：{len(rows)} 段，耗時 {hms(time.time() - t0)}")
    return rows


def clip_wav(workdir: Path, start: float, end: float, out: Path) -> Path:
    with wave.open(str(workdir / "audio_16k.wav"), "rb") as w:
        n = w.getnframes()
        s, e = max(0, int(start * SR)), min(n, int(end * SR))
        w.setpos(s)
        frames = w.readframes(e - s)
    with wave.open(str(out), "wb") as o:
        o.setnchannels(1)
        o.setsampwidth(2)
        o.setframerate(SR)
        o.writeframes(frames)
    return out
