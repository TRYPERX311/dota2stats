import pytest
from heroes import get_hero_name, get_hero_image_url


@pytest.mark.parametrize(
    "hero_id, expected_name",
    [
        # Невалидные ID (граница 0 и отрицательный)
        (0, "Unknown (0)"),
        (-1, "Unknown (-1)"),
        (9999, "Unknown (9999)"),

        # Валидные ID (первый, второй и последний в твоем JSON)
        (1, "Anti-Mage"),
        (2, "Axe"),
        (155, "Largo"),
    ]
)
def test_hero_name(hero_id, expected_name):
    assert get_hero_name(hero_id) == expected_name


def test_get_hero_image_url_invalid_returns_none():
    assert get_hero_image_url(0) is None
    assert get_hero_image_url(9999) is None


def test_get_hero_image_url_valid_returns_string():
    url = get_hero_image_url(1)

    assert url is not None
    assert "antimage.png" in url