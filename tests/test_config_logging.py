import logging

from app.core.config import Settings
from app.core.logging import RedactSecretsFilter


def test_settings_defaults_and_cors_parsing():
    s = Settings(_env_file=None, cors_origins="http://a.com, http://b.com", log_level="debug")
    assert s.cors_origin_list == ["http://a.com", "http://b.com"]
    assert s.log_level == "DEBUG"


def test_production_flag():
    assert Settings(_env_file=None, app_env="production").is_production is True


def test_log_filter_redacts_secrets():
    rec = logging.LogRecord("t", logging.INFO, "", 0, "api_key=SUPERSECRET123 ok", (), None)
    RedactSecretsFilter().filter(rec)
    assert "SUPERSECRET123" not in rec.getMessage()
    assert "***" in rec.getMessage()
