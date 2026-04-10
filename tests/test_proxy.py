"""Tests for proxy URL parsing and credential extraction."""

from unittest.mock import patch

from cloakbrowser.browser import (
    _is_socks_proxy,
    _parse_proxy_url,
    _resolve_proxy_config,
    maybe_resolve_geoip,
)


class TestParseProxyUrl:
    def test_no_credentials(self):
        assert _parse_proxy_url("http://proxy:8080") == {"server": "http://proxy:8080"}

    def test_with_credentials(self):
        result = _parse_proxy_url("http://user:pass@proxy:8080")
        assert result == {"server": "http://proxy:8080", "username": "user", "password": "pass"}

    def test_url_encoded_password(self):
        result = _parse_proxy_url("http://user:p%40ss%3Aword@proxy:8080")
        assert result["password"] == "p@ss:word"
        assert result["username"] == "user"
        assert result["server"] == "http://proxy:8080"

    def test_socks5(self):
        result = _parse_proxy_url("socks5://user:pass@proxy:1080")
        assert result["server"] == "socks5://proxy:1080"
        assert result["username"] == "user"
        assert result["password"] == "pass"

    def test_no_port(self):
        result = _parse_proxy_url("http://user:pass@proxy")
        assert result["server"] == "http://proxy"
        assert result["username"] == "user"

    def test_username_only(self):
        result = _parse_proxy_url("http://user@proxy:8080")
        assert result["server"] == "http://proxy:8080"
        assert result["username"] == "user"
        assert "password" not in result


class TestBuildProxyKwargs:
    """Tests for _resolve_proxy_config (formerly _build_proxy_kwargs) HTTP path."""

    def test_none(self):
        kwargs, args = _resolve_proxy_config(None)
        assert kwargs == {}
        assert args == []

    def test_simple_proxy(self):
        kwargs, args = _resolve_proxy_config("http://proxy:8080")
        assert kwargs == {"proxy": {"server": "http://proxy:8080"}}
        assert args == []

    def test_proxy_with_auth(self):
        kwargs, args = _resolve_proxy_config("http://user:pass@proxy:8080")
        assert kwargs == {
            "proxy": {"server": "http://proxy:8080", "username": "user", "password": "pass"}
        }
        assert args == []

    def test_proxy_dict_passthrough(self):
        proxy_dict = {"server": "http://proxy:8080", "bypass": ".google.com,localhost"}
        kwargs, args = _resolve_proxy_config(proxy_dict)
        assert kwargs == {"proxy": proxy_dict}
        assert args == []

    def test_proxy_dict_with_auth(self):
        proxy_dict = {
            "server": "http://proxy:8080",
            "username": "user",
            "password": "pass",
            "bypass": ".example.com",
        }
        kwargs, args = _resolve_proxy_config(proxy_dict)
        assert kwargs == {"proxy": proxy_dict}
        assert args == []


