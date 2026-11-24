# -*- coding: utf-8 -*-
"""「AI 記憶與提示詞」視窗與「送出前檢視」對話框（sdd: prompt-editor，2026-11-24）。

分頁：提示詞範本（原廠預設／我的預設，欄位上色、檢查、還原、和原廠比較）、情境說明、已知名詞。
"""
import datetime as dt
import difflib
import re
import shutil
import tkinter as tk
from tkinter import messagebox, ttk

import prompts
from common import CONTEXT, KNOWN

FONT = "Microsoft JhengHei"
F_EDIT = ("Microsoft JhengHei", 10)


def _mark_fields(txt: tk.Text, name: str):
    """欄位上色：可用欄位藍底、本範本沒有的欄位紅底。"""
    for t in ("field", "badfield"):
        txt.tag_remove(t, "1.0", "end")
    s = txt.get("1.0", "end-1c")
    for m in re.finditer(r"\{([^{}\s\"]{1,12})\}", s):
        txt.tag_add("field" if m.group(1) in prompts.FIELDS[name] else "badfield", f"1.0+{m.start()}c", f"1.0+{m.end()}c")


def _editor(parent, height=24) -> tk.Text:
    f = ttk.Frame(parent)
    f.pack(fill="both", expand=True)
    t = tk.Text(f, wrap="word", undo=True, font=F_EDIT, height=height, padx=6, pady=4)
    sb = ttk.Scrollbar(f, command=t.yview)
    t.configure(yscrollcommand=sb.set)
    t.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    t.tag_configure("field", background="#d6eaf8", foreground="#1a5276")
    t.tag_configure("badfield", background="#f5b7b1")
    return t


def _backup_file(p):
    if p.exists():
        bk = prompts.user_dir() / "備份"
        bk.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, bk / f"{p.stem}_{dt.datetime.now():%Y%m%d_%H%M%S}{p.suffix}")


