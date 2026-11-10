# -*- coding: utf-8 -*-
"""錄音轉文字：圖形介面主程式。

流程：① 開始辨識 → ② 校正專有名詞 → ③ 產生會議記錄（md + pdf）→（編輯 md 後）重新產生 PDF
設定：AI（Claude Code／Codex）、語音模型（可下載、可自選資料夾）、語言
"""
import datetime as dt
import json
import os
import queue
import threading
import tkinter as tk
import traceback
import webbrowser
import winsound
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import ai_engines
import asr
import pdf
import report
import terms
from common import hms, load_settings, safe_name, save_settings, unique_path

AUDIO_TYPES = [("音檔", "*.m4a *.mp3 *.wav *.mp4 *.aac *.wma *.flac *.ogg *.mov"), ("全部檔案", "*.*")]
FONT = "Microsoft JhengHei"


def fmt_left(reset: dt.datetime) -> str:
    sec = int((reset - dt.datetime.now()).total_seconds())
    if sec <= 0:
        return "應已恢復"
    h, m = divmod(sec // 60, 60)
    return f"約 {h} 小時 {m} 分後" if h else f"約 {m} 分後"


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("錄音轉文字")
        root.geometry("900x720")
        root.minsize(780, 600)
        self.q = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.limit = None  # (engine, reset, message)
        self.settings = load_settings()

        style = ttk.Style()
        style.configure("Big.TButton", font=(FONT, 11, "bold"), padding=6)
        f = ttk.Frame(root, padding=12)
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)

        # 使用上限提示列（平常隱藏）
        self.banner = tk.Label(f, text="", bg="#c0392b", fg="white", font=(FONT, 10, "bold"),
                               anchor="w", padx=10, pady=6, wraplength=840, justify="left")

        self.v_audio = tk.StringVar()
        self.v_out = tk.StringVar(value=self.settings.get("out", ""))
        self.v_name = tk.StringVar()
        self.v_topic = tk.StringVar()

        def row(r, label, var, btn=None, cmd=None):
            ttk.Label(f, text=label).grid(row=r, column=0, sticky="w", pady=3)
            ttk.Entry(f, textvariable=var).grid(row=r, column=1, sticky="ew", padx=6)
            if btn:
                ttk.Button(f, text=btn, command=cmd).grid(row=r, column=2, sticky="ew")

        row(1, "音檔", self.v_audio, "選擇音檔…", self.pick_audio)
        row(2, "輸出資料夾", self.v_out, "選擇資料夾…", self.pick_out)
        row(3, "會議名稱", self.v_name)
        row(4, "特別整理的主題（選填）", self.v_topic)
        ttk.Label(f, text="例：採購流程、年度預算。有填會另外產出一份專題整理。", foreground="#666").grid(row=5, column=1, sticky="w", padx=6)

        # ---- 設定區：AI、語音模型、語言 ----
        sf = ttk.LabelFrame(f, text="設定", padding=8)
        sf.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(8, 4))
        sf.columnconfigure(1, weight=1)

        ttk.Label(sf, text="AI（解析與撰寫）").grid(row=0, column=0, sticky="w")
        af = ttk.Frame(sf)
        af.grid(row=0, column=1, columnspan=2, sticky="ew", padx=6)
        self.v_engine = tk.StringVar(value=self.settings.get("engine", "Claude Code"))
        cb = ttk.Combobox(af, textvariable=self.v_engine, values=list(ai_engines.ENGINES), state="readonly", width=14)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda _: self.refresh_engine())
        self.v_engine_st = tk.StringVar()
        self.lb_engine = ttk.Label(af, textvariable=self.v_engine_st, width=16)
        self.lb_engine.pack(side="left", padx=8)
        ttk.Button(af, text="登入帳號", command=self.login).pack(side="left", padx=2)
        ttk.Button(af, text="查看用量", command=lambda: webbrowser.open(ai_engines.ENGINES[self.engine]["usage_url"])).pack(side="left", padx=2)
        ttk.Button(af, text="安裝說明", command=self.install_help).pack(side="left", padx=2)

        ttk.Label(sf, text="語音模型").grid(row=1, column=0, sticky="w", pady=(6, 0))
        mf = ttk.Frame(sf)
        mf.grid(row=1, column=1, columnspan=2, sticky="ew", padx=6, pady=(6, 0))
        self.v_model = tk.StringVar()
        self.cb_model = ttk.Combobox(mf, textvariable=self.v_model, state="readonly", width=46)
        self.cb_model.pack(side="left")
        self.cb_model.bind("<<ComboboxSelected>>", lambda _: self.remember_model())
        ttk.Button(mf, text="選擇模型資料夾…", command=self.pick_model).pack(side="left", padx=4)
        ttk.Button(mf, text="下載模型…", command=lambda: DownloadWindow(self)).pack(side="left", padx=2)

        ttk.Label(sf, text="語言").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.v_lang = tk.StringVar(value=self.settings.get("language", "中文（繁體輸出）"))
        if self.v_lang.get() not in asr.LANGUAGES:
            self.v_lang.set("中文（繁體輸出）")
        lc = ttk.Combobox(sf, textvariable=self.v_lang, values=list(asr.LANGUAGES), state="readonly", width=30)
        lc.grid(row=2, column=1, sticky="w", padx=6, pady=(6, 0))
        lc.bind("<<ComboboxSelected>>", lambda _: self.save_pref())

        # ---- 按鈕 ----
        b = ttk.Frame(f)
        b.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(10, 6))
        self.btn_run = ttk.Button(b, text="① 開始辨識", style="Big.TButton", command=self.start_asr)
        self.btn_stop = ttk.Button(b, text="取消", command=self.stop, state="disabled")
        self.btn_fix = ttk.Button(b, text="② 校正專有名詞", style="Big.TButton", command=self.open_fix)
        self.btn_rep = ttk.Button(b, text="③ 產生會議記錄", style="Big.TButton", command=self.start_report)
        for w in (self.btn_run, self.btn_stop, self.btn_fix, self.btn_rep):
            w.pack(side="left", padx=(0, 8))
        b2 = ttk.Frame(f)
        b2.grid(row=8, column=0, columnspan=3, sticky="ew")
        ttk.Button(b2, text="重新產生 PDF（編輯 md 之後）", command=self.regen_pdf).pack(side="left", padx=(0, 8))
        ttk.Button(b2, text="開啟輸出資料夾", command=self.open_out).pack(side="left")

        self.pb = ttk.Progressbar(f, maximum=1000)
        self.pb.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(10, 2))
        self.v_prog = tk.StringVar(value="")
        ttk.Label(f, textvariable=self.v_prog).grid(row=10, column=0, columnspan=3, sticky="w")

        lf = ttk.Frame(f)
        lf.grid(row=11, column=0, columnspan=3, sticky="nsew", pady=(6, 0))
        f.rowconfigure(11, weight=1)
        self.logbox = tk.Text(lf, height=10, wrap="word", font=(FONT, 9), state="disabled")
        sb = ttk.Scrollbar(lf, command=self.logbox.yview)
        self.logbox.configure(yscrollcommand=sb.set)
        self.logbox.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.refresh_engine()
        self.refresh_models()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(150, self.poll)
        root.after(30000, self.tick_banner)
        if not self.model_path:
            root.after(600, lambda: (messagebox.showinfo("第一次使用", "這台電腦還沒有語音模型，請先下載（建議 large-v3-turbo）。"),
                                     DownloadWindow(self)))

    # ---------- 共用 ----------
    def log(self, msg: str):
        self.q.put(("log", msg))

    def poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    self.logbox.configure(state="normal")
                    self.logbox.insert("end", f"[{dt.datetime.now():%H:%M:%S}] {val}\n")
                    self.logbox.see("end")
                    self.logbox.configure(state="disabled")
                elif kind == "prog":
                    done, total, eta = val
                    self.pb["value"] = 1000 * done / max(total, 1)
                    self.v_prog.set(f"已辨識 {hms(done)} / {hms(total)}　預估剩餘 {hms(eta)}")
                elif kind == "call":
                    val()
        except queue.Empty:
            pass
        self.root.after(150, self.poll)

    def ui(self, fn):
        self.q.put(("call", fn))

    def set_busy(self, busy: bool):
        self.busy = busy
        st = "disabled" if busy else "normal"
        for w in (self.btn_run, self.btn_fix, self.btn_rep):
            w.configure(state=st)
        self.btn_stop.configure(state="normal" if busy else "disabled")

    def run_bg(self, fn, retry=None):
        """背景執行；遇到使用上限時顯示通知，retry 為「改用另一個 AI 重試」時要再呼叫的函式。"""
        def wrap():
            try:
                fn()
            except ai_engines.LimitError as e:
                self.ui(lambda: self.handle_limit(e, retry))
            except Exception as e:
                self.log("錯誤：" + str(e))
                self.log(traceback.format_exc(limit=2))
                self.ui(lambda: messagebox.showerror("錯誤", str(e)))
            finally:
                self.ui(lambda: self.set_busy(False))
        self.set_busy(True)
        threading.Thread(target=wrap, daemon=True).start()

    def save_pref(self):
        self.settings.update(engine=self.engine, language=self.v_lang.get())
        save_settings(self.settings)

    # ---------- AI ----------
    @property
    def engine(self) -> str:
        return self.v_engine.get()

    def refresh_engine(self):
        p = ai_engines.find(self.engine)
        self.v_engine_st.set("● 已安裝" if p else "● 未安裝")
        self.lb_engine.configure(foreground="#2e8b57" if p else "#c0392b")
        self.save_pref()

    def login(self):
        try:
            ai_engines.open_login(self.engine)
            self.log(f"已開啟 {self.engine} 登入視窗，請依畫面在瀏覽器完成登入。")
        except Exception as e:
            messagebox.showwarning("無法登入", str(e))

    def install_help(self):
        e = self.engine
        txt = ai_engines.ENGINES[e]["install"]
        d = tk.Toplevel(self.root)
        d.title(f"{e} 安裝說明")
        d.transient(self.root)
        ttk.Label(d, text=f"在 PowerShell 執行以下指令安裝 {e}：", padding=8).pack(anchor="w")
        t = tk.Text(d, height=6, width=70, font=("Consolas", 10))
        t.insert("1.0", txt)
        t.pack(padx=8)
        def copy():
            d.clipboard_clear()
            d.clipboard_append(txt.splitlines()[0])
            self.log("已複製安裝指令。")
        bf = ttk.Frame(d, padding=8)
        bf.pack(fill="x")
        ttk.Button(bf, text="複製第一行指令", command=copy).pack(side="left")
        ttk.Button(bf, text="安裝好了，重新偵測", command=lambda: (self.refresh_engine(), d.destroy())).pack(side="right")

    def handle_limit(self, e: ai_engines.LimitError, retry):
        self.limit = (e.engine, e.reset, e.message)
        self.show_banner()
        when = f"預計 {e.reset:%m/%d %H:%M} 恢復（{fmt_left(e.reset)}）" if e.reset else "訊息中沒有提供恢復時間，請到用量頁面查看"
        self.log(f"{e.engine} 已達使用上限：{when}。原始訊息：{e.message[:300]}")
        alt = ai_engines.other(e.engine)
        msg = f"{e.engine} 已達使用上限。\n{when}。\n\n已完成的步驟都已存檔，恢復後再按一次即可。"
        if retry and ai_engines.find(alt):
            if messagebox.askyesno("已達使用上限", msg + f"\n\n要改用 {alt} 立即重試嗎？"):
                self.v_engine.set(alt)
                self.refresh_engine()
                retry()
        else:
            messagebox.showwarning("已達使用上限", msg)

    def show_banner(self):
        if not self.limit:
            self.banner.grid_forget()
            return
        eng, reset, msg = self.limit
        if reset and reset <= dt.datetime.now():
            self.limit = None
            self.banner.grid_forget()
            self.log(f"{eng} 的使用上限時間已過，應可再使用。")
            return
        txt = f"⚠ {eng} 已達使用上限　" + (f"預計 {reset:%m/%d %H:%M} 恢復（{fmt_left(reset)}）" if reset else "恢復時間不明，請按「查看用量」")
        self.banner.configure(text=txt + "　（點此關閉）")
        self.banner.bind("<Button-1>", lambda _: (setattr(self, "limit", None), self.banner.grid_forget()))
        self.banner.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 8))

    def tick_banner(self):
        if self.limit:
            self.show_banner()
        self.root.after(30000, self.tick_banner)

    # ---------- 語音模型 ----------
    def refresh_models(self, select: str | None = None):
        self.models = dict(asr.list_models())
        custom = self.settings.get("model_custom")
        if custom and not asr.check_model(Path(custom)):
            self.models[f"自選：{custom}"] = custom
        self.cb_model["values"] = list(self.models)
        want = select or self.settings.get("model")
        pick = next((k for k, v in self.models.items() if v == want), None)
        if not pick and self.models:
            pick = next((k for k in self.models if k.startswith("large-v3-turbo")), list(self.models)[0])
        self.v_model.set(pick or "（尚未有模型，請按「下載模型」）")
        self.remember_model()

    @property
    def model_path(self) -> str | None:
        return self.models.get(self.v_model.get())

    def remember_model(self):
        if self.model_path:
            self.settings["model"] = self.model_path
            save_settings(self.settings)

    def pick_model(self):
        p = filedialog.askdirectory(title="選擇語音模型資料夾（內含 model.bin）")
        if not p:
            return
        miss = asr.check_model(Path(p))
        if miss:
            messagebox.showwarning("模型不完整", f"這個資料夾缺少：\n{'、'.join(miss)}\n\n請選擇 faster-whisper 格式的模型資料夾。")
            return
        self.settings["model_custom"] = p
        self.refresh_models(select=p)
        self.log(f"已選用模型資料夾：{p}")

    # ---------- 路徑與狀態 ----------
    def pick_audio(self):
        p = filedialog.askopenfilename(title="選擇音檔", filetypes=AUDIO_TYPES,
                                       initialdir=self.settings.get("audio_dir") or None)
        if p:
            self.v_audio.set(p)
            self.settings["audio_dir"] = str(Path(p).parent)
            if not self.v_name.get():
                self.v_name.set(Path(p).stem)
            if not self.v_out.get():
                self.v_out.set(str(Path(p).parent))

    def pick_out(self):
        p = filedialog.askdirectory(title="選擇輸出資料夾", initialdir=self.v_out.get() or None)
        if p:
            self.v_out.set(p)

    def check_paths(self, need_audio=True) -> bool:
        if need_audio and not Path(self.v_audio.get()).is_file():
            messagebox.showwarning("缺少音檔", "請先選擇音檔。")
            return False
        if not self.v_out.get():
            messagebox.showwarning("缺少輸出資料夾", "請先選擇輸出資料夾。")
            return False
        if not self.v_name.get().strip():
            self.v_name.set(Path(self.v_audio.get()).stem if self.v_audio.get() else "會議")
        Path(self.v_out.get()).mkdir(parents=True, exist_ok=True)
        self.settings["out"] = self.v_out.get()
        save_settings(self.settings)
        return True

    @property
    def name(self) -> str:
        return safe_name(self.v_name.get())

    @property
    def outdir(self) -> Path:
        return Path(self.v_out.get())

    @property
    def workdir(self) -> Path:
        return self.outdir / "_工作檔" / self.name

    def state(self) -> dict:
        try:
            return json.loads((self.workdir / "state.json").read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save_state(self, **kw):
        s = self.state()
        s.update(kw)
        self.workdir.mkdir(parents=True, exist_ok=True)
        (self.workdir / "state.json").write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")

    def open_out(self):
        if self.v_out.get() and Path(self.v_out.get()).exists():
            os.startfile(self.v_out.get())

    def stop(self):
        self.cancel.set()
        self.log("取消中…（等目前這一段辨識完就停止）")

    def on_close(self):
        if self.busy and not messagebox.askyesno("確認", "工作進行中，確定要關閉嗎？\n（辨識可下次續跑）"):
            return
        self.cancel.set()
        save_settings(self.settings)
        self.root.destroy()

    # ---------- ① 辨識 ----------
    def start_asr(self):
        if not self.check_paths():
            return
        if not self.model_path:
            messagebox.showwarning("沒有語音模型", "請先按「下載模型」或「選擇模型資料夾」。")
            return
        self.cancel.clear()
        audio, wd, mp, lang = Path(self.v_audio.get()), self.workdir, self.model_path, self.v_lang.get()
        st = self.state()
        if st.get("model") and (st.get("model") != mp or st.get("language") != lang) and (wd / "逐字稿_原始.jsonl").exists():
            if not messagebox.askyesno("設定不同", f"這場會議先前用「{Path(st['model']).name}／{st.get('language')}」辨識到一半，\n"
                                                   f"現在選的是「{Path(mp).name}／{lang}」。\n\n續跑的後半段會用新設定，要繼續嗎？"):
                return
        self.save_state(audio=str(audio), model=mp, language=lang)

        def job():
            rows = asr.transcribe(audio, wd, self.log, lambda d, t, e: self.q.put(("prog", (d, t, e))), self.cancel,
                                  model_dir=mp, language=lang)
            if not self.cancel.is_set() and rows:
                self.log("辨識完成，開啟校正畫面…")
                self.ui(self.open_fix)
        self.run_bg(job)

    # ---------- ② 校正 ----------
    def open_fix(self):
        if not self.check_paths(need_audio=False):
            return
        rows = asr.read_rows(self.workdir / "逐字稿_原始.jsonl")
        if not rows:
            messagebox.showwarning("沒有逐字稿", f"找不到「{self.name}」的辨識結果，請先按「① 開始辨識」。\n（會議名稱要跟辨識時相同）")
            return
        FixWindow(self, rows)

    # ---------- ③ 會議記錄 ----------
    def start_report(self):
        if not self.check_paths(need_audio=False):
            return
        st = self.state()
        tp = Path(st.get("transcript", ""))
        if not st.get("transcript") or not tp.exists():
            messagebox.showwarning("尚未校正", "請先完成「② 校正專有名詞」並按「套用並存檔」。")
            return
        engine = self.engine
        if not ai_engines.find(engine):
            messagebox.showerror(f"找不到 {engine}", f"這台電腦找不到 {engine}，請按「安裝說明」，或改選另一個 AI。")
            return
        name, topic = self.name, self.v_topic.get().strip()
        audio_name = Path(st.get("audio", "")).name
        pending = st.get("pending", [])
        have_min = bool(st.get("minutes_md") and Path(st["minutes_md"]).exists() and st.get("minutes_for") == str(tp))
        have_top = bool(topic and st.get("topic_md") and Path(st["topic_md"]).exists() and st.get("topic_for") == f"{tp}|{topic}")
        redo = False
        if have_min and (have_top or not topic):
            if not messagebox.askyesno("已有會議記錄", f"這份逐字稿已產生過會議記錄{'與專題' if topic else ''}。\n要用 {engine} 再產生一份新版嗎？（另存，不覆蓋舊檔）"):
                return
            redo = True
        elif have_min:
            redo = messagebox.askyesno("已有會議記錄", f"會議記錄已產生過，專題還沒有。\n\n「是」：會議記錄也重新產生一份新版\n「否」：只補產生專題")
        self.log(f"本次使用：{engine}")

        def job():
            text = tp.read_text(encoding="utf-8")
            done = {} if redo else self.state()
            if not (done.get("minutes_md") and Path(done["minutes_md"]).exists() and done.get("minutes_for") == str(tp)):
                md = report.minutes(name, audio_name, tp.name, text, pending, topic, self.log, engine)
                mdp = unique_path(self.outdir / f"{name}_會議記錄.md")
                mdp.write_text(md, encoding="utf-8")
                pdfp = pdf.md_to_pdf(mdp, unique_path(mdp.with_suffix(".pdf")))
                self.save_state(minutes_md=str(mdp), minutes_for=str(tp), minutes_engine=engine)
                self.log(f"已產生：{mdp.name}、{pdfp.name}（{engine}）")
            if topic and not (done.get("topic_md") and Path(done["topic_md"]).exists() and done.get("topic_for") == f"{tp}|{topic}"):
                md2 = report.topic_report(name, topic, text, pending, self.log, engine)
                tpm = unique_path(self.outdir / f"{name}_{safe_name(topic)}_專題整理.md")
                tpm.write_text(md2, encoding="utf-8")
                tpp = pdf.md_to_pdf(tpm, unique_path(tpm.with_suffix(".pdf")))
                self.save_state(topic_md=str(tpm), topic_for=f"{tp}|{topic}", topic_engine=engine)
                self.log(f"已產生：{tpm.name}、{tpp.name}（{engine}）")
            self.log("完成。請檢查「待確認事項」，可直接編輯 md，再按「重新產生 PDF」。")
            self.ui(lambda: messagebox.showinfo("完成", f"會議記錄已產生（{engine}）。\n無法確認的詞列在記錄檔最後的「待確認事項」，\n可直接編輯 md 後按「重新產生 PDF」。"))
        self.run_bg(job, retry=self.start_report)

    def regen_pdf(self):
        if not self.v_out.get():
            messagebox.showwarning("缺少輸出資料夾", "請先選擇輸出資料夾。")
            return
        st = self.state()
        mds = [Path(st[k]) for k in ("minutes_md", "topic_md") if st.get(k) and Path(st[k]).exists()]
        if not mds:
            picked = filedialog.askopenfilenames(title="選擇要轉成 PDF 的 md", initialdir=self.v_out.get(),
                                                 filetypes=[("Markdown", "*.md")])
            mds = [Path(p) for p in picked]
        if not mds:
            return

        def job():
            for m in mds:
                pdf.md_to_pdf(m, m.with_suffix(".pdf"))
                self.log(f"已重新產生：{m.with_suffix('.pdf').name}")
        self.run_bg(job)


class DownloadWindow:
    """下載語音模型。"""

    def __init__(self, app: App):
        self.app = app
        self.cancel = threading.Event()
        w = self.win = tk.Toplevel(app.root)
        w.title("下載語音模型")
        w.transient(app.root)
        w.resizable(False, False)
        ttk.Label(w, text="選擇要下載的模型（從 Hugging Face 下載，存到這台電腦，只需下載一次）",
                  font=(FONT, 10, "bold"), padding=(10, 10, 10, 4)).pack(anchor="w")
        ttk.Label(w, text=f"存放位置：{asr.user_models_dir()}", foreground="#666", padding=(10, 0)).pack(anchor="w")
        self.v = tk.StringVar(value="large-v3-turbo")
        have = {Path(p).name for p in app.models.values()}
        for name, (_, size, desc) in asr.DOWNLOADS.items():
            fr = ttk.Frame(w, padding=(10, 6))
            fr.pack(fill="x")
            mark = "　✓ 已下載" if name in have else ""
            ttk.Radiobutton(fr, text=f"{name}（{size}）{mark}", value=name, variable=self.v).pack(anchor="w")
            ttk.Label(fr, text=desc, foreground="#444", wraplength=520, padding=(22, 0)).pack(anchor="w")
        self.pb = ttk.Progressbar(w, maximum=1000, length=540)
        self.pb.pack(padx=10, pady=(10, 2))
        self.v_st = tk.StringVar(value="")
        ttk.Label(w, textvariable=self.v_st, padding=(10, 0)).pack(anchor="w")
        bf = ttk.Frame(w, padding=10)
        bf.pack(fill="x")
        self.btn = ttk.Button(bf, text="開始下載", command=self.start)
        self.btn.pack(side="left")
        ttk.Button(bf, text="取消／關閉", command=self.close).pack(side="right")

    def start(self):
        name = self.v.get()
        self.btn.configure(state="disabled")
        self.cancel.clear()

        def prog(got, total):
            self.app.ui(lambda: (self.pb.configure(value=1000 * got / max(total, 1)),
                                 self.v_st.set(f"{got / 1024 ** 2:,.0f} / {total / 1024 ** 2:,.0f} MB")))

        def job():
            try:
                dest = asr.download_model(name, prog, self.cancel, self.app.log)
                if not self.cancel.is_set():
                    def done():
                        self.app.refresh_models(select=str(dest))
                        messagebox.showinfo("下載完成", f"{name} 已下載完成，可以開始使用。", parent=self.win)
                        self.win.destroy()
                    self.app.ui(done)
            except Exception as e:
                self.app.log("下載失敗：" + str(e))
                self.app.ui(lambda: messagebox.showerror("下載失敗", f"{e}\n\n請確認網路連線後再試一次（會從中斷處接著下載）。", parent=self.win))
            finally:
                self.app.ui(lambda: self.btn.winfo_exists() and self.btn.configure(state="normal"))
        threading.Thread(target=job, daemon=True).start()

    def close(self):
        self.cancel.set()
        self.win.destroy()


class FixWindow:
    """專有名詞校正畫面。"""
    COLS = ("原詞", "改為", "次數", "處理", "加入對照表", "類別", "理由")
    ACTIONS = ("替換", "待確認", "不改")

    def __init__(self, app: App, raw_rows: list):
        self.app = app
        self.raw = raw_rows
        self.pairs = terms.load_glossary()
        self.rows, self.gl_counts = terms.apply(raw_rows, self.pairs)
        self.items = []

        w = self.win = tk.Toplevel(app.root)
        w.title(f"② 校正專有名詞 — {app.name}")
        w.geometry("980x640")
        w.transient(app.root)
        top = ttk.Frame(w, padding=8)
        top.pack(fill="x")
        n_gl = sum(self.gl_counts.values())
        ttk.Label(top, text=f"已自動套用共用對照表：{n_gl} 處。下表為疑似誤辨識的詞，請逐項確認。", font=(FONT, 10, "bold")).pack(side="left")
        self.btn_ai = ttk.Button(top, text="請 AI 找疑問詞", command=self.ask_ai)
        self.btn_ai.pack(side="right")
        ttk.Button(top, text="＋手動新增", command=self.add_manual).pack(side="right", padx=6)

        mid = ttk.Frame(w, padding=(8, 0))
        mid.pack(fill="both", expand=True)
        self.tv = ttk.Treeview(mid, columns=self.COLS, show="headings", selectmode="browse")
        widths = (130, 130, 50, 70, 80, 70, 380)
        for c, wd in zip(self.COLS, widths):
            self.tv.heading(c, text=c)
            self.tv.column(c, width=wd, anchor="w" if c in ("原詞", "改為", "理由") else "center")
        sb = ttk.Scrollbar(mid, command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tv.bind("<<TreeviewSelect>>", self.on_select)

        ed = ttk.LabelFrame(w, text="編輯選取的項目", padding=8)
        ed.pack(fill="x", padx=8, pady=6)
        self.v_to = tk.StringVar()
        self.v_act = tk.StringVar(value="替換")
        self.v_gl = tk.BooleanVar()
        ttk.Label(ed, text="改為").grid(row=0, column=0)
        ttk.Entry(ed, textvariable=self.v_to, width=22).grid(row=0, column=1, padx=4)
        for i, a in enumerate(self.ACTIONS):
            ttk.Radiobutton(ed, text=a, value=a, variable=self.v_act).grid(row=0, column=2 + i, padx=4)
        ttk.Checkbutton(ed, text="加入共用對照表（下次自動套用）", variable=self.v_gl).grid(row=0, column=5, padx=8)
        ttk.Button(ed, text="更新此項", command=self.update_item).grid(row=0, column=6, padx=4)
        ttk.Button(ed, text="▶ 播放原音", command=self.play).grid(row=0, column=7, padx=4)
        ttk.Button(ed, text="■ 停止", command=lambda: winsound.PlaySound(None, 0)).grid(row=0, column=8)
        self.ex = tk.Text(ed, height=4, wrap="word", font=(FONT, 9), state="disabled")
        self.ex.grid(row=1, column=0, columnspan=9, sticky="ew", pady=(6, 0))
        ed.columnconfigure(5, weight=1)

        bot = ttk.Frame(w, padding=8)
        bot.pack(fill="x")
        ttk.Label(bot, text="「待確認」的詞不替換，會列在會議記錄最後的待確認區，之後可直接編輯記錄檔。", foreground="#666").pack(side="left")
        ttk.Button(bot, text="套用並存檔", style="Big.TButton", command=self.apply_save).pack(side="right")

        if ai_engines.find(app.engine):
            self.ask_ai()
        else:
            self.app.log(f"找不到 {app.engine}：可用「＋手動新增」自行輸入要校正的詞，或改選另一個 AI 後按「請 AI 找疑問詞」。")

    # ----- 資料 -----
    def refresh(self):
        self.tv.delete(*self.tv.get_children())
        for i, it in enumerate(self.items):
            self.tv.insert("", "end", iid=str(i), values=(it["原詞"], it["建議"], it["次數"], it["處理"],
                                                          "✓" if it["加入"] else "", it.get("類別", ""), it.get("理由", "")))

    def ask_ai(self):
        engine = self.app.engine
        self.btn_ai.configure(state="disabled", text=f"{engine} 分析中…")
        self.app.log(f"本次使用：{engine}")

        def job():
            found = []
            try:
                found = terms.find_suspects(self.rows, self.app.log, engine)
            except ai_engines.LimitError as e:
                self.app.ui(lambda: self.app.handle_limit(e, retry=lambda: self.win.winfo_exists() and self.ask_ai()))
            except Exception as e:
                self.app.log("找疑問詞失敗：" + str(e))

            def done():
                if not self.win.winfo_exists():
                    return
                have = {it["原詞"] for it in self.items}
                for it in found:
                    if it["原詞"] not in have:
                        it["處理"] = "替換" if it["建議"] else "待確認"
                        it["加入"] = False
                        self.items.append(it)
                self.refresh()
                self.btn_ai.configure(state="normal", text="請 AI 再找一次")
            self.app.ui(done)
        threading.Thread(target=job, daemon=True).start()

    def add_manual(self):
        d = tk.Toplevel(self.win)
        d.title("手動新增")
        d.transient(self.win)
        a, b = tk.StringVar(), tk.StringVar()
        ttk.Label(d, text="逐字稿中的錯誤寫法").grid(row=0, column=0, padx=8, pady=6)
        ttk.Entry(d, textvariable=a).grid(row=0, column=1, padx=8)
        ttk.Label(d, text="改為").grid(row=1, column=0, padx=8, pady=6)
        ttk.Entry(d, textvariable=b).grid(row=1, column=1, padx=8)

        def ok():
            word = a.get().strip()
            if not word:
                return
            n, ex = terms.occurrences(self.rows, word)
            if n == 0:
                messagebox.showwarning("找不到", f"逐字稿中沒有「{word}」。", parent=d)
                return
            self.items.append({"原詞": word, "建議": b.get().strip(), "類別": "手動", "理由": "",
                               "次數": n, "例句": ex, "處理": "替換" if b.get().strip() else "待確認", "加入": False})
            self.refresh()
            d.destroy()
        ttk.Button(d, text="新增", command=ok).grid(row=2, column=0, columnspan=2, pady=8)

    def current(self):
        sel = self.tv.selection()
        return int(sel[0]) if sel else None

    def on_select(self, _=None):
        i = self.current()
        if i is None:
            return
        it = self.items[i]
        self.v_to.set(it["建議"])
        self.v_act.set(it["處理"])
        self.v_gl.set(it["加入"])
        self.ex.configure(state="normal")
        self.ex.delete("1.0", "end")
        for s, t in it["例句"]:
            self.ex.insert("end", f"[{hms(s)}] {t}\n")
        self.ex.configure(state="disabled")

    def update_item(self):
        i = self.current()
        if i is None:
            return
        it = self.items[i]
        it["建議"] = self.v_to.get().strip()
        it["處理"] = self.v_act.get()
        if it["處理"] == "替換" and not it["建議"]:
            messagebox.showwarning("缺少改為", "選「替換」時請填「改為」。", parent=self.win)
            return
        it["加入"] = self.v_gl.get() and it["處理"] == "替換"
        self.refresh()
        nxt = i + 1 if i + 1 < len(self.items) else i
        self.tv.selection_set(str(nxt))
        self.tv.see(str(nxt))

    def play(self):
        i = self.current()
        if i is None or not self.items[i]["例句"]:
            return
        s = self.items[i]["例句"][0][0]
        try:
            clip = asr.clip_wav(self.app.workdir, s - 2, s + 10, self.app.workdir / "_播放片段.wav")
            winsound.PlaySound(str(clip), winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception as e:
            messagebox.showerror("無法播放", str(e), parent=self.win)

    # ----- 存檔 -----
    def apply_save(self):
        reps = [(it["原詞"], it["建議"]) for it in self.items if it["處理"] == "替換" and it["建議"]]
        pending = [it["原詞"] for it in self.items if it["處理"] == "待確認"]
        rows, counts = terms.apply(self.rows, reps)
        app = self.app
        tp = unique_path(app.outdir / f"{app.name}_逐字稿.txt")
        tp.write_text(terms.to_text(rows), encoding="utf-8")
        allc = dict(self.gl_counts)
        allc.update(counts)
        terms.write_record(app.workdir / "校正紀錄.md", allc, pending)
        added = terms.add_to_glossary([(it["原詞"], it["建議"]) for it in self.items if it["加入"]])
        app.save_state(transcript=str(tp), pending=pending)
        winsound.PlaySound(None, 0)
        app.log(f"已存逐字稿：{tp.name}（本次替換 {sum(counts.values())} 處，待確認 {len(pending)} 項，對照表新增 {added} 筆）")
        self.win.destroy()
        if ai_engines.find(app.engine) and messagebox.askyesno("下一步", f"逐字稿已存檔。要接著用 {app.engine} 產生會議記錄嗎？"):
            app.start_report()


def selftest(audio: str, out: str, engine: str = "Claude Code") -> None:
    """環境檢測（不開介面）：辨識、AI、轉 PDF 各跑一次，結果寫到 <輸出資料夾>\\環境檢測.log。"""
    import sys
    import time
    outd = Path(out)
    outd.mkdir(parents=True, exist_ok=True)
    logp = outd / "環境檢測.log"
    lines = []

    def log(m):
        lines.append(f"[{time.strftime('%H:%M:%S')}] {m}")
        logp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        models = asr.list_models()
        log(f"程式位置：{Path(sys.executable).parent}")
        log(f"找到的模型：{models or '無'}")
        if not models:
            raise RuntimeError(f"沒有語音模型，請先開啟程式下載（存放位置 {asr.user_models_dir()}）")
        mp = next((p for n, p in models if n.startswith("large-v3-turbo")), models[0][1])
        rows = asr.transcribe(Path(audio), outd / "_工作檔" / "環境檢測", log, lambda *a: None, threading.Event(), model_dir=mp)
        log(f"辨識 OK：{len(rows)} 段；第一段：{rows[0]['text'] if rows else '（無）'}")
        for eng in ai_engines.ENGINES:
            p = ai_engines.find(eng)
            log(f"{eng}：{p or '未安裝'}")
            if p and (eng == engine or engine == "全部"):
                log(f"{eng} 回覆：" + ai_engines.run(eng, "請只回覆四個字：連線成功", timeout=300))
        mdp = outd / "_工作檔" / "環境檢測" / "檢測.md"
        mdp.write_text("# 環境檢測\n\n| 項目 | 結果 |\n|---|---|\n| PDF | OK |\n", encoding="utf-8")
        log(f"PDF OK：{pdf.md_to_pdf(mdp, mdp.with_suffix('.pdf'))}")
        log("全部完成")
    except Exception:
        log("失敗：\n" + traceback.format_exc())


def main():
    import sys
    if len(sys.argv) >= 4 and sys.argv[1] == "--檢測":
        selftest(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "全部")
        return
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 1.25)
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
