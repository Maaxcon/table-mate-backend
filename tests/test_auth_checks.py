from django.test import override_settings

from apps.authentication.checks import google_oauth_settings_check


@override_settings(GOOGLE_CLIENT_ID="id", GOOGLE_CLIENT_SECRET="secret")
def test_no_warnings_when_configured() -> None:
    assert google_oauth_settings_check(None) == []


@override_settings(GOOGLE_CLIENT_ID="", GOOGLE_CLIENT_SECRET="")
def test_warns_for_both_when_empty() -> None:
    ids = {w.id for w in google_oauth_settings_check(None)}
    assert ids == {"authentication.W001", "authentication.W002"}


@override_settings(GOOGLE_CLIENT_ID="id", GOOGLE_CLIENT_SECRET="")
def test_warns_only_for_missing_secret() -> None:
    warnings = google_oauth_settings_check(None)
    assert [w.id for w in warnings] == ["authentication.W002"]
    assert "GOOGLE_CLIENT_SECRET" in warnings[0].msg
