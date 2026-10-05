import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core"
CJK = re.compile(r"[一-鿿]")
FORBIDDEN = ("subprocess", "sys.platform", "os.name", "startfile", "ctypes")


def test_bottom_layer_never_imports_tkinter():
    code = ("import sys; sys.modules['tkinter']=None; import core.types, core.text, core.meta, "
            "core.scan, core.errors, core.runner, core.history, core.create, "
            "core.app, core.core")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_core_has_no_os_code():
    """碰作業系統的事放 modules/作業系統，核心連字都不能出現（含註解與 docstring）。"""
    for p in sorted(CORE.glob("*.py")):
        src = p.read_text(encoding="utf-8")
        for word in FORBIDDEN:
            # 若有誤判（例如某個識別字剛好含 os.name），改用 re 加字界，不要放寬清單
            assert word not in src, f"core/{p.name} 出現 {word}"


def test_actions_module_is_gone():
    assert not (CORE / "actions.py").exists()


def _string_constants(path):
    """path 裡不是 docstring 的字串常數。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docs.add(id(first.value))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs]


def test_no_chinese_string_constants_outside_text():
    """D32：畫面文字都在 core/text.py；core/ 其他檔、ui/*.py、main.py 的字串常數沒有中文（註解與 docstring 不算）。"""
    files = [p for p in CORE.glob("*.py") if p.name != "text.py"] + list((ROOT / "ui").glob("*.py"))
    for p in sorted(files + [ROOT / "main.py"]):
        found = [s for s in _string_constants(p) if CJK.search(s)]
        assert not found, f"{p.relative_to(ROOT)} 有中文字串常數：{found}"


def test_core_never_imports_webview():
    """只有 ui/web.py 可以用 lib/ 裡的 pywebview；core/ 一行都不能 import 它。"""
    for p in sorted(CORE.glob("*.py")):
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                     else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            assert not any(n.split(".")[0] in ("webview", "ui") for n in names), f"core/{p.name} import 了 {names}"


# 面板本體（ui/index.html、app.js、style.css）：前端沒有自動測試，這裡只釘住它跟 Python 那一頭對得上

UI = ROOT / "ui"
PAGE = ("index.html", "app.js", "style.css")
JS_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)


def _page(name):
    assert (UI / name).exists(), f"ui/{name} 還沒有"
    return (UI / name).read_text(encoding="utf-8")


def test_ui_has_no_external_urls():
    """零外部資源：沒有 CDN、沒有網路字型、沒有函式庫，不需要網路。"""
    for name in PAGE:
        text = _page(name)
        for word in ("http://", "https://", "@import", "url(//"):
            assert word not in text, f"ui/{name} 出現 {word}"


def test_app_js_has_no_chinese_outside_comments():
    """畫面文字由 Python 整份送進去（iplot.init），app.js 只用 key；註解可以是中文。"""
    code = JS_COMMENT.sub("", _page("app.js"))
    assert not CJK.search(code), CJK.findall(code)


def test_app_js_uses_only_text_keys_that_exist():
    from core.text import T
    used = set(re.findall(r"\bT\.([a-z_]+)\b", JS_COMMENT.sub("", _page("app.js"))))
    assert used and used <= set(T), used - set(T)
    assert {"menu_run", "menu_enter", "menu_edit", "menu_reveal", "menu_terminal", "menu_add_child", "add_tile",
            "ask_name", "bad_name", "empty_group", "status_hint", "open_file", "details", "hide_details",
            "ok", "cancel"} <= used


def test_app_js_calls_exactly_the_bridge_methods():
    """頁面呼叫的 pywebview.api.<方法> 都是 Bridge 有的；Bridge 的方法（state 除外）頁面也都用到。"""
    from ui.web import Bridge
    bridge = {n for n in vars(Bridge) if not n.startswith("_")}
    called = set(re.findall(r"\bapi\(\)\.(\w+)\(", JS_COMMENT.sub("", _page("app.js"))))
    assert called <= bridge, called - bridge
    assert bridge - called <= {"state"}, bridge - called


def test_app_js_defines_every_entry_python_calls():
    """ui/web.py 用 evaluate_js 呼叫的 iplot.<名字>，app.js 都有定義，而且沒有多的。"""
    web = (UI / "web.py").read_text(encoding="utf-8")
    called = set(re.findall(r"self\._(?:js|dialog)\(\"(\w+)\"", web))
    defined = set(re.findall(r"^iplot\.(\w+) = ", _page("app.js"), re.M))
    assert called == defined == {"init", "show", "log", "report", "ask", "confirm"}


def test_index_html_loads_style_then_custom_css_then_script():
    """custom.css 在 style.css 之後載入，使用者的覆寫才蓋得過去；JS 全在 app.js，HTML 裡沒有行內的事件處理。"""
    html = _page("index.html")
    style, custom, script = (html.index(s) for s in ('href="style.css"', 'href="../custom.css"', 'src="app.js"'))
    assert style < custom < script
    assert not re.search(r"\son\w+\s*=", html) and not re.search(r"<script(?![^>]*\bsrc=)", html)
    assert not CJK.search(re.sub(r"<!--.*?-->", "", html, flags=re.S)), "index.html 的文字也由 Python 送進去（註解除外）"


def test_style_css_keeps_colors_in_the_variables_at_the_top():
    """style.css 開頭是色彩與尺寸的變數；其餘只用變數，改顏色只改那一段。"""
    css = _page("style.css")
    code = [line.strip() for line in JS_COMMENT.sub("", css).splitlines() if line.strip()]
    assert code[0].startswith(":root"), code[0]
    literal = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\((?!var)")
    stray = [line for line in code if literal.search(line) and not line.startswith("--")]
    assert not stray, stray
    assert "prefers-color-scheme: dark" in css
