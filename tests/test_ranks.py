import pytest

from ranks import rank_to_str


@pytest.mark.parametrize(
    "rank_tier,  expected",
    [
        (-100, "Unknown"),
        (-1, "Unknown"),
        (0, "Calibrating"),
        (None, "Calibrating"),
        (5, "Unknown"),
        (10, "Unknown"),
        (11, "Herald 1"),
        (15, "Herald 5"),
        (16, "Unknown"),
        (53, "Legend 3"),
        (70, "Unknown"),
        (75, "Divine 5"),
        (76, "Unknown"),
        (80, "Immortal"),
        (86, "Immortal"),
        (90, "Unknown"),
        (128, "Unknown")
    ]
)
def test_rank_to_str_returns_expected(rank_tier, expected):
    assert rank_to_str(rank_tier) == expected
