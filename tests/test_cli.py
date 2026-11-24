"""python3 main.py --run（ui/cli.py，D163）：在面板外跑一個模組，跟面板按下一樣另開工作程序。"""

import builtins
import sys

import pytest
from conftest import make_module

from core.core import Core
from core.text import T
from core.types import DEFAULT_CONFIG, ErrorInfo
from ui import cli

HELLO = "def run(app):\n    print('哈囉')\n\ndef on_files(app, paths):\n    print('檔案', [p.name for p in paths])\n"


def scanned(home):
    core = Core(home, DEFAULT_CONFIG, cli.TerminalView())
    core.rescan()
    return core


def test_resolve_by_folder_by_iplot_py_and_by_name(home, tmp_path):
    folder = make_module(home / "modules", "甲")
    core = scanned(home)
    for target, cwd in ((str(folder), tmp_path), ("iPLoT/modules/甲/iplot.py", tmp_path), ("甲", tmp_path)):
        info, problem = cli.resolve(core, target, cwd)
        assert problem is None and info.folder == folder.resolve() and info.level == "here"


def test_resolve_a_folder_below_a_module_is_a_child_and_outside_every_root_is_extra(home, tmp_path, tmp_path_factory):
    kid = make_module(make_module(home / "modules", "甲"), "乙")
    loose = make_module(tmp_path_factory.mktemp("別處"), "丙")  # tmp_path 本身是 iPLoT 的上一層（".."），不算別處
    core = scanned(home)
    assert cli.resolve(core, str(kid), tmp_path)[0].level == "child"
    assert cli.resolve(core, str(loose), tmp_path)[0].level == "extra"


def test_resolve_says_why_it_cannot(home, tmp_path):
    (tmp_path / "空的").mkdir()
    make_module(home / "modules", "甲")
    core = scanned(home)
    assert cli.resolve(core, str(tmp_path / "空的"), tmp_path) == (None, T["cli_not_module"].format(path=tmp_path / "空的"))
    assert cli.resolve(core, "~/沒有這個/甲", tmp_path) == (None, T["cli_gone"].format(path="~/沒有這個/甲"))
    assert cli.resolve(core, "乙", tmp_path) == (None, T["not_found"].format(name="乙", paths=""))


def test_run_without_arguments_prints_the_usage(home, capsys):
    assert cli.run(home, DEFAULT_CONFIG, None, []) == cli.FAILED
    assert T["cli_usage"] in capsys.readouterr().out


def test_run_in_the_terminal_in_its_own_process(home, tmp_path, capsys):
    folder = make_module(home / "modules", "甲", HELLO)
    assert cli.run(home, DEFAULT_CONFIG, None, [str(folder)], cwd=tmp_path) == cli.OK
    assert "哈囉" in capsys.readouterr().out
    assert cli.run(home, DEFAULT_CONFIG, None, ["甲", "a.txt"], cwd=tmp_path) == cli.OK
    assert "檔案 ['a.txt']" in capsys.readouterr().out


def test_run_an_error_prints_the_sentence_and_exits_1(home, tmp_path, capsys):
    make_module(home / "modules", "壞", "def run(app):\n    1 / 0\n")
    assert cli.run(home, DEFAULT_CONFIG, None, ["壞"], cwd=tmp_path) == cli.FAILED
    out = capsys.readouterr().out
    assert "ZeroDivisionError" in out and "Traceback" in out


def test_run_a_module_that_is_not_found_exits_1(home, tmp_path, capsys):
    assert cli.run(home, DEFAULT_CONFIG, None, ["沒有"], cwd=tmp_path) == cli.FAILED
    assert T["not_found"].format(name="沒有", paths="") in capsys.readouterr().out


def test_questions_are_answered_in_the_terminal(home, tmp_path, capsys, monkeypatch):
    make_module(home / "modules", "問", "def run(app):\n    print('答', app.ask('名字'), app.confirm('確定'))\n")
    answers = iter(["小明", "y"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))
    assert cli.run(home, DEFAULT_CONFIG, None, ["問"], cwd=tmp_path) == cli.OK
    assert "答 小明 True" in capsys.readouterr().out


