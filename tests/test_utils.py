import pytest
from utils import wl_from_match

@pytest.mark.parametrize(
    "match, expected",
    [
        # Классы эквивалентности
        ({}, None),                                           # пустой словарь
        ({"radiant_win": True}, None),                        # нет player_slot
        ({"player_slot": 0}, None),                           # нет radiant_win
        ({"radiant_win": True, "player_slot": 0}, 1),         # Radiant победил, игрок Radiant
        ({"radiant_win": True, "player_slot": 128}, 0),       # Radiant победил, игрок Dire
        ({"radiant_win": False, "player_slot": 0}, 0),        # Dire победил, игрок Radiant
        ({"radiant_win": False, "player_slot": 128}, 1),      # Dire победил, игрок Dire

        # Граничные значения player_slot
        ({"radiant_win": True, "player_slot": 0}, 1),         # первый Radiant
        ({"radiant_win": True, "player_slot": 127}, 1),       # последний Radiant
        ({"radiant_win": True, "player_slot": 128}, 0),       # первый Dire
        ({"radiant_win": True, "player_slot": 255}, 0),       # последний Dire
    ],
)
def test_wl_from_match_returns_expected(match, expected):
    assert wl_from_match(match, account_id=1) == expected

def test_wl_from_match_account_id_not_used():
    match = {"radiant_win": True, "player_slot": 0}
    assert wl_from_match(match, account_id=1) == 1
    assert wl_from_match(match, account_id=999) == 1
    assert wl_from_match(match, account_id=0) == 1