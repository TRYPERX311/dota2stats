from datetime import datetime
import pytest
from utils import winrate, wl_from_match, ts_to_dt


@pytest.mark.parametrize(
    "wins, games, expected",
    [
        # Классы эквивалентности
        (0, 0, 0.0),  # нет игр
        (0, 10, 0.0),  # все поражения
        (10, 10, 100.0),  # все победы
        (5, 10, 50.0),  # половина
        (1, 3, 33.33),  # округление
        (2, 3, 66.67),  # округление
        (11, 10, 110.0),  # аномалия (wins > games)

        # Граничные значения
        (0, 1, 0.0),  # минимум игр
        (1, 1, 100.0),  # максимум при 1 игре
        (100, 100, 100.0),  # большое значение
        (1, 7, 14.29),  # округление до 2 знаков
        (1, 6, 16.67),  # округление
    ],
)
def test_winrate_returns_expected(wins, games, expected):
    assert winrate(wins, games) == expected


@pytest.mark.parametrize(
    "match, expected",
    [
        # Классы эквивалентности
        ({}, None),  # пустой словарь
        ({"radiant_win": True}, None),  # нет player_slot
        ({"player_slot": 0}, None),  # нет radiant_win
        ({"radiant_win": True, "player_slot": 0}, 1),  # Radiant победил, игрок Radiant
        ({"radiant_win": True, "player_slot": 128}, 0),  # Radiant победил, игрок Dire
        ({"radiant_win": False, "player_slot": 0}, 0),  # Dire победил, игрок Radiant
        ({"radiant_win": False, "player_slot": 128}, 1),  # Dire победил, игрок Dire

        # Граничные значения player_slot
        ({"radiant_win": True, "player_slot": 0}, 1),  # первый Radiant
        ({"radiant_win": True, "player_slot": 127}, 1),  # последний Radiant
        ({"radiant_win": True, "player_slot": 128}, 0),  # первый Dire
        ({"radiant_win": True, "player_slot": 255}, 0),  # последний Dire
    ],
)
def test_wl_from_match_returns_expected(match, expected):
    assert wl_from_match(match, account_id=1) == expected


def test_wl_from_match_account_id_not_used():
    match = {"radiant_win": True, "player_slot": 0}
    assert wl_from_match(match, account_id=1) == 1
    assert wl_from_match(match, account_id=999) == 1
    assert wl_from_match(match, account_id=0) == 1


@pytest.mark.parametrize(
    "ts, expected",
    [
        (None, None),  # пустой вход
        (0, None),  # нулевой вход (falsy)

        (1, datetime(1970, 1, 1, 0, 0, 1)),  # первая секунда Unix-эпохи
        (1700000000, datetime(2023, 11, 14, 22, 13, 20)),  # известная дата
        (946684800, datetime(2000, 1, 1, 0, 0, 0)),  # Y2K

        (-1, datetime(1969, 12, 31, 23, 59, 59)),

        (1, datetime(1970, 1, 1, 0, 0, 1)),  # минимум
        (9999999999, datetime(2286, 11, 20, 17, 46, 39)),  # очень большое
    ],
)


def test_ts_to_dt_returns_expected(ts, expected):
    assert ts_to_dt(ts) == expected


def test_ts_to_dt_is_utc_naive():
    """Функция должна возвращать naive datetime в UTC, без tzinfo."""
    result = ts_to_dt(1700000000)
    assert result is not None
    assert result.tzinfo is None  # naive
    # 1700000000 UTC = 2023-11-14 22:13:20 UTC
    assert result.year == 2023
    assert result.month == 11
    assert result.day == 14
    assert result.hour == 22
    assert result.minute == 13
    assert result.second == 20