class TestMaybeResolveGeoip:
    @patch("cloakbrowser.geoip.resolve_proxy_geo_with_ip", return_value=("America/New_York", "en-US", "1.2.3.4"))
    def test_geoip_with_string_proxy(self, mock_geo):
        tz, locale, ip = maybe_resolve_geoip(True, "http://proxy:8080", None, None)
        mock_geo.assert_called_once_with("http://proxy:8080")
        assert tz == "America/New_York"
        assert locale == "en-US"
        assert ip == "1.2.3.4"

    @patch("cloakbrowser.geoip.resolve_proxy_geo_with_ip", return_value=("Europe/London", "en-GB", "5.6.7.8"))
    def test_geoip_with_dict_proxy_extracts_server(self, mock_geo):
        proxy_dict = {"server": "http://proxy:8080", "bypass": ".google.com"}
        tz, locale, ip = maybe_resolve_geoip(True, proxy_dict, None, None)
        mock_geo.assert_called_once_with("http://proxy:8080")
        assert tz == "Europe/London"
        assert locale == "en-GB"

    def test_geoip_disabled_skips_resolution(self):
        tz, locale, ip = maybe_resolve_geoip(False, "http://proxy:8080", None, None)
        assert tz is None
        assert locale is None
        assert ip is None

    def test_geoip_no_proxy_skips_resolution(self):
        tz, locale, ip = maybe_resolve_geoip(True, None, None, None)
        assert tz is None
        assert locale is None
        assert ip is None

    @patch("cloakbrowser.geoip.resolve_proxy_geo_with_ip", return_value=("Asia/Tokyo", "ja-JP", "9.8.7.6"))
    def test_geoip_preserves_explicit_timezone(self, mock_geo):
        tz, locale, _ip = maybe_resolve_geoip(True, "http://proxy:8080", "Europe/Berlin", None)
        assert tz == "Europe/Berlin"
        assert locale == "ja-JP"

    @patch("cloakbrowser.geoip.resolve_proxy_geo_with_ip", return_value=("America/New_York", "en-US", "1.2.3.4"))
    def test_geoip_normalizes_bare_proxy_with_creds(self, mock_geo):
        # "user:pass@host:port" must be normalized to http:// before geoip lookup.
        tz, locale, _ip = maybe_resolve_geoip(True, "user:pass@proxy:8080", None, None)
        mock_geo.assert_called_once_with("http://user:pass@proxy:8080")
        assert tz == "America/New_York"
        assert locale == "en-US"

    @patch("cloakbrowser.geoip.resolve_proxy_geo_with_ip", return_value=("America/New_York", "en-US", "1.2.3.4"))
    def test_geoip_normalizes_schemeless_proxy_no_creds(self, mock_geo):
        # "host:port" (no @ and no scheme) must also be normalized.
        tz, locale, _ip = maybe_resolve_geoip(True, "proxy:8080", None, None)
        mock_geo.assert_called_once_with("http://proxy:8080")
        assert tz == "America/New_York"

    @patch("cloakbrowser.geoip.resolve_proxy_geo_with_ip", return_value=("Europe/Berlin", "de-DE", "5.6.7.8"))
    def test_geoip_socks5_dict_reconstructs_credentials(self, mock_geo):
        proxy_dict = {"server": "socks5://proxy:1080", "username": "user", "password": "pass"}
        tz, locale, ip = maybe_resolve_geoip(True, proxy_dict, None, None)
        mock_geo.assert_called_once_with("socks5://user:pass@proxy:1080")
        assert tz == "Europe/Berlin"
        assert locale == "de-DE"

    @patch("cloakbrowser.geoip.resolve_proxy_geo_with_ip", return_value=("Europe/Berlin", "de-DE", "5.6.7.8"))
    def test_geoip_socks5_dict_no_auth_uses_server(self, mock_geo):
        proxy_dict = {"server": "socks5://proxy:1080"}
        tz, locale, ip = maybe_resolve_geoip(True, proxy_dict, None, None)
        mock_geo.assert_called_once_with("socks5://proxy:1080")

    @patch("cloakbrowser.geoip.resolve_proxy_geo_with_ip", return_value=("Europe/London", "en-GB", "1.1.1.1"))
    def test_geoip_http_dict_does_not_inline_creds(self, mock_geo):
        # HTTP dict: credentials stay separate, only server URL passed
        proxy_dict = {"server": "http://proxy:8080", "username": "user", "password": "pass"}
        tz, locale, ip = maybe_resolve_geoip(True, proxy_dict, None, None)
        mock_geo.assert_called_once_with("http://proxy:8080")