class MemoryWindow:
    """AI 記憶與提示詞。"""

    def __init__(self, app):
        self.app = app
        w = self.win = tk.Toplevel(app.root)
        w.title("AI 記憶與提示詞")
        w.geometry("1150x780")
        w.protocol("WM_DELETE_WINDOW", self.close)
        ttk.Label(w, text="這裡的內容會送給 AI（Claude Code／Codex）。請不要寫入不想交給 AI 服務的個人資料。",
                  foreground="#666", padding=(10, 6, 10, 0)).pack(anchor="w")
        nb = self.nb = ttk.Notebook(w)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self._tab_memory(nb)
        self._tab_templates(nb)
        self.files = {}
        self._tab_file(nb, "情境說明", CONTEXT, "第一行：一句話說明是什麼會議（也用在語音辨識）；第二行以後：公司、人物、單位之間的關係等背景，給寫記錄的 AI 參考。# 開頭是註解。")
        self._tab_file(nb, "已知名詞", KNOWN, "每行一個寫法正確的名詞，可加說明與常見誤寫（格式見檔案開頭的註解）。「從我的修改學習」也會自動加進這裡。")

    # ── 長期記憶 ──────────────────────────────────────────────
    def _tab_memory(self, nb):
        import memory
        f = ttk.Frame(nb, padding=6)
        nb.add(f, text="長期記憶")
        ttk.Label(f, text="AI 會記住這裡寫的事，每次寫記錄都遵守。分四節：關於我們／寫作偏好／常見修正／不要做的事，每條一行、以「- 」開頭。"
                          "修改畫面「存檔並產生 PDF」後，AI 會依你的修改提議新增或修改（你核可才寫入）。",
                  foreground="#555", wraplength=1080).pack(anchor="w", pady=(0, 4))
        self.v_mem = tk.StringVar()
        ttk.Label(f, textvariable=self.v_mem, foreground="#1a5276").pack(anchor="w")
        self.t_mem = _editor(f, 24)
        self.t_mem.insert("1.0", memory.load_text())
        self.t_mem.edit_reset()
        self.t_mem.edit_modified(False)
        self.t_mem.bind("<KeyRelease>", lambda _e: self._mem_info())
        bf = ttk.Frame(f)
        bf.pack(fill="x", pady=(6, 0))
        ttk.Button(bf, text="存檔", command=self.save_mem).pack(side="left")
        ttk.Button(bf, text="請 AI 整理記憶", command=lambda: self.app.memory_consolidate(self)).pack(side="left", padx=6)
        ttk.Button(bf, text="變更紀錄", command=lambda: self._open(memory.base_dir() / "記憶變更紀錄.md")).pack(side="left")
        ttk.Button(bf, text="備份資料夾", command=lambda: self._open(memory.base_dir() / "記憶備份")).pack(side="left", padx=6)
        self.files_mem = self.t_mem
        self._mem_info()

    def _mem_info(self):
        import memory
        txt = self.t_mem.get("1.0", "end-1c")
        n, s = memory.items_count(txt), len(memory.prompt_text(txt))
        warn = f"　⚠ 超過建議上限 {memory.LIMIT:,} 字，建議按「請 AI 整理記憶」" if s > memory.LIMIT else ""
        self.v_mem.set(f"目前 {n} 條，送給 AI 約 {s:,} 字（上限 {memory.LIMIT:,}）{warn}")

    @staticmethod
    def _open(p):
        import os
        if p.exists():
            os.startfile(str(p))
        else:
            messagebox.showinfo("還沒有", f"還沒有 {p.name}。")

    def save_mem(self):
        import memory
        try:
            memory.save_text(self.t_mem.get("1.0", "end-1c"), "手動修改（長期記憶分頁）")
        except OSError as e:
            messagebox.showerror("存檔失敗", str(e), parent=self.win)
            return
        self.t_mem.edit_modified(False)
        self._mem_info()
        self.app.log("已存檔長期記憶（舊版備份在 記憶備份\\）")

    def reload_mem(self):
        import memory
        self.t_mem.delete("1.0", "end")
        self.t_mem.insert("1.0", memory.load_text())
        self.t_mem.edit_modified(False)
        self._mem_info()

    # ── 提示詞範本 ────────────────────────────────────────────
    def _tab_templates(self, nb):
        f = ttk.Frame(nb, padding=6)
        nb.add(f, text="提示詞範本")
        left = ttk.Frame(f)
        left.pack(side="left", fill="y")
        ttk.Label(left, text="範本", font=(FONT, 10, "bold")).pack(anchor="w")
        self.lb = tk.Listbox(left, width=24, height=8, font=F_EDIT, exportselection=False)
        self.lb.pack(fill="y")
        self.lb.bind("<<ListboxSelect>>", lambda _: self.pick())
        ttk.Label(left, text="\n三層：\n原廠預設（程式內建）\n→ 我的預設（存在 提示詞\\）\n→ 本次送出（按 ③ 前可再改）",
                  foreground="#666", justify="left").pack(anchor="w", pady=8)
        right = ttk.Frame(f)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self.v_src = tk.StringVar()
        ttk.Label(right, textvariable=self.v_src, font=(FONT, 10, "bold")).pack(anchor="w")
        self.v_notice = tk.StringVar()
        ttk.Label(right, textvariable=self.v_notice, foreground="#b9770e", wraplength=800).pack(anchor="w")
        self.t_tpl = _editor(right, 22)
        self.t_tpl.bind("<<Modified>>", self._tpl_modified)
        ttk.Label(right, text="可用欄位（送出時自動填入；★ 不能刪；逐字稿本文一律接在最後）：", foreground="#555").pack(anchor="w", pady=(6, 0))
        self.t_fields = tk.Text(right, height=5, font=(FONT, 9), bg="#f7f7f7", relief="flat", wrap="word")
        self.t_fields.pack(fill="x")
        bf = ttk.Frame(right)
        bf.pack(fill="x", pady=(6, 0))
        ttk.Button(bf, text="存成我的預設", command=self.save_tpl).pack(side="left")
        ttk.Button(bf, text="和原廠比較", command=self.compare).pack(side="left", padx=6)
        ttk.Button(bf, text="還原原廠預設", command=self.reset_tpl).pack(side="left")
        ttk.Button(bf, text="放棄這次修改", command=self.pick).pack(side="left", padx=6)
        self.refresh_list()
        self.lb.selection_set(0)
        self.cur = None
        self.pick()

    def refresh_list(self):
        sel = self.lb.curselection()
        self.lb.delete(0, "end")
        for n in prompts.NAMES:
            src = prompts.load(n)[1]
            mark = "⚠" if prompts.factory_updated(n) else ("✎" if src == "我的預設" else "")
            self.lb.insert("end", f"{n}　{mark}{'（我的預設）' if src == '我的預設' else ''}")
        if sel:
            self.lb.selection_set(sel[0])

    def _tpl_modified(self, _e=None):
        if self.t_tpl.edit_modified() and self.cur:
            _mark_fields(self.t_tpl, self.cur)

    def pick(self):
        sel = self.lb.curselection()
        if not sel:
            return
        name = prompts.NAMES[sel[0]]
        if self.cur and self.cur != name and self.t_tpl.edit_modified():
            if not messagebox.askyesno("尚未存檔", f"「{self.cur}」的修改還沒存，要放棄嗎？", parent=self.win):
                self.lb.selection_clear(0, "end")
                self.lb.selection_set(prompts.NAMES.index(self.cur))
                return
        self.cur = name
        text, src = prompts.load(name)
        self.t_tpl.delete("1.0", "end")
        self.t_tpl.insert("1.0", text)
        self.t_tpl.edit_reset()
        self.t_tpl.edit_modified(False)
        _mark_fields(self.t_tpl, name)
        self.v_src.set(f"{name}：目前使用「{src}」")
        self.v_notice.set("⚠ 新版程式的原廠預設有更新：按「和原廠比較」看差異，可手動合併後存檔，或「還原原廠預設」。"
                          if prompts.factory_updated(name) else "")
        self.t_fields.configure(state="normal")
        self.t_fields.delete("1.0", "end")
        fs = prompts.FIELDS[name]
        self.t_fields.insert("1.0", "\n".join(f"{{{k}}}　{v}" for k, v in fs.items()) if fs else "（這個範本沒有欄位，內容會整段放進會議記錄與專題整理的 {寫作規則}）")
        self.t_fields.configure(state="disabled")

    def save_tpl(self):
        name, text = self.cur, self.t_tpl.get("1.0", "end-1c")
        probs = prompts.check(name, text)
        hard = [p for p in probs if p.startswith("不能")]
        if hard:
            messagebox.showwarning("不能存", "\n".join(hard), parent=self.win)
            return
        if probs and not messagebox.askyesno("確認", "\n".join(probs) + "\n\n仍要存檔嗎？", parent=self.win):
            return
        p = prompts.save_user(name, text)
        self.t_tpl.edit_modified(False)
        self.refresh_list()
        self.pick()
        self.app.log(f"已存成我的預設：{p}（舊版備份在 提示詞\\備份）")

    def reset_tpl(self):
        name = self.cur
        if prompts.load(name)[1] != "我的預設":
            messagebox.showinfo("已是原廠預設", f"「{name}」目前就是原廠預設。", parent=self.win)
            return
        if not messagebox.askyesno("還原原廠預設", f"把「{name}」換回原廠預設？\n目前的我的預設會移到 提示詞\\備份\\，不會刪除。", parent=self.win):
            return
        dst = prompts.reset(name)
        self.t_tpl.edit_modified(False)
        self.refresh_list()
        self.pick()
        self.app.log(f"已還原原廠預設：{name}（原本的我的預設在 {dst}）")

    def compare(self):
        compare_window(self.win, f"{self.cur}：原廠預設 vs 目前編輯中", prompts.FACTORY[self.cur],
                       self.t_tpl.get("1.0", "end-1c"), "原廠預設", "目前編輯中")

    # ── 情境說明、已知名詞 ────────────────────────────────────
    def _tab_file(self, nb, label, path, hint):
        f = ttk.Frame(nb, padding=6)
        nb.add(f, text=label)
        ttk.Label(f, text=hint, foreground="#555", wraplength=1000).pack(anchor="w", pady=(0, 4))
        t = _editor(f, 26)
        try:
            t.insert("1.0", path.read_text(encoding="utf-8") if path.exists() else "")
        except OSError:
            pass
        t.edit_reset()
        t.edit_modified(False)
        bf = ttk.Frame(f)
        bf.pack(fill="x", pady=(6, 0))
        ttk.Button(bf, text="存檔", command=lambda: self.save_file(label)).pack(side="left")
        ttk.Label(bf, text=f"檔案：{path}", foreground="#888").pack(side="left", padx=10)
        self.files[label] = (path, t)

    def save_file(self, label):
        path, t = self.files[label]
        try:
            _backup_file(path)
            path.write_text(t.get("1.0", "end-1c").rstrip("\n") + "\n", encoding="utf-8")
        except OSError as e:
            messagebox.showerror("存檔失敗", str(e), parent=self.win)
            return
        t.edit_modified(False)
        self.app.log(f"已存檔：{path.name}（舊版備份在 提示詞\\備份）")

    def close(self):
        dirty = [self.cur] if self.t_tpl.edit_modified() else []
        dirty += ["長期記憶"] if self.t_mem.edit_modified() else []
        dirty += [k for k, (_p, t) in self.files.items() if t.edit_modified()]
        if dirty and not messagebox.askyesno("尚未存檔", "這些還沒存：" + "、".join(dirty) + "\n要放棄修改並關閉嗎？", parent=self.win):
            return
        self.win.destroy()


