from core.meta import read_meta


def write(tmp_path, src):
    f = tmp_path / "iplot.py"
    f.write_text(src, encoding="utf-8")
    return f


def test_full_header(tmp_path):
    f = write(tmp_path, '"""第一段。\n\n第二段。"""\nTITLE = "開工"\n\n'
                        "def run(app):\n    pass\n\ndef on_files(app, paths):\n    pass\n")
    m = read_meta(f)
    assert (m.title, m.description, m.has_run, m.accepts_files, m.error) == (
        "開工", "第一段。", True, True, None)


def test_commented_title_is_none(tmp_path):
    m = read_meta(write(tmp_path, '# TITLE = "x"\ndef run(app):\n    pass\n'))
    assert m.title is None and m.has_run


def test_no_run(tmp_path):
    m = read_meta(write(tmp_path, "def on_files(app, paths):\n    pass\n"))
    assert m.has_run is False and m.accepts_files is True


def test_syntax_error(tmp_path):
    m = read_meta(write(tmp_path, "def run(app)\n  pass\n"))
    assert m.error.startswith("第 1 行")
    assert m.has_run is False


def test_bom_ok(tmp_path):
    f = tmp_path / "iplot.py"
    f.write_bytes(b"\xef\xbb\xbf" + b"def run(app):\n    pass\n")
    m = read_meta(f)
    assert m.error is None and m.has_run


def test_directory_named_iplot_py(tmp_path):
    d = tmp_path / "iplot.py"
    d.mkdir()
    m = read_meta(d)
    assert m.error is not None and m.has_run is False


def test_never_executes(tmp_path):
    marker = tmp_path / "side_effect"
    m = read_meta(write(tmp_path, f'open({str(marker)!r}, "w").close()\ndef run(app):\n    pass\n'))
    assert not marker.exists()
    assert m.has_run


def test_null_byte_does_not_crash(tmp_path):
    f = tmp_path / "iplot.py"
    f.write_bytes(b"x = 1\x00\ndef run(app):\n    pass\n")
    m = read_meta(f)
    assert m.error is not None and m.has_run is False
