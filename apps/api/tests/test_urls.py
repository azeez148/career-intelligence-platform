import socket

import pytest

from app.core.urls import source_url


@pytest.mark.parametrize(
    "value,expected",
    [
        ("HTTPS://EXAMPLE.COM:443", "https://example.com/"),
        ("http://example.com.:80/jobs?b=2&a=1", "http://example.com/jobs?b=2&a=1"),
        ("https://bücher.de/Jobs?q=C%2B%2B", "https://xn--bcher-kva.de/Jobs?q=C%2B%2B"),
        ("https://example.com/職業", "https://example.com/%E8%81%B7%E6%A5%AD"),
        ("https://sub.example.com/Careers/a%2Fb", "https://sub.example.com/Careers/a%2Fb"),
    ],
)
def test_canonical_urls_without_network(value, expected, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("URL validation must not resolve DNS")

    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    assert source_url(value) == expected
    assert source_url(expected) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "example.com",
        "//example.com/jobs",
        "file:///etc/passwd",
        "ftp://example.com",
        "javascript:alert(1)",
        "https:///jobs",
        "https://user:password@example.com",
        "https://@example.com",
        "https://example.com/#jobs",
        "https://example.com:8443",
        "http://example.com:443",
        "https://example.com:",
        "https://example.com:invalid",
        "https://127.0.0.1",
        "https://127.1",
        "https://2130706433",
        "https://0x7f000001",
        "https://0177.0.0.1",
        "https://127.0.0.0x1",
        "https://[::1]",
        "https://[::ffff:127.0.0.1]",
        "https://[2606:4700:4700::1111]",
        "https://localhost",
        "https://localhost.",
        "https://nested.localhost",
        "https://server.local",
        "https://server.internal",
        "https://server.test",
        "https://server.invalid",
        "https://server.home",
        "https://host",
        "https://example..com",
        "https://-host.com",
        "https://host_.com",
        "https://example.com..",
        "https://example%2ecom",
        "https://example.com\\@local",
        " https://example.com",
        "https://example.com/with space",
        "https://example.com/\n",
        "https://example.com/%0a",
        "https://example.com/%7F",
        "https://example.com/%5c",
        "https://example.com/%zz",
        "https://example.com/%",
        "https://example.com/" + "a" * 2048,
    ],
)
def test_rejected_urls(value):
    with pytest.raises(ValueError):
        source_url(value)


@pytest.mark.parametrize(
    "value", ["https://router.home.arpa", "https://hidden.onion", "https://xn--a.com"]
)
def test_special_use_and_invalid_idna(value):
    with pytest.raises(ValueError):
        source_url(value)


def test_company_name_bound_applies_after_whitespace_normalization():
    from pydantic import ValidationError

    from app.modules.companies.schemas import CompanyInput

    assert CompanyInput(name=" " * 200 + "Name").name == "Name"
    for value in ("x" * 201, "   ", 123):
        with pytest.raises(ValidationError):
            CompanyInput(name=value)
