def test_version_is_string():
    import core
    assert core.__version__.startswith("0.2.0")
