"""Unit tests for _build_args timezone/locale injection and deprecation compat."""

import warnings

from cloakbrowser.browser import _build_args, _migrate_timezone_id


def test_timezone_injected():
    """--fingerprint-timezone flag should appear when timezone is set."""
    args = _build_args(stealth_args=True, extra_args=None, timezone="America/New_York")
    assert "--fingerprint-timezone=America/New_York" in args


def test_locale_injected():
    """--lang flag should appear when locale is set."""
    args = _build_args(stealth_args=True, extra_args=None, locale="en-US")
    assert "--lang=en-US" in args


def test_both_injected():
    """Both flags should appear when both are set."""
    args = _build_args(stealth_args=True, extra_args=None, timezone="Europe/Berlin", locale="de-DE")
    assert "--fingerprint-timezone=Europe/Berlin" in args
    assert "--lang=de-DE" in args


def test_timezone_independent_of_stealth_args():
    """--fingerprint-timezone should be injected even when stealth_args=False."""
    args = _build_args(stealth_args=False, extra_args=None, timezone="America/New_York", locale="en-US")
    assert "--fingerprint-timezone=America/New_York" in args
    assert "--lang=en-US" in args
    # No stealth fingerprint args
    assert not any(a.startswith("--fingerprint=") for a in args)


def test_no_flags_when_not_set():
    """No timezone/lang flags when params are None."""
    args = _build_args(stealth_args=True, extra_args=None)
    assert not any(a.startswith("--fingerprint-timezone=") for a in args)
    assert not any(a.startswith("--lang=") for a in args)


def test_extra_args_preserved():
    """Extra args should still be included alongside timezone/locale."""
    args = _build_args(stealth_args=True, extra_args=["--disable-gpu"], timezone="Asia/Tokyo", locale="ja-JP")
    assert "--disable-gpu" in args
    assert "--fingerprint-timezone=Asia/Tokyo" in args
    assert "--lang=ja-JP" in args


# --- _migrate_timezone_id deprecation compat ---


def test_migrate_old_param_only():
    """timezone_id in kwargs should be promoted to timezone."""
    kwargs = {"timezone_id": "Europe/Paris"}
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = _migrate_timezone_id(None, kwargs)
    assert result == "Europe/Paris"
    assert "timezone_id" not in kwargs
    assert len(w) == 1 and issubclass(w[0].category, FutureWarning)


def test_migrate_new_param_wins():
    """Explicit timezone takes precedence; timezone_id is still popped."""
    kwargs = {"timezone_id": "Europe/Paris"}
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = _migrate_timezone_id("UTC", kwargs)
    assert result == "UTC"
    assert "timezone_id" not in kwargs
    assert len(w) == 1


def test_migrate_no_old_param():
    """No warning when timezone_id is absent."""
    kwargs = {"other": "value"}
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = _migrate_timezone_id("UTC", kwargs)
    assert result == "UTC"
    assert "other" in kwargs
    assert len(w) == 0


def test_migrate_both_none():
    """Neither param set — returns None, no warning."""
    kwargs = {}
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = _migrate_timezone_id(None, kwargs)
    assert result is None
    assert len(w) == 0
