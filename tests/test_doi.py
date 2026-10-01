import pytest

from paperflow.utils.doi import (
    is_valid_doi,
    normalize_doi,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "10.1016/j.buildenv.2025.113229",
            "10.1016/j.buildenv.2025.113229",
        ),
        (
            " DOI:10.1016/J.BUILDENV.2025.113229 ",
            "10.1016/j.buildenv.2025.113229",
        ),
        (
            "https://doi.org/10.1007/s12273-026-1484-2",
            "10.1007/s12273-026-1484-2",
        ),
        (
            "http://dx.doi.org/10.1007/s12273-026-1484-2",
            "10.1007/s12273-026-1484-2",
        ),
        (
            "<https://doi.org/10.1016/j.buildenv.2026.114205>",
            "10.1016/j.buildenv.2026.114205",
        ),
    ],
)
def test_normalize_doi(raw, expected):
    assert normalize_doi(raw) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "hello",
        "10.123",
        "https://example.com/10.1007/test",
        "not-a-doi",
    ],
)
def test_invalid_doi_raises(value):
    with pytest.raises(ValueError):
        normalize_doi(value)


def test_is_valid_doi():
    assert is_valid_doi("10.1007/s12273-026-1484-2")

    assert not is_valid_doi("not-a-doi")
