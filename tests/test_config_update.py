from voice_input.config_update import set_config_value


def test_replace_existing_key_preserves_rest(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('api_key = "sk-keep"\n# my comment\nhotkey = "f9"\n')
    set_config_value(p, "hotkey", "f10")
    text = p.read_text()
    assert 'hotkey = "f10"' in text
    assert 'api_key = "sk-keep"' in text and "# my comment" in text


def test_append_missing_key(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('api_key = "sk-keep"\n')
    set_config_value(p, "language", "yue")
    assert 'language = "yue"' in p.read_text()


def test_none_removes_key(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('api_key = "sk-keep"\nlanguage = "en"\n')
    set_config_value(p, "language", None)
    assert "language" not in p.read_text()


def test_value_with_quotes_and_newlines_is_escaped(tmp_path):
    import tomllib

    p = tmp_path / "config.toml"
    p.write_text('api_key = "sk-keep"\n')
    set_config_value(p, "hotkey", 'f9"\nbad = "1')
    data = tomllib.loads(p.read_text())
    assert data["hotkey"] == 'f9"\nbad = "1'
    assert "bad" not in data
