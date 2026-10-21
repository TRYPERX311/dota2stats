"""Smoke-тесты: проверяют, что ключевые модули импортируются без ошибок."""


def test_utils_imports():
    """utils.py должен импортироваться без ошибок."""
    import utils
    assert utils is not None


def test_ranks_imports():
    """ranks.py должен импортироваться без ошибок."""
    import ranks
    assert ranks is not None


def test_heroes_imports():
    """heroes.py должен импортироваться без ошибок."""
    import heroes
    assert heroes is not None