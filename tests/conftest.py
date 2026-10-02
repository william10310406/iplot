import pytest

DEFAULT_SRC = 'def run(app):\n    print("ok")\n'


def make_module(parent, name, src=DEFAULT_SRC):
    """在 parent 底下建資料夾 name 並寫入 iplot.py，回傳資料夾。"""
    folder = parent / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "iplot.py").write_text(src, encoding="utf-8")
    return folder


@pytest.fixture
def home(tmp_path):
    """假的 iPLoT 程式資料夾：tmp/iPLoT，裡面有空的 modules/。"""
    h = tmp_path / "iPLoT"
    (h / "modules").mkdir(parents=True)
    return h
