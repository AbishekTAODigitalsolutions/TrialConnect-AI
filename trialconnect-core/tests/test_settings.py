from app.config import Settings


def test_settings_default_values(monkeypatch) -> None:
    monkeypatch.delenv("LLM_ENABLED", raising=False)
    settings = Settings(_env_file=None)
    assert settings.PROJECT_NAME == "Clinical Connect AI"
    assert settings.LLM_ENABLED is False


def test_database_url_escapes_reserved_password_characters() -> None:
    settings = Settings(_env_file=None, POSTGRES_PASSWORD="pass@word", POSTGRES_SCHEMA="trialconnect")
    url = settings.database_url
    assert url.password == "pass@word"
    assert url.query["options"] == "-c search_path=trialconnect"
    rendered_url = url.render_as_string(hide_password=False)
    assert "pass%40word@" in rendered_url


def test_database_schema_must_be_a_safe_identifier() -> None:
    settings = Settings(_env_file=None, POSTGRES_SCHEMA="schema;DROP")
    try:
        settings.database_url
    except ValueError as exc:
        assert "valid unquoted PostgreSQL identifier" in str(exc)
    else:
        raise AssertionError("invalid schema names must be rejected")
