"""tkinter 面板：薄的一層。只負責畫按鈕、把動作交給 Core，不做任何決定。"""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, simpledialog

from . import actions
from .core import Core
from .errors import describe
from .text import T
from .types import ErrorInfo, Group, ModuleInfo, Scope

COLORS = {"here": "blue", "parent": "red", "extra": "green"}


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
        self.title = T["title"].format(version=version)
        self.root.title(self.title + (T["safe_mode"] if safe else ""))
        self.root.geometry("420x600")
        self.core: Core | None = None
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
        """接上 Core；之後按鈕的動作都交給它。"""
        self.core = core

    @property
    def window(self) -> tk.Tk:
        """tkinter 主視窗。"""
        return self.root

    def mainloop(self) -> None:
        """進入 tkinter 的事件迴圈。"""
        self.root.mainloop()

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
        if group.note is None:  # 根目錄讀不到時沒有地方可以建，不給 ＋
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
        menu.add_command(label=T["menu_edit"],
                         command=lambda: actions.edit(info.file, self.core.config.editor))
        menu.add_command(label=T["menu_reveal"], command=lambda: actions.reveal(info.folder))
        menu.add_command(label=T["menu_terminal"], command=lambda: actions.terminal(info.folder))

        def popup(event: tk.Event) -> str:
            menu.tk_popup(event.x_root, event.y_root)
            return "break"  # Control-click 不要同時算成左鍵按下

        for sequence in ("<Button-2>", "<Button-3>", "<Control-Button-1>"):
            button.bind(sequence, popup)

    def _create(self, parent: Path) -> None:
        name = self.ask(T["ask_name"])
        if name is not None:
            self.core.create(parent, name)

    def log(self, text: str) -> None:
        """訊息區末尾加一行。"""
        self._write(text + "\n")

    def report(self, error: ErrorInfo) -> None:
        """訊息區顯示白話錯誤和完整 traceback；有檔案時附一顆「打開檔案」。"""
        button = None
        if error.file is not None:
            button = tk.Button(self.messages, text=T["open_file"], command=lambda: actions.edit(
                error.file, self.core.config.editor, error.line))
        self._write(describe(error) + "\n" + error.traceback_text, button)

    def _write(self, text: str, button: tk.Button | None = None) -> None:
        self.messages.configure(state="normal")
        self.messages.insert("end", text)
        if button is not None:
            self.messages.window_create("end", window=button)
            self.messages.insert("end", "\n")
        self.messages.configure(state="disabled")
        self.messages.see("end")

    def ask(self, prompt: str, default: str = "") -> str | None:
        """跳出對話框問一個字串；按取消回 None。"""
        return simpledialog.askstring(self.title, prompt, initialvalue=default, parent=self.root)

    def choose_files(self) -> list[Path]:
        """跳出檔案選擇視窗；按取消回空清單。"""
        return [Path(p) for p in filedialog.askopenfilenames(parent=self.root)]

    def choose_folder(self) -> Path | None:
        """跳出資料夾選擇視窗；按取消回 None。"""
        folder = filedialog.askdirectory(parent=self.root)
        return Path(folder) if folder else None