def compare_window(parent, title, a: str, b: str, la: str, lb: str, accept=None, accept_text="採用右邊的版本"):
    """並排比較：左邊刪掉或改掉的行紅底，右邊新增或改過的行綠底。accept：按「採用」時呼叫（給整理記憶用）。"""
    w = tk.Toplevel(parent)
    if accept:
        bf = ttk.Frame(w, padding=(6, 6, 6, 0))
        bf.pack(side="bottom", fill="x")
        ttk.Button(bf, text=accept_text, style="Big.TButton", command=lambda: (accept(), w.destroy())).pack(side="right")
        ttk.Button(bf, text="不要", command=w.destroy).pack(side="right", padx=6)
    w.title(title)
    w.geometry("1200x700")
    pw = ttk.PanedWindow(w, orient="horizontal")
    pw.pack(fill="both", expand=True, padx=6, pady=6)
    al, bl = a.split("\n"), b.split("\n")
    texts = []
    for lab in (la, lb):
        f = ttk.Frame(pw)
        pw.add(f, weight=1)
        ttk.Label(f, text=lab, font=(FONT, 10, "bold")).pack(anchor="w")
        t = tk.Text(f, wrap="word", font=F_EDIT)
        t.pack(fill="both", expand=True)
        t.tag_configure("del", background="#fadbd8")
        t.tag_configure("add", background="#d5f5e3")
        texts.append(t)
    ta, tb = texts
    ta.insert("1.0", a)
    tb.insert("1.0", b)
    n, first = 0, None
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, al, bl, autojunk=False).get_opcodes():
        if op != "equal":
            n += 1
            first = first or (i1 + 1, j1 + 1)
            if i2 > i1:
                ta.tag_add("del", f"{i1 + 1}.0", f"{i2}.end+1c")
            if j2 > j1:
                tb.tag_add("add", f"{j1 + 1}.0", f"{j2}.end+1c")
    for t in texts:
        t.configure(state="disabled")
    if first:                                            # 捲到第一處不同
        w.after(100, lambda: (ta.see(f"{first[0]}.0"), tb.see(f"{first[1]}.0")))
    ttk.Label(w, text=f"共 {n} 處不同" if n else "內容完全相同", padding=6).pack(anchor="w")