class TestBareProxyFormat:
    """_parse_proxy_url must handle bare 'user:pass@host:port' strings (no scheme)."""

    def test_bare_with_credentials(self):
        r = _parse_proxy_url("user:pass@proxy:8080")
        assert r["username"] == "user"
        assert r["password"] == "pass"
        assert r["server"] == "http://proxy:8080"

    def test_bare_credentials_not_in_server(self):
        r = _parse_proxy_url("user:pass@proxy1.example.com:5610")
        assert "user" not in r["server"]
        assert "pass" not in r["server"]

    def test_bare_username_only(self):
        r = _parse_proxy_url("user@proxy:8080")
        assert r["username"] == "user"
        assert "password" not in r
        assert r["server"] == "http://proxy:8080"

    def test_bare_no_port(self):
        r = _parse_proxy_url("user:pass@proxy.example.com")
        assert r["username"] == "user"
        assert r["password"] == "pass"
        assert r["server"] == "http://proxy.example.com"

    def test_bare_no_credentials_passthrough(self):
        # "host:port" without @ — no scheme, no creds — pass through unchanged
        r = _parse_proxy_url("proxy:8080")
        assert r == {"server": "proxy:8080"}

    def test_resolve_proxy_config_bare(self):
        kwargs, args = _resolve_proxy_config("user:pass@proxy:8080")
        assert kwargs["proxy"]["username"] == "user"
        assert kwargs["proxy"]["password"] == "pass"
        assert "user" not in kwargs["proxy"]["server"]


class TestIsSocksProxy:
    def test_socks5_string(self):
        assert _is_socks_proxy("socks5://user:pass@host:1080") is True

    def test_socks5h_string(self):
        assert _is_socks_proxy("socks5h://host:1080") is True

    def test_socks5_uppercase(self):
        assert _is_socks_proxy("SOCKS5://host:1080") is True

    def test_http_string(self):
        assert _is_socks_proxy("http://host:8080") is False

    def test_dict_socks5(self):
        assert _is_socks_proxy({"server": "socks5://host:1080"}) is True

    def test_dict_http(self):
        assert _is_socks_proxy({"server": "http://host:8080"}) is False

    def test_none(self):
        assert _is_socks_proxy(None) is False


class TestResolveProxyConfig:
    def test_none(self):
        kwargs, args = _resolve_proxy_config(None)
        assert kwargs == {}
        assert args == []

    def test_http_string_returns_playwright_dict(self):
        kwargs, args = _resolve_proxy_config("http://user:pass@proxy:8080")
        assert "proxy" in kwargs
        assert kwargs["proxy"]["server"] == "http://proxy:8080"
        assert kwargs["proxy"]["username"] == "user"
        assert args == []

    def test_http_dict_passthrough(self):
        proxy = {"server": "http://proxy:8080", "bypass": ".example.com"}
        kwargs, args = _resolve_proxy_config(proxy)
        assert kwargs == {"proxy": proxy}
        assert args == []

    def test_socks5_string_returns_chrome_arg(self):
        kwargs, args = _resolve_proxy_config("socks5://user:pass@host:1080")
        assert kwargs == {}
        assert args == ["--proxy-server=socks5://user:pass@host:1080"]

    def test_socks5_no_auth_returns_chrome_arg(self):
        kwargs, args = _resolve_proxy_config("socks5://host:1080")
        assert kwargs == {}
        assert args == ["--proxy-server=socks5://host:1080"]

    def test_socks5h_returns_chrome_arg(self):
        kwargs, args = _resolve_proxy_config("socks5h://user:pass@host:1080")
        assert kwargs == {}
        assert args == ["--proxy-server=socks5h://user:pass@host:1080"]

    def test_socks5_dict_reconstructs_url(self):
        proxy = {"server": "socks5://host:1080", "username": "user", "password": "p@ss"}
        kwargs, args = _resolve_proxy_config(proxy)
        assert kwargs == {}
        assert len(args) == 1
        assert args[0].startswith("--proxy-server=socks5://user:p%40ss@host:1080")

    def test_socks5_dict_ipv6_preserves_brackets(self):
        proxy = {"server": "socks5://[::1]:1080", "username": "user", "password": "pass"}
        kwargs, args = _resolve_proxy_config(proxy)
        assert kwargs == {}
        assert "[::1]" in args[0]

    def test_socks5_dict_with_bypass(self):
        proxy = {"server": "socks5://host:1080", "bypass": ".example.com"}
        kwargs, args = _resolve_proxy_config(proxy)
        assert kwargs == {}
        assert "--proxy-server=socks5://host:1080" in args
        assert "--proxy-bypass-list=.example.com" in args
