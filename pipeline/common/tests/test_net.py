"""`assert_public_url` keeps fetches out of the deployment's private network."""

import pytest

from pipeline.common.errors import StageError
from pipeline.common.net import assert_public_url


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8001/health",
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://10.1.2.3/admin",
        "http://169.254.169.254/latest/meta-data",
        "http://[::ffff:192.168.0.1]/",
        "ftp://93.184.216.34/file",
        "https:///no-host",
    ],
)
def test_private_and_non_http_targets_are_refused(url: str) -> None:
    with pytest.raises(StageError):
        assert_public_url(url)


def test_public_addresses_pass() -> None:
    assert_public_url("https://93.184.216.34/article")
    assert_public_url("http://[2606:2800:220:1:248:1893:25c8:1946]/")