class ProposalWindow:
    """AI 提議的記憶更新與範本修改建議：逐條勾選、可改文字，按「寫入勾選的項目」才套用。"""

    def __init__(self, app, prop: dict, source: str):
        import memory
        self.app, self.source = app, source
        self.mem = [dict(x, on=True) for x in prop.get("memory", [])]
        self.tpl = [dict(x, on=False) for x in prop.get("template", [])]      # 預設只動記憶
        w = self.win = tk.Toplevel(app.root)
        w.title("建議記住的事")
        w.geometry("1100x640")
        ttk.Label(w, text=f"AI 依你對「{source}」的修改，提議以下更新。勾選要採用的，雙擊可修改文字；按「寫入勾選的項目」才會套用（寫入前自動備份）。",
                  wraplength=1060, padding=(10, 8)).pack(anchor="w")
        ttk.Label(w, text="記憶（預設勾選）", font=(FONT, 10, "bold"), padding=(10, 0)).pack(anchor="w")
        self.tv = self._tree(w, ("on", "op", "section", "text", "reason"), ("採用", "動作", "分節", "內容", "理由"),
                             (50, 60, 90, 450, 420), 9)
        ttk.Label(w, text="提示詞範本修改建議（預設不勾；採用後存成「我的預設」，可在 AI 記憶與提示詞視窗還原）",
                  font=(FONT, 10, "bold"), padding=(10, 6, 10, 0)).pack(anchor="w")
        self.tv2 = self._tree(w, ("on", "name", "find", "replace", "reason"), ("採用", "範本", "原文", "改成", "理由"),
                              (50, 90, 300, 300, 330), 5)
        bf = ttk.Frame(w, padding=10)
        bf.pack(fill="x")
        ttk.Button(bf, text="寫入勾選的項目", style="Big.TButton", command=self.apply).pack(side="right")
        ttk.Button(bf, text="全部不要", command=w.destroy).pack(side="right", padx=6)
        self.v_info = tk.StringVar()
        ttk.Label(bf, textvariable=self.v_info, foreground="#555").pack(side="left")
        if not self.mem and not self.tpl:
            self.v_info.set("這次的修改沒有找到需要記住的通則。")
        self.fill()
        self.tv.bind("<Double-1>", lambda e: self.edit(self.tv, self.mem, e))
        self.tv2.bind("<Double-1>", lambda e: self.edit(self.tv2, self.tpl, e))
        self.tv.bind("<space>", lambda _e: self.toggle(self.tv, self.mem))
        self.tv2.bind("<space>", lambda _e: self.toggle(self.tv2, self.tpl))
        self.tv.bind("<Button-1>", lambda e: self.click(self.tv, self.mem, e))
        self.tv2.bind("<Button-1>", lambda e: self.click(self.tv2, self.tpl, e))

    def _tree(self, w, cols, heads, widths, h):
        f = ttk.Frame(w)
        f.pack(fill="both", expand=True, padx=10)
        tv = ttk.Treeview(f, columns=cols, show="headings", height=h)
        for c, hd, wd in zip(cols, heads, widths):
            tv.heading(c, text=hd)
            tv.column(c, width=wd, anchor="center" if c == "on" else "w")
        sb = ttk.Scrollbar(f, command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        return tv

    def fill(self):
        self.tv.delete(*self.tv.get_children())
        for i, x in enumerate(self.mem):
            txt = x["text"] if x["op"] != "刪除" else f"（刪除）{x['old']}"
            if x["op"] == "修改":
                txt = f"{x['old']} → {x['text']}"
            self.tv.insert("", "end", iid=str(i), values=("☑" if x["on"] else "☐", x["op"], x["section"], txt, x["reason"]))
        self.tv2.delete(*self.tv2.get_children())
        for i, x in enumerate(self.tpl):
            self.tv2.insert("", "end", iid=str(i), values=("☑" if x["on"] else "☐", x["name"], x["find"], x["replace"], x["reason"]))

    def click(self, tv, lst, e):
        if tv.identify_column(e.x) == "#1" and tv.identify_row(e.y):
            i = int(tv.identify_row(e.y))
            lst[i]["on"] = not lst[i]["on"]
            self.fill()
            return "break"

    def toggle(self, tv, lst):
        for s in tv.selection():
            lst[int(s)]["on"] = not lst[int(s)]["on"]
        self.fill()

    def edit(self, tv, lst, e):
        from tkinter import simpledialog
        row = tv.identify_row(e.y)
        if not row:
            return
        x = lst[int(row)]
        key = "text" if tv is self.tv else "replace"
        if tv is self.tv and x["op"] == "刪除":
            return
        new = simpledialog.askstring("修改", "改成：", initialvalue=x[key], parent=self.win)
        if new is not None and new.strip():
            x[key] = new.strip()
            x["on"] = True
            self.fill()

    def apply(self):
        import memory
        import prompts
        n = memory.apply([x for x in self.mem if x["on"]], f"從 {self.source} 的修改學到")
        t_ok, t_bad = 0, []
        for x in (y for y in self.tpl if y["on"]):
            cur = prompts.load(x["name"])[0] if x["name"] in prompts.NAMES else None
            if cur is None or x["find"] not in cur:
                t_bad.append(f"{x['name']}：找不到要改的原文")
                continue
            new = cur.replace(x["find"], x["replace"], 1)
            hard = [p for p in prompts.check(x["name"], new) if p.startswith("不能")]
            if hard:
                t_bad.append(f"{x['name']}：{hard[0]}")
                continue
            prompts.save_user(x["name"], new)
            t_ok += 1
        msg = f"已寫入記憶 {n} 條" + (f"、修改範本 {t_ok} 處" if t_ok else "") + ("。\n沒套用：" + "；".join(t_bad) if t_bad else "。")
        self.app.log("長期記憶：" + msg.replace("\n", " "))
        if memory.size() > memory.LIMIT:
            msg += f"\n\n記憶已超過建議上限 {memory.LIMIT:,} 字，建議到「AI 記憶與提示詞 → 長期記憶」按「請 AI 整理記憶」。"
        messagebox.showinfo("完成", msg, parent=self.win)
        mw = getattr(self.app, "_memwin", None)
        if mw is not None and mw.win.winfo_exists():
            mw.reload_mem()
            mw.refresh_list()
        self.win.destroy()


def remember_dialog(app, parent, text: str = ""):
    """「記住這點…」：選一節、寫一句，直接新增一條長期記憶。"""
    import memory
    d = tk.Toplevel(parent)
    d.title("記住這點")
    d.transient(parent)
    ttk.Label(d, text="寫一句以後每次寫記錄都要記住的事（例如：「大華」指公司時寫「大華公司」）：", padding=(10, 10, 10, 4)).pack(anchor="w")
    v_sec = tk.StringVar(value="寫作偏好")
    ttk.Combobox(d, textvariable=v_sec, values=list(memory.SECTIONS), state="readonly", width=14).pack(anchor="w", padx=10)
    t = tk.Text(d, height=4, width=70, font=F_EDIT, wrap="word")
    t.insert("1.0", text.strip())
    t.pack(padx=10, pady=6)

    def ok():
        s = " ".join(t.get("1.0", "end").split())
        if not s:
            return
        memory.add_one(v_sec.get(), s)
        app.log(f"已記住（{v_sec.get()}）：{s}")
        mw = getattr(app, "_memwin", None)
        if mw is not None and mw.win.winfo_exists():
            mw.reload_mem()
        d.destroy()
    bf = ttk.Frame(d, padding=10)
    bf.pack(fill="x")
    ttk.Button(bf, text="記住", command=ok).pack(side="right")
    ttk.Button(bf, text="取消", command=d.destroy).pack(side="right", padx=6)


class PreviewDialog:
    """送出前檢視（本次送出層）。回傳 self.result：None＝取消；否則為要送出的提示（不含逐字稿）。"""

    def __init__(self, parent, name: str, filled: str, rebuild, extra_len: int, extra_label: str = "逐字稿"):
        """rebuild(template) → 用範本重新組出完整提示。extra_len：送出時接在最後的文字長度（逐字稿）。"""
        self.result, self.name, self.rebuild = None, name, rebuild
        w = self.win = tk.Toplevel(parent)
        w.title(f"送出前檢視：{name}")
        w.geometry("1100x760")
        w.transient(parent)
        w.grab_set()
        self.v_info = tk.StringVar()
        ttk.Label(w, textvariable=self.v_info, padding=(10, 8, 10, 0)).pack(anchor="w")
        nb = self.nb = ttk.Notebook(w)
        nb.pack(fill="both", expand=True, padx=8, pady=6)
        f1 = ttk.Frame(nb, padding=4)
        nb.add(f1, text="這次送出的內容（只用這一次）")
        self.t_full = _editor(f1, 24)
        self.t_full.insert("1.0", filled)
        self.t_full.insert("end", f"\n［以下接著送出{extra_label}本文，共 {extra_len:,} 字，這裡不顯示］", ("note",))
        self.t_full.tag_configure("note", foreground="#888")
        self.t_full.bind("<KeyRelease>", lambda _e: self.update_info())
        self.t_full.edit_reset()
        self.t_full.edit_modified(False)
        f2 = ttk.Frame(nb, padding=4)
        nb.add(f2, text="範本（改這裡可存成我的預設）")
        text, src = prompts.load(name)
        ttk.Label(f2, text=f"目前使用「{src}」。改完按「套用範本」更新左邊分頁，或直接「存成我的預設並送出」。", foreground="#555").pack(anchor="w")
        self.t_tpl = _editor(f2, 22)
        self.t_tpl.insert("1.0", text)
        _mark_fields(self.t_tpl, name)
        self.t_tpl.bind("<<Modified>>", lambda _e: self.t_tpl.edit_modified() and _mark_fields(self.t_tpl, name))
        self.t_tpl.edit_modified(False)
        ttk.Button(f2, text="套用範本（重新組出這次的內容）", command=self.apply_tpl).pack(anchor="w", pady=4)
        self.extra_len = extra_len
        self.update_info()
        bf = ttk.Frame(w, padding=8)
        bf.pack(fill="x")
        ttk.Button(bf, text="取消（不送）", command=w.destroy).pack(side="right")
        ttk.Button(bf, text="存成我的預設並送出", command=self.save_send).pack(side="right", padx=6)
        ttk.Button(bf, text="送出", style="Big.TButton", command=self.send).pack(side="right")
        w.wait_window()

    def _full(self) -> str:
        s = self.t_full.get("1.0", "end-1c")
        k = s.rfind("\n［以下接著送出")
        return s[:k] if k >= 0 else s

    def update_info(self):
        n = len(self._full())
        self.v_info.set(f"提示 {n:,} 字＋逐字稿 {self.extra_len:,} 字，共約 {n + self.extra_len:,} 字。"
                        "改「這次送出的內容」只影響這一次；要以後都這樣，請改「範本」分頁。")

    def apply_tpl(self):
        tpl = self.t_tpl.get("1.0", "end-1c")
        probs = [p for p in prompts.check(self.name, tpl) if p.startswith("不能")]
        if probs:
            messagebox.showwarning("範本有問題", "\n".join(probs), parent=self.win)
            return False
        self.t_full.delete("1.0", "end")
        self.t_full.insert("1.0", self.rebuild(tpl))
        self.t_full.insert("end", f"\n［以下接著送出逐字稿本文，共 {self.extra_len:,} 字，這裡不顯示］", ("note",))
        self.t_full.edit_modified(False)
        self.nb.select(0)
        self.update_info()
        return True

    def send(self):
        self.result = self._full()
        self.win.destroy()

    def save_send(self):
        if self.t_full.edit_modified() and not messagebox.askyesno(
                "確認", "「這次送出的內容」分頁裡的直接修改含這場會議的資料，不會存成預設，會被範本重新組出的內容取代。\n要繼續嗎？",
                parent=self.win):
            return
        tpl = self.t_tpl.get("1.0", "end-1c")
        probs = prompts.check(self.name, tpl)
        if [p for p in probs if p.startswith("不能")]:
            messagebox.showwarning("不能存", "\n".join(p for p in probs if p.startswith("不能")), parent=self.win)
            return
        prompts.save_user(self.name, tpl)
        self.result = self.rebuild(tpl)
        self.win.destroy()