def test_terminal_view_ctrl_d_cancels_and_files_split_like_a_shell(monkeypatch):
    view = cli.TerminalView()

    def eof(prompt=""):
        raise EOFError

    monkeypatch.setattr(builtins, "input", eof)
    assert view.ask("x") is None and view.confirm("x") is False and view.choose_files() == []
    assert view.choose_folder() is None
    monkeypatch.setattr(builtins, "input", lambda prompt="": "")
    assert view.ask("x", "預設") == "預設"
    monkeypatch.setattr(builtins, "input", lambda prompt="": "'a b.txt' c.txt")
    assert [p.name for p in view.choose_files()] == ["a b.txt", "c.txt"]
    monkeypatch.setattr(builtins, "input", lambda prompt="": "/tmp")
    assert view.choose_folder() == Path("/tmp")


def test_config_error_is_reported_before_running(home, tmp_path, capsys):
    make_module(home / "modules", "甲", HELLO)
    err = ErrorInfo("SyntaxError", "invalid syntax", home / "config.py", 1, "", "config", None)
    assert cli.run(home, DEFAULT_CONFIG, err, ["甲"], cwd=tmp_path) == cli.OK
    out = capsys.readouterr().out
    assert out.index("config.py") < out.index("哈囉")


OUTSIDE = ('PROVIDES = {"run.outside": "outside"}\nfrom pathlib import Path\n\ndef run(app):\n    pass\n\n'
           "def outside(app, core, info, files, problem, err):\n"
           "    Path(app.home, 'got.txt').write_text(f'{info.name} {[f.name for f in files]} {problem}', encoding='utf-8')\n"
           "    return 0 if info is not None else 1\n")


def test_a_run_outside_provider_gets_the_module_already_found(home, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "path", list(sys.path))
    make_module(home / "modules", "互通的替身", OUTSIDE)
    make_module(home / "modules", "甲", HELLO)
    assert cli.run(home, DEFAULT_CONFIG, None, ["甲", "a.txt"], cwd=tmp_path) == cli.OK
    assert (home / "got.txt").read_text(encoding="utf-8") == "甲 ['a.txt'] None"


def test_a_provider_whose_window_cannot_open_falls_back_to_the_terminal(home, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(sys, "path", list(sys.path))
    make_module(home / "modules", "互通的替身", 'PROVIDES = {"run.outside": "outside"}\n\ndef run(app):\n    pass\n\n'
                "def outside(app, core, info, files, problem, err):\n    raise ImportError('No module named webview')\n")
    make_module(home / "modules", "甲", HELLO)
    assert cli.run(home, DEFAULT_CONFIG, None, ["甲"], cwd=tmp_path) == cli.OK
    out = capsys.readouterr().out
    assert T["cli_window_failed"].format(message="No module named webview") in out and "哈囉" in out
    assert "webview" in (home / "logs" / "iplot.log").read_text(encoding="utf-8")


@pytest.mark.parametrize("news", [None, "隨附的模組換成新版了"])
def test_main_run_dispatches_to_the_cli_without_opening_a_panel(monkeypatch, capsys, news):
    import test_main
    main = test_main.load_main()
    seen = []
    monkeypatch.setattr(sys, "argv", ["main.py", "--run", "甲", "a.txt"])
    monkeypatch.setattr(main, "bundle_news", lambda home, version: news)
    monkeypatch.setattr(cli, "run", lambda home, config, err, argv: seen.append(argv) or 3)
    monkeypatch.setattr(main, "run_web", lambda *a, **kw: pytest.fail("不該開面板"))
    with pytest.raises(SystemExit) as stop:
        main.main()
    assert stop.value.code == 3 and seen == [["甲", "a.txt"]]
    assert capsys.readouterr().out == (f"{news}\n" if news else "")
