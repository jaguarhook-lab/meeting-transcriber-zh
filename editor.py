# -*- coding: utf-8 -*-
"""會議記錄修改視窗：不用 VS Code，對照待確認清單修改會議記錄 md（sdd: minutes-editor，2026-11-19）。

左：待確認清單（點選標示出現處、改為／全部替換／只改這處／確認無誤、聽錄音）
右：全文編輯（「（?）」黃底、上一個／下一個（?）、尋找取代、復原）
上：基本資料（寫回記錄開頭表格）
存檔前把上一版備份到 _工作檔\\<會議>\\修改紀錄\\；可存檔並產生新版 PDF，再「從我的修改學習」。
"""
import datetime as dt
import os
import shutil
import tkinter as tk
import winsound
from pathlib import Path
from tkinter import messagebox, ttk

import asr
import pdf
import pending as P
from common import hms, unique_path

FONT = "Microsoft JhengHei"


class EditorWindow:
    def __init__(self, app, c, which: str = "minutes"):
        self.app, self.c = app, c
        st = app.state(c.workdir)
        self.files = {}                                   # 顯示名 → (md 路徑, 待確認路徑, state 的 pdf 欄)
        if st.get("minutes_md") and Path(st["minutes_md"]).exists():
            pp = st.get("minutes_pending") or ""
            if not (pp and Path(pp).exists()):
                guess = Path(st["minutes_md"]).with_name(f"{c.name}_待確認.md")
                pp = str(guess) if guess.exists() else ""
            self.files["會議記錄"] = (Path(st["minutes_md"]), Path(pp) if pp else None, "minutes_pdf")
        if st.get("topic_md") and Path(st["topic_md"]).exists():
            self.files["專題整理"] = (Path(st["topic_md"]), None, "topic_pdf")
        if not self.files:
            messagebox.showwarning("沒有會議記錄", f"找不到「{c.name}」的會議記錄，請先按「③ 產生會議記錄」。\n"
                                               "（輸出資料夾與會議名稱要跟產生時相同）")
            return
        self.which = which if which in self.files else next(iter(self.files))

        w = self.win = tk.Toplevel(app.root)
        w.title(f"會議記錄修改：{c.name}")
        w.geometry("1250x800")
        w.minsize(980, 600)
        w.protocol("WM_DELETE_WINDOW", self.close)

        # ── 上：基本資料 ──
        hf = ttk.LabelFrame(w, text="基本資料（存檔時寫回記錄開頭的表格）", padding=6)
        hf.pack(fill="x", padx=8, pady=(8, 4))
        self.v_head = {}
        for i, k in enumerate(P.FIELDS):
            ttk.Label(hf, text=k).grid(row=0 if i < 4 else 1, column=(i % 4) * 2 if i < 4 else 0, sticky="w", padx=(0, 4))
            v = tk.StringVar()
            e = ttk.Entry(hf, textvariable=v, width=22 if i < 4 else 100)
            e.grid(row=0 if i < 4 else 1, column=(i % 4) * 2 + 1 if i < 4 else 1, columnspan=1 if i < 4 else 7,
                   sticky="ew", padx=(0, 12), pady=2)
            self.v_head[k] = v

        pw = ttk.PanedWindow(w, orient="horizontal")
        pw.pack(fill="both", expand=True, padx=8, pady=4)

        # ── 左：待確認清單 ──
        lf = ttk.Frame(pw, padding=(0, 0, 6, 0))
        pw.add(lf, weight=1)
        self.v_left = tk.StringVar()
        ttk.Label(lf, textvariable=self.v_left, font=(FONT, 10, "bold")).pack(anchor="w")
        tf = ttk.Frame(lf)
        tf.pack(fill="both", expand=True, pady=(4, 4))
        self.tree = ttk.Treeview(tf, columns=("n",), show="tree headings", height=14, selectmode="browse")
        self.tree.heading("#0", text="項目")
        self.tree.heading("n", text="正文")
        self.tree.column("#0", width=230)
        self.tree.column("n", width=90, anchor="center")
        sb = ttk.Scrollbar(tf, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.tag_configure("done", foreground="#2e8b57")
        self.tree.tag_configure("cat", font=(FONT, 9, "bold"))
        self.tree.bind("<<TreeviewSelect>>", lambda _: self.on_pick())

        df = ttk.Frame(lf)
        df.pack(fill="x")
        self.note = tk.Text(df, height=5, wrap="word", font=(FONT, 9), bg="#f7f7f7", relief="flat")
        self.note.pack(fill="x")
        pf = ttk.Frame(df)
        pf.pack(fill="x", pady=(4, 2))
        self.v_time = tk.StringVar()
        self.cb_time = ttk.Combobox(pf, textvariable=self.v_time, width=10, state="readonly")
        self.cb_time.pack(side="left")
        ttk.Button(pf, text="▶ 聽錄音", command=self.play).pack(side="left", padx=4)
        ttk.Button(pf, text="■ 停止", command=lambda: winsound.PlaySound(None, 0)).pack(side="left")
        rf = ttk.Frame(df)
        rf.pack(fill="x", pady=2)
        ttk.Label(rf, text="改為").pack(side="left")
        self.v_new = tk.StringVar()
        self.e_new = ttk.Entry(rf, textvariable=self.v_new)
        self.e_new.pack(side="left", fill="x", expand=True, padx=4)
        self.v_plain = tk.BooleanVar(value=False)
        self.ck_plain = ttk.Checkbutton(df, text="也改正文中沒標（?）的地方", variable=self.v_plain)
        self.ck_plain.pack(anchor="w")
        bf = ttk.Frame(df)
        bf.pack(fill="x", pady=(2, 0))
        self.btn_all = ttk.Button(bf, text="全部替換", command=self.do_all)
        self.btn_one = ttk.Button(bf, text="只改這處", command=self.do_one)
        self.btn_ok = ttk.Button(bf, text="確認無誤，拿掉（?）", command=self.do_confirm)
        for b in (self.btn_all, self.btn_one, self.btn_ok):
            b.pack(side="left", padx=(0, 4))
        bf2 = ttk.Frame(df)
        bf2.pack(fill="x", pady=(4, 0))
        ttk.Button(bf2, text="◀ 這項的上一處", command=lambda: self.jump_item(-1)).pack(side="left")
        ttk.Button(bf2, text="下一處 ▶", command=lambda: self.jump_item(1)).pack(side="left", padx=4)
        self.btn_mark = ttk.Button(bf2, text="標記已處理／取消", command=self.toggle_done)
        self.btn_mark.pack(side="right")

        # ── 右：全文 ──
        rfm = ttk.Frame(pw)
        pw.add(rfm, weight=3)
        tb = ttk.Frame(rfm)
        tb.pack(fill="x", pady=(0, 4))
        ttk.Button(tb, text="◀ 上一個（?）", command=lambda: self.jump_q(-1)).pack(side="left")
        ttk.Button(tb, text="下一個（?）▶", command=lambda: self.jump_q(1)).pack(side="left", padx=4)
        self.v_qn = tk.StringVar()
        ttk.Label(tb, textvariable=self.v_qn, foreground="#b7950b").pack(side="left", padx=8)
        ttk.Button(tb, text="記住這點…", command=self.remember).pack(side="right")
        fb = ttk.Frame(rfm)                               # 第二列：尋找／取代
        fb.pack(fill="x", pady=(0, 4))
        ttk.Label(fb, text="尋找").pack(side="left", padx=(0, 2))
        self.v_find = tk.StringVar()
        fe = ttk.Entry(fb, textvariable=self.v_find, width=18)
        fe.pack(side="left")
        fe.bind("<Return>", lambda _: self.find_next())
        ttk.Label(fb, text="取代為").pack(side="left", padx=(8, 2))
        self.v_rep = tk.StringVar()
        ttk.Entry(fb, textvariable=self.v_rep, width=18).pack(side="left")
        ttk.Button(fb, text="找下一個", command=self.find_next).pack(side="left", padx=(6, 0))
        ttk.Button(fb, text="取代", command=self.replace_one).pack(side="left", padx=2)
        ttk.Button(fb, text="全部取代", command=self.replace_every).pack(side="left")
        ttk.Label(fb, text="Ctrl+Z 復原", foreground="#888").pack(side="right")
        txf = ttk.Frame(rfm)
        txf.pack(fill="both", expand=True)
        self.txt = tk.Text(txf, wrap="word", undo=True, maxundo=-1, font=(FONT, 11), padx=8, pady=6)
        ys = ttk.Scrollbar(txf, command=self.txt.yview)
        self.txt.configure(yscrollcommand=ys.set)
        self.txt.pack(side="left", fill="both", expand=True)
        ys.pack(side="right", fill="y")
        self.txt.tag_configure("q", background="#fff59d")
        self.txt.tag_configure("item", background="#ffcc80")
        self.txt.tag_configure("cur", background="#ff9800", foreground="white")
        self.txt.tag_configure("find", background="#b3e5fc")
        self.txt.tag_raise("cur")
        self.txt.bind("<<Modified>>", self.on_modified)
        self.txt.bind("<Control-f>", lambda _: (fe.focus_set(), "break")[1])
        self.txt.bind("<Control-s>", lambda _: (self.save(), "break")[1])
        self.txt.bind("<Control-y>", lambda _: (self.redo(), "break")[1])

        # ── 下：檔案、存檔 ──
        bot = ttk.Frame(w, padding=8)
        bot.pack(fill="x")
        ttk.Label(bot, text="修改的檔案").pack(side="left")
        self.v_file = tk.StringVar(value=self.which)
        cbf = ttk.Combobox(bot, textvariable=self.v_file, values=list(self.files), state="readonly", width=10)
        cbf.pack(side="left", padx=4)
        cbf.bind("<<ComboboxSelected>>", lambda _: self.switch(self.v_file.get()))
        self.v_status = tk.StringVar()
        ttk.Label(bot, textvariable=self.v_status, foreground="#666").pack(side="left", padx=10)
        ttk.Button(bot, text="關閉", command=self.close).pack(side="right")
        ttk.Button(bot, text="存檔並產生 PDF", style="Big.TButton", command=self.save_pdf).pack(side="right", padx=6)
        ttk.Button(bot, text="存檔（Ctrl+S）", command=self.save).pack(side="right")

        self._after = None
        self.cur_item = None
        self.cur_span = -1
        self.load(self.which)

    # ── 載入／切換 ─────────────────────────────────────────────
    def remember(self):
        """把一件事直接寫進長期記憶（選取的文字會帶入）。"""
        import memory_ui
        try:
            sel = self.txt.get("sel.first", "sel.last")
        except tk.TclError:
            sel = ""
        memory_ui.remember_dialog(self.app, self.win, sel)

    def redo(self):
        try:
            self.txt.edit_redo()
        except tk.TclError:                              # 沒有可重做的
            pass

    def load(self, which):
        self.which = which
        md, pp, _k = self.files[which]
        self.md_path, self.pend_path = md, pp
        text = md.read_text(encoding="utf-8").replace("\r\n", "\n")
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", text)
        self.txt.edit_reset()
        self.txt.edit_modified(False)
        self.head0 = P.header_get(text)
        for k, v in self.v_head.items():
            v.set(self.head0.get(k, ""))
        self.items = P.parse(pp.read_text(encoding="utf-8")) if pp and pp.exists() else []
        st = self.app.state(self.c.workdir)
        self.done = set(st.get("edit_done", {}).get(str(md), []))
        self.fill_tree()
        self.refresh_marks()
        self.v_status.set(f"{md.name}")
        self.win.title(f"會議記錄修改：{self.c.name}（{which}）")

    def switch(self, which):
        if which == self.which:
            return
        if self.dirty() and not self.ask_save():
            self.v_file.set(self.which)
            return
        self.load(which)

    def text(self) -> str:
        return self.txt.get("1.0", "end-1c")

    def idx(self, off: int) -> str:
        return f"1.0+{off}c"

    # ── 左側清單 ───────────────────────────────────────────────
    def fill_tree(self):
        self.tree.delete(*self.tree.get_children())
        if not self.items:
            self.v_left.set("待確認清單：（這份沒有待確認清單）")
            return
        cats = {}
        for i, it in enumerate(self.items):
            if it["cat"] not in cats:
                cats[it["cat"]] = self.tree.insert("", "end", text=it["cat"], open=True, tags=("cat",))
            self.tree.insert(cats[it["cat"]], "end", iid=str(i), text=it["label"])
        self.update_tree()

    def update_tree(self):
        text = self.text()
        for i, it in enumerate(self.items):
            if it["kind"] == "term":
                m, p = P.counts(text, it)
                n = f"（?）{m}" + (f"／未標 {p}" if p else "") if (m or p) else "未出現"
            elif it["kind"] == "time":
                n = "時間點"
            else:
                n = "說明"
            done = it["label"] in self.done
            self.tree.item(str(i), text=("✓ " if done else "● ") + it["label"], values=(n,), tags=("done",) if done else ())
        left = sum(1 for it in self.items if it["label"] not in self.done)
        self.v_left.set(f"待確認（剩 {left}／{len(self.items)} 項）")

    def on_pick(self):
        sel = self.tree.selection()
        if not sel or not sel[0].isdigit():
            return
        it = self.cur_item = self.items[int(sel[0])]
        self.note.configure(state="normal")
        self.note.delete("1.0", "end")
        self.note.insert("1.0", f"{it['label']}\n{it['note']}")
        self.note.configure(state="disabled")
        ts = [hms(t) for t in it["times"]]
        self.cb_time.configure(values=ts)
        self.v_time.set(ts[0] if ts else "")
        term = it["kind"] == "term"
        self.v_new.set(it["alts"][0] if term and it["alts"] else "")
        for b in (self.btn_all, self.btn_one, self.btn_ok, self.e_new, self.ck_plain):
            b.configure(state="normal" if term else "disabled")
        self.cur_span = -1
        self.refresh_marks()
        self.jump_item(1)

    def item_spans(self):
        return P.spans(self.text(), self.cur_item) if self.cur_item else []

    def jump_item(self, step):
        sp = self.item_spans()
        if not sp:
            if self.cur_item and self.cur_item["kind"] == "term":
                self.v_status.set("正文中沒有出現這一項（可能 AI 沒有寫入正文），可直接標記已處理。")
            return
        self.cur_span = (self.cur_span + step) % len(sp)
        s, e, _m = sp[self.cur_span]
        self.txt.tag_remove("cur", "1.0", "end")
        self.txt.tag_add("cur", self.idx(s), self.idx(e))
        self.txt.see(self.idx(s))
        self.txt.mark_set("insert", self.idx(s))
        self.v_status.set(f"第 {self.cur_span + 1}／{len(sp)} 處")

    # ── 修改動作 ───────────────────────────────────────────────
    def _apply(self, edits):
        """edits：[(start, end, 新文字)]，由後往前改，算一次復原（關掉自動分段，刪＋插才會一起復原）。"""
        self.txt.configure(autoseparators=False)
        self.txt.edit_separator()
        for s, e, new in sorted(edits, reverse=True):
            self.txt.delete(self.idx(s), self.idx(e))
            self.txt.insert(self.idx(s), new)
        self.txt.edit_separator()
        self.txt.configure(autoseparators=True)
        self.after_edit()

    def do_all(self):
        it, new = self.cur_item, self.v_new.get().strip()
        if not it or not new:
            messagebox.showinfo("請填寫", "請在「改為」填入正確的寫法。", parent=self.win)
            return
        sp = [x for x in self.item_spans() if x[2] or self.v_plain.get()]
        if not sp:
            messagebox.showinfo("沒有可替換的地方", "正文中沒有標（?）的這個詞。要連沒標的一起改，請勾「也改正文中沒標（?）的地方」。",
                                parent=self.win)
            return
        self._apply([(s, e, new) for s, e, _m in sp])
        self.mark_done(it)
        self.v_status.set(f"已替換 {len(sp)} 處：{it['label']} → {new}")

    def do_one(self):
        it, new = self.cur_item, self.v_new.get().strip()
        sp = self.item_spans()
        if not it or not new or not sp:
            return
        k = self.cur_span if 0 <= self.cur_span < len(sp) else 0
        s, e, _m = sp[k]
        self._apply([(s, e, new)])
        if not any(m for *_x, m in self.item_spans()):
            self.mark_done(it)
        self.cur_span -= 1
        self.jump_item(1)

    def do_confirm(self):
        it = self.cur_item
        if not it:
            return
        text = self.text()
        sp = [x for x in self.item_spans() if x[2]]
        self._apply([(s, e, text[s:e].replace(P.Q, "")) for s, e, _m in sp])
        self.mark_done(it)
        self.v_status.set(f"已確認「{it['label']}」，拿掉 {len(sp)} 處（?）")

    def mark_done(self, it, on=True):
        (self.done.add if on else self.done.discard)(it["label"])
        st = self.app.state(self.c.workdir)
        ed = st.get("edit_done", {})
        ed[str(self.md_path)] = sorted(self.done)
        self.app.save_state(self.c.workdir, edit_done=ed)
        self.update_tree()

    def toggle_done(self):
        if self.cur_item:
            self.mark_done(self.cur_item, self.cur_item["label"] not in self.done)

    # ── 右側：標示、跳轉、尋找取代 ─────────────────────────────
    def on_modified(self, _e=None):
        if self.txt.edit_modified():
            if self._after:
                self.win.after_cancel(self._after)
            self._after = self.win.after(400, self.after_edit)

    def after_edit(self):
        self._after = None
        self.refresh_marks()
        self.update_tree()

    def refresh_marks(self):
        text = self.text()
        for t in ("q", "item", "cur"):
            self.txt.tag_remove(t, "1.0", "end")
        i, n = text.find(P.Q), 0
        while i >= 0:
            self.txt.tag_add("q", self.idx(i), self.idx(i + len(P.Q)))
            n += 1
            i = text.find(P.Q, i + 1)
        self.v_qn.set(f"正文還有 {n} 處（?）")
        for s, e, _m in self.item_spans():
            self.txt.tag_add("item", self.idx(s), self.idx(e))

    def jump_q(self, step):
        text = self.text()
        here = len(self.txt.get("1.0", "insert"))
        pos = [i for i in range(len(text)) if text.startswith(P.Q, i)]
        if not pos:
            self.v_status.set("正文已經沒有（?）")
            return
        nxt = next((p for p in pos if p > here), pos[0]) if step > 0 else next((p for p in reversed(pos) if p < here - 1), pos[-1])
        ls = text.rfind("\n", 0, nxt) + 1                 # 選到這一行的開頭，方便看前後文
        self.txt.tag_remove("cur", "1.0", "end")
        self.txt.tag_add("cur", self.idx(nxt), self.idx(nxt + len(P.Q)))
        self.txt.mark_set("insert", self.idx(nxt + len(P.Q)))
        self.txt.see(self.idx(ls))
        self.txt.see(self.idx(nxt))

    def find_next(self):
        s = self.v_find.get()
        if not s:
            return
        pos = self.txt.search(s, "insert+1c", stopindex="end") or self.txt.search(s, "1.0", stopindex="end")
        self.txt.tag_remove("find", "1.0", "end")
        if not pos:
            self.v_status.set(f"找不到「{s}」")
            return
        end = f"{pos}+{len(s)}c"
        self.txt.tag_add("find", pos, end)
        self.txt.mark_set("insert", pos)
        self.txt.see(pos)

    def replace_one(self):
        s = self.v_find.get()
        r = self.txt.tag_ranges("find")
        if s and r and self.txt.get(r[0], r[1]) == s:
            off = len(self.txt.get("1.0", r[0]))
            self._apply([(off, off + len(s), self.v_rep.get())])
        self.find_next()

    def replace_every(self):
        s, rep = self.v_find.get(), self.v_rep.get()
        if not s:
            return
        text = self.text()
        n = text.count(s)
        if not n:
            self.v_status.set(f"找不到「{s}」")
            return
        if not messagebox.askyesno("全部取代", f"把 {n} 處「{s}」全部改成「{rep}」？（可按 Ctrl+Z 復原）", parent=self.win):
            return
        i, edits = text.find(s), []
        while i >= 0:
            edits.append((i, i + len(s), rep))
            i = text.find(s, i + len(s))
        self._apply(edits)
        self.v_status.set(f"已取代 {n} 處")

    # ── 聽錄音 ─────────────────────────────────────────────────
    def play(self):
        t = self.v_time.get()
        if not t:
            return
        h, m, s = (int(x) for x in t.split(":"))
        sec = h * 3600 + m * 60 + s
        if not (self.c.workdir / "audio_16k.wav").exists():
            messagebox.showinfo("沒有錄音", "工作檔裡沒有轉好的錄音。\n請在主畫面選好音檔後按「① 開始辨識」：已辨識完成的會議不會重跑，"
                                         "只會準備好播放用的錄音。", parent=self.win)
            return
        try:
            clip = asr.clip_wav(self.c.workdir, sec - 3, sec + 15, self.c.workdir / "_播放片段.wav")
            winsound.PlaySound(str(clip), winsound.SND_FILENAME | winsound.SND_ASYNC)
            self.v_status.set(f"播放 {t} 前後（約 18 秒）")
        except Exception as e:
            messagebox.showerror("無法播放", str(e), parent=self.win)

    # ── 存檔 ───────────────────────────────────────────────────
    def dirty(self) -> bool:
        return self.txt.edit_modified() or any(self.v_head[k].get() != self.head0.get(k, "") for k in self.v_head)

    def save(self) -> bool:
        changed = {k: v.get() for k, v in self.v_head.items() if v.get() != self.head0.get(k, "") and k in self.head0}
        if changed:                                      # 只改表頭那幾行（可復原），不整篇重貼
            old = self.text()
            new_lines, old_lines = P.header_set(old, changed).split("\n"), old.split("\n")
            edits, off = [], 0
            for a, b in zip(old_lines, new_lines):
                if a != b:
                    edits.append((off, off + len(a), b))
                off += len(a) + 1
            self._apply(edits)
        text = self.text()
        md = self.md_path
        try:
            if md.exists():                              # 先備份上一版，改錯找得回來
                bk = self.c.workdir / "修改紀錄"
                bk.mkdir(parents=True, exist_ok=True)
                shutil.copy2(md, bk / f"{md.stem}_{dt.datetime.now():%Y%m%d_%H%M%S}.md")
            md.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
        except OSError as e:
            messagebox.showerror("存檔失敗", f"{e}\n\n檔案可能被其他程式（例如 Word、記事本）開著，請關掉後再試。", parent=self.win)
            return False
        self.head0 = P.header_get(text)
        self.txt.edit_modified(False)
        self.v_status.set(f"已存檔 {dt.datetime.now():%H:%M:%S}：{md.name}（上一版備份在 _工作檔\\{self.c.name}\\修改紀錄）")
        self.app.log(f"已存檔修改：{md.name}")
        return True

    def save_pdf(self):
        if not self.save():
            return
        md = self.md_path
        self.win.configure(cursor="watch")
        self.win.update()
        try:
            dst = pdf.md_to_pdf(md, unique_path(md.with_suffix(".pdf")))
        except Exception as e:
            import traceback
            self.app.show_error(f"{e}\n\n{traceback.format_exc()}", "轉 PDF", parent=self.win)
            return
        finally:
            self.win.configure(cursor="")
        self.app.save_state(self.c.workdir, **{self.files[self.which][2]: str(dst)})
        self.app.log(f"已產生新版 PDF：{dst.name}（舊版保留）")
        open_it = messagebox.askyesno("PDF 已產生", f"已產生新版 PDF：\n{dst.name}\n（舊版 PDF 保留不動）\n\n要現在開啟看看嗎？", parent=self.win)
        if open_it:
            os.startfile(str(dst))
        if self.which == "會議記錄" and self.app.workdir == self.c.workdir and messagebox.askyesno(
                "從我的修改學習", "要把這次改的詞記下來嗎？\n下次同樣的錯字會自動改好（會先列出來給你勾選）。", parent=self.win):
            self.app.open_learn()
        if self.which == "會議記錄" and messagebox.askyesno(
                "讓 AI 記住你的習慣", "要讓 AI 根據這次的修改，提議以後要記住的事（寫作偏好、背景、常見錯誤）嗎？\n"
                                       "約需 1～3 分鐘；每一條都由你決定要不要記。", parent=self.win):
            done = "、".join(sorted(self.done)) or "（沒有標記）"
            self.app.memory_propose(self.c, self.md_path, f"已處理的待確認項目：{done}")

    def ask_save(self) -> bool:
        """有未存檔修改時詢問。回 False＝使用者取消。"""
        ans = messagebox.askyesnocancel("尚未存檔", "有修改還沒存檔，要先存檔嗎？", parent=self.win)
        if ans is None:
            return False
        return self.save() if ans else True

    def close(self):
        if self.dirty() and not self.ask_save():
            return
        winsound.PlaySound(None, 0)
        self.win.destroy()
