"""tkinter 面板：安全模式（--safe）與網頁面板開不起來時的後備。薄的一層：只負責畫按鈕、
把動作交給 Core，不做任何決定。"""

import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

from core.core import Core
from core.errors import describe
from core.text import T
from core.types import ErrorInfo, Group, ModuleInfo, Scope
from ui import errlog
from ui import menu as ui_menu

COLORS = {"here": "blue", "parent": "red", "extra": "green"}
ERROR_ROLE = "panel.error"  # 錯誤那一列的「回報這個問題」交給提供它的模組（D110、D162，跟網頁面板一樣）


def _make_root(safe: bool) -> tk.Tk:
    """主視窗：有 tkinterdnd2 就用它（拖放 M2 才註冊）；安全模式、沒裝或載入失敗就用一般的 tkinter。"""
    if safe:
        return tk.Tk()
    try:
        from tkinterdnd2 import TkinterDnD
    except ImportError:
        return tk.Tk()
    before = tk._default_root
    try:
        return TkinterDnD.Tk()
    except (RuntimeError, tk.TclError):  # 原生 tkdnd 載入失敗：視窗已經建好就直接用它，只是沒有拖放
        made = tk._default_root  # 不 destroy：macOS 的 Tk 9.0 把沒跑過事件迴圈的視窗 destroy 後，下一個事件迴圈會當掉
        return made if made is not None and made is not before else tk.Tk()


