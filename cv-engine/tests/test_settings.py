"""Configuration loading: env overrides, defaults, derived URLs, no secrets."""

from __future__ import annotations

from config.settings import Settings, describe_settings, load_settings


def test_defaults_are_offline_safe():
    s = load_settings(env={})
    assert s.sentinel_catalogue_url.endswith("cameras.json")
    assert s.conf_threshold == 0.35
    assert s.reconnect_min_s == 2.0
    assert s.reconnect_max_s == 30.0
    assert s.events_path == "/api/events"


def test_env_overrides_every_documented_variable():
    env = {
        "SENTINEL_CATALOGUE_URL": "https://example.test/cameras.json",
        "BACKEND_BASE_URL": "http://backend:9000",
        "MODEL_PATH": "/models/yolo11s.pt",
        "CONF_THRESHOLD": "0.55",
        "ANPR_CONF_THRESHOLD": "0.4",
        "FRAME_SKIP": "3",
        "RECONNECT_MIN": "1.5",
        "RECONNECT_MAX": "45",
        "EVIDENCE_DIR": "/var/lib/trinetra/evidence",
    }
    # Every name below is the one the brief documents, used verbatim.
    s = load_settings(env=dict(env))
    assert s.sentinel_catalogue_url == "https://example.test/cameras.json"
    assert s.backend_base_url == "http://backend:9000"
    assert s.model_path == "/models/yolo11s.pt"
    assert s.conf_threshold == 0.55
    assert s.anpr_conf_threshold == 0.4
    assert s.frame_skip == 3
    assert s.reconnect_min_s == 1.5
    assert s.reconnect_max_s == 45.0
    assert s.evidence_dir == "/var/lib/trinetra/evidence"


def test_invalid_numbers_fall_back_to_defaults_instead_of_crashing():
    s = load_settings(env={"CONF_THRESHOLD": "not-a-number", "FRAME_SKIP": "abc"})
    assert s.conf_threshold == Settings.conf_threshold
    assert s.frame_skip == Settings.frame_skip


def test_events_url_joins_base_and_path():
    s = load_settings(env={"BACKEND_BASE_URL": "http://x:1/"})
    assert s.events_url == "http://x:1/api/events"
    s2 = load_settings(env={"BACKEND_BASE_URL": "http://x", "EVENTS_PATH": "api/events"})
    assert s2.events_url == "http://x/api/events"


def test_booleans_and_lists_parse():
    s = load_settings(env={"ALLOW_HLS_FALLBACK": "false", "OCR_LANGUAGES": "en, hi "})
    assert s.allow_hls_fallback is False
    assert s.ocr_languages == ["en", "hi"]


def test_describe_settings_contains_no_secret_shaped_keys():
    s = load_settings(env={})
    keys = set(describe_settings(s))
    assert "conf_threshold" in keys
    assert not any(k for k in keys if "password" in k or "token" in k or "secret" in k)


def test_unknown_override_is_rejected():
    try:
        load_settings(env={}, not_a_setting=1)
    except KeyError:
        return
    raise AssertionError("expected KeyError for an unknown setting")
