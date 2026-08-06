import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.core.env import get_bool, get_choice, get_int, get_list, get_log_level


class TestGetBool:
    def test_missing_returns_default(self, monkeypatch):
        monkeypatch.delenv("SOME_BOOL", raising=False)
        assert get_bool("SOME_BOOL", True) is True
        assert get_bool("SOME_BOOL", False) is False

    @pytest.mark.parametrize("raw", ["true", "True", "TRUE", "1", "yes", "on"])
    def test_true_values(self, monkeypatch, raw):
        monkeypatch.setenv("SOME_BOOL", raw)
        assert get_bool("SOME_BOOL", False) is True

    @pytest.mark.parametrize("raw", ["false", "False", "FALSE", "0", "no", "off"])
    def test_false_values(self, monkeypatch, raw):
        monkeypatch.setenv("SOME_BOOL", raw)
        assert get_bool("SOME_BOOL", True) is False

    def test_the_bool_of_env_get_pitfall_this_helper_exists_to_avoid(self, monkeypatch):
        """bool(os.environ.get("SOME_BOOL")) would be True here — any non-empty
        string, including "false", is truthy in Python. get_bool must not
        repeat that mistake."""
        monkeypatch.setenv("SOME_BOOL", "false")
        assert bool("false") is True  # the pitfall itself
        assert get_bool("SOME_BOOL", True) is False  # the helper avoids it

    def test_malformed_value_raises(self, monkeypatch):
        monkeypatch.setenv("SOME_BOOL", "maybe")
        with pytest.raises(ImproperlyConfigured):
            get_bool("SOME_BOOL", True)

    def test_present_but_empty_is_treated_as_unset(self, monkeypatch):
        """A `.env` line like `SOME_BOOL=` sets the key with an empty value
        (not the same as the key being absent) — this must fall through to
        `default`, not raise, matching the "leave blank to use the default"
        convention documented in .env.example."""
        monkeypatch.setenv("SOME_BOOL", "")
        assert get_bool("SOME_BOOL", True) is True
        assert get_bool("SOME_BOOL", False) is False


class TestGetList:
    def test_missing_returns_default(self, monkeypatch):
        monkeypatch.delenv("SOME_LIST", raising=False)
        assert get_list("SOME_LIST") == []
        assert get_list("SOME_LIST", default=("a", "b")) == ["a", "b"]

    def test_parses_comma_separated(self, monkeypatch):
        monkeypatch.setenv("SOME_LIST", "a,b,c")
        assert get_list("SOME_LIST") == ["a", "b", "c"]

    def test_strips_whitespace_and_drops_blanks(self, monkeypatch):
        monkeypatch.setenv("SOME_LIST", " a , , b ,")
        assert get_list("SOME_LIST") == ["a", "b"]

    def test_empty_string_returns_empty_list(self, monkeypatch):
        monkeypatch.setenv("SOME_LIST", "")
        assert get_list("SOME_LIST") == []


class TestGetInt:
    def test_missing_returns_default(self, monkeypatch):
        monkeypatch.delenv("SOME_INT", raising=False)
        assert get_int("SOME_INT", 42) == 42

    def test_parses_valid_integer(self, monkeypatch):
        monkeypatch.setenv("SOME_INT", "123")
        assert get_int("SOME_INT", 0) == 123

    def test_negative_integer(self, monkeypatch):
        monkeypatch.setenv("SOME_INT", "-5")
        assert get_int("SOME_INT", 0) == -5

    def test_malformed_value_raises(self, monkeypatch):
        monkeypatch.setenv("SOME_INT", "abc")
        with pytest.raises(ImproperlyConfigured):
            get_int("SOME_INT", 0)

    def test_error_message_names_the_variable_and_value_but_nothing_else(self, monkeypatch):
        monkeypatch.setenv("SOME_INT", "abc")
        with pytest.raises(ImproperlyConfigured) as exc_info:
            get_int("SOME_INT", 0)
        assert "SOME_INT" in str(exc_info.value)
        assert "abc" in str(exc_info.value)

    def test_present_but_empty_is_treated_as_unset(self, monkeypatch):
        """Same reasoning as TestGetBool's equivalent case — a blank `.env`
        value (e.g. GUNICORN_WORKERS=) must fall through to `default`, not
        raise ImproperlyConfigured. This exact gap previously crashed
        gunicorn's config loading in the production Docker image when
        GUNICORN_WORKERS/GUNICORN_TIMEOUT were left blank."""
        monkeypatch.setenv("SOME_INT", "")
        assert get_int("SOME_INT", 42) == 42


class TestGetChoice:
    _CHOICES = ("json", "text", "plain")

    def test_missing_returns_default(self, monkeypatch):
        monkeypatch.delenv("SOME_CHOICE", raising=False)
        assert get_choice("SOME_CHOICE", "json", self._CHOICES) == "json"

    def test_accepts_an_exact_choice(self, monkeypatch):
        monkeypatch.setenv("SOME_CHOICE", "text")
        assert get_choice("SOME_CHOICE", "json", self._CHOICES) == "text"

    def test_case_insensitive_but_normalizes_to_the_declared_spelling(self, monkeypatch):
        monkeypatch.setenv("SOME_CHOICE", "TEXT")
        assert get_choice("SOME_CHOICE", "json", self._CHOICES) == "text"

    def test_present_but_empty_is_treated_as_unset(self, monkeypatch):
        monkeypatch.setenv("SOME_CHOICE", "")
        assert get_choice("SOME_CHOICE", "json", self._CHOICES) == "json"

    def test_unknown_value_raises(self, monkeypatch):
        monkeypatch.setenv("SOME_CHOICE", "xml")
        with pytest.raises(ImproperlyConfigured):
            get_choice("SOME_CHOICE", "json", self._CHOICES)

    def test_error_message_never_suggests_an_import_path(self, monkeypatch):
        """This helper's whole reason for existing (Chunk J §15: "Do not
        allow arbitrary import paths from environment values") is that a
        malformed value is rejected outright, not resolved to a class/module
        — the error message itself must only ever mention the fixed choice
        set, never anything resembling a dotted import path."""
        monkeypatch.setenv("SOME_CHOICE", "apps.evil.PayloadFormatter")
        with pytest.raises(ImproperlyConfigured) as exc_info:
            get_choice("SOME_CHOICE", "json", self._CHOICES)
        assert str(self._CHOICES) in str(exc_info.value)


class TestGetLogLevel:
    def test_missing_returns_default(self, monkeypatch):
        monkeypatch.delenv("SOME_LEVEL", raising=False)
        assert get_log_level("SOME_LEVEL", "INFO") == "INFO"

    @pytest.mark.parametrize("raw", ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "warning"])
    def test_accepts_every_standard_level(self, monkeypatch, raw):
        monkeypatch.setenv("SOME_LEVEL", raw)
        assert get_log_level("SOME_LEVEL", "INFO") == raw.upper()

    def test_rejects_a_nonstandard_level(self, monkeypatch):
        monkeypatch.setenv("SOME_LEVEL", "TRACE")
        with pytest.raises(ImproperlyConfigured):
            get_log_level("SOME_LEVEL", "INFO")