class Panel:
    """iPLoT 的主視窗：上面是麵包屑和一組組按鈕，下面是訊息區。實作 core.View。"""

    def __init__(self, version: str, safe: bool) -> None:
        self.root = _make_root(safe)
        self.title, self.name, self.restarting = T["title"].format(version=version), "tkinter", False  # app.panel（D164）
        self.root.title(self.title + (T["safe_mode"] if safe else ""))
        self.root.geometry("420x600")
        self.core: Core | None = None
        self.recent, self.offer = errlog.Recent(), errlog.Offer()  # 最近的訊息；自動問「要回報嗎？」的節流（D150）
        self.crumbs = tk.Frame(self.root)
        self.crumbs.pack(fill="x", padx=8, pady=4)
        self.messages = tk.Text(self.root, height=10, wrap="word", state="disabled")
        self.messages.pack(side="bottom", fill="x")
        canvas = tk.Canvas(self.root, highlightthickness=0)
        bar = tk.Scrollbar(self.root, command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        canvas.pack(fill="both", expand=True)
        self.body = tk.Frame(canvas)
        canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        self.root.bind("<FocusIn>", self._focus)

    def attach(self, core: Core) -> None:
        """接上 Core；之後按鈕的動作都交給它，tkinter 回呼裡沒接住的例外也交給它回報。"""
        self.core = core
        self.root.report_callback_exception = core.report_internal

    def mainloop(self) -> None:
        """進入 tkinter 的事件迴圈。按了「重新啟動」（app.restart，D166）：迴圈結束後整個 iPLoT 從頭再來，--safe 照舊。"""
        self.root.mainloop()
        if self.restarting:
            os.chdir(self.core.home)
            os.execv(sys.executable, [sys.executable, str(self.core.home / "main.py"), *sys.argv[1:]])

    def restart(self) -> None:
        """app.restart：結束事件迴圈，mainloop 接著重新啟動。"""
        self.restarting = True
        self.root.quit()

    def _focus(self, event: tk.Event) -> None:
        if event.widget is self.root and self.core:
            self.core.rescan()

    def show(self, scope: Scope) -> None:
        """把範圍畫成麵包屑和按鈕；每次整個重畫。"""
        for frame in (self.crumbs, self.body):
            for w in frame.winfo_children():
                w.destroy()
        for i, crumb in enumerate(scope.crumbs):
            if i:
                tk.Label(self.crumbs, text="▸").pack(side="left")
            tk.Button(self.crumbs, text=crumb, command=lambda i=i: self.core.back(i)).pack(side="left")
        for group in scope.groups:
            self._group(group)

    def _group(self, group: Group) -> None:
        head = tk.Frame(self.body)
        head.pack(fill="x", padx=8, pady=(8, 0))
        tk.Label(head, text=group.label, font=("", 13, "bold")).pack(side="left")
        if group.note is None or group.level == "here":  # 其他根目錄讀不到時沒有地方可以建，不給 ＋；modules/ 被刪掉 create 會重建
            tk.Button(head, text="＋", command=lambda: self._create(group.root)).pack(side="right")
        if not group.modules:
            tk.Label(self.body, text=group.note or T["empty_group"], fg="gray").pack(anchor="w", padx=24)
        for info in group.modules:
            self._row(info, COLORS.get(group.level, "black"))

    def _row(self, info: ModuleInfo, color: str) -> None:
        row = tk.Frame(self.body)
        row.pack(fill="x", padx=24)
        text = ("⚠ " if info.error else "") + info.title
        button = tk.Button(row, text=text, fg=color, anchor="w", command=lambda: self.core.press(info))
        button.pack(side="left", fill="x", expand=True)
        if info.has_children:
            tk.Button(row, text="▸", command=lambda: self.core.enter(info)).pack(side="left")
        menu = tk.Menu(button, tearoff=False)
        menu.add_command(label=T["menu_edit"], command=lambda: self.core.action(
            "edit", info.file, self.core.config.editor, None))
        menu.add_command(label=T["menu_reveal"], command=lambda: self.core.action("reveal", info.folder))
        menu.add_command(label=T["menu_terminal"],
                         command=lambda: self.core.action("terminal", info.folder))
        menu.add_command(label=T["menu_add_child"], command=lambda: self._create(info.folder))
        fixed = menu.index("end")

        def popup(event: tk.Event) -> str:
            self._extend(menu, fixed, info)
            menu.tk_popup(event.x_root, event.y_root)
            return "break"  # Control-click 不要同時算成左鍵按下

        for sequence in ("<Button-2>", "<Button-3>", "<Control-Button-1>"):
            button.bind(sequence, popup)

    def _extend(self, menu: tk.Menu, fixed: int, info: ModuleInfo) -> None:
        """右鍵選單打開時：固定的幾項後面，換上提供 menu.module 的模組這一次給的項目（D159）。"""
        menu.delete(fixed + 1, "end")
        for pick, label in zip(*ui_menu.items(self.core, info), strict=True):
            menu.add_command(label=label, command=lambda pick=pick: self.core.press(*pick, quiet=True))

    def _create(self, parent: Path) -> None:
        name = self.ask(T["ask_name"])
        if name is not None:
            self.core.create(parent, name)

    def log(self, text: str) -> None:
        """訊息區末尾加一行。"""
        self.recent.add(text)
        self._write(text + "\n")

    def report(self, error: ErrorInfo) -> None:
        """訊息區顯示完整 traceback，最後才是白話那一句和「打開檔案」：捲到底看到的是人話，不是 traceback。
        有模組提供 panel.error（而且不是它自己出的錯）時多一顆「回報這個問題」；也先交給它看一眼，它說值得回報就
        自動問一次要不要回報（這一輪事件做完才問，D150）。"""
        if error.kind == "InputCancelled":  # 在提問框按了取消：自己的動作，訊息區只說一行，不是錯誤（體驗 2-08b）
            self.log(T["module_cancelled"].format(module=error.module))
            return
        self.recent.add(describe(error))
        recent, buttons = self.recent.lines(), []
        if error.file is not None:
            buttons.append(tk.Button(self.messages, text=T["open_file"], command=lambda: self.core.action(
                "edit", error.file, self.core.config.editor, error.line)))
        info = self._reporter(error)
        if info is not None:
            buttons.append(tk.Button(self.messages, text=T["report_issue"], command=lambda: self._report(error, recent)))
            self.root.after_idle(self._notice, error, recent)
        self._write(error.traceback_text + describe(error) + "\n", *buttons)

    def _reporter(self, error: ErrorInfo) -> ModuleInfo | None:
        found = [m for m in self.core.providers(ERROR_ROLE) if m.name != error.module]
        return found[0] if found else None

    def _notice(self, error: ErrorInfo, recent: list[str]) -> None:
        info = self._reporter(error)
        if info is None:
            return
        worth = self.core.press(info, dict(info.provides)[ERROR_ROLE], (error, recent, False), quiet=True).value
        if worth is True and self.offer.due(error):
            self._offer(error, recent)

    def _offer(self, error: ErrorInfo, recent: list[str]) -> None:
        """「出錯了，要回報嗎？」：答回報就跟按那一列的鈕一樣；勾了「這次執行期間不要再問」就記下（只在記憶體）。"""
        answer = self.ask_offer(T["offer_report"].format(sentence=describe(error)))
        self.offer.muted = self.offer.muted or answer["mute"]
        if answer["report"]:
            self._report(error, recent)

    def ask_offer(self, prompt: str) -> dict:
        """「回報／不用」加一個「這次執行期間不要再問」的勾選框（messagebox 放不了勾選框）；關掉視窗算不用。"""
        top, mute, answer = tk.Toplevel(self.root), tk.BooleanVar(master=self.root), {"report": False}
        top.title(self.title)
        top.transient(self.root)
        tk.Label(top, text=prompt, justify="left", wraplength=360).pack(padx=12, pady=(12, 6), anchor="w")
        tk.Checkbutton(top, text=T["offer_mute"], variable=mute).pack(padx=12, anchor="w")
        row = tk.Frame(top)
        row.pack(padx=12, pady=12, anchor="e")

        def close(report: bool) -> None:
            answer["report"] = report
            top.destroy()

        tk.Button(row, text=T["offer_no"], command=lambda: close(False)).pack(side="left")
        tk.Button(row, text=T["offer_yes"], command=lambda: close(True)).pack(side="left", padx=(6, 0))
        top.grab_set()
        self.root.wait_window(top)
        return {**answer, "mute": mute.get()}

    def _report(self, error: ErrorInfo, recent: list[str]) -> None:
        info = self._reporter(error)
        if info is None:  # 畫出鈕之後被刪了
            return self.core.rescan()
        self.core.press(info, dict(info.provides)[ERROR_ROLE], (error, recent, True), quiet=True)
        return None

    def _write(self, text: str, *buttons: tk.Button) -> None:
        self.messages.configure(state="normal")
        self.messages.insert("end", text)
        for button in buttons:
            self.messages.window_create("end", window=button)
        if buttons:
            self.messages.insert("end", "\n")
        self.messages.configure(state="disabled")
        self.messages.see("end")

    def ask(self, prompt: str, default: str = "") -> str | None:
        """跳出對話框問一個字串；按取消回 None。"""
        return simpledialog.askstring(self.title, prompt, initialvalue=default, parent=self.root)

    def confirm(self, prompt: str) -> bool:
        """跳出「確定／取消」對話框；按確定回 True。"""
        return messagebox.askokcancel(self.title, prompt, parent=self.root)

    def page(self, title: str, html: str, api: object | None) -> None:
        """tkinter 面板沒有頁面：在訊息區記一行就回來。"""
        self.log(T["page_unsupported"])

    def choose_files(self) -> list[Path]:
        """跳出檔案選擇視窗；按取消回空清單。"""
        return [Path(p) for p in filedialog.askopenfilenames(parent=self.root)]

    def choose_folder(self) -> Path | None:
        """跳出資料夾選擇視窗；按取消回 None。"""
        folder = filedialog.askdirectory(parent=self.root)
        return Path(folder) if folder else None
