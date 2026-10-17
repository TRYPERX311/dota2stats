"""Чистые утилиты: конвертация времени, определение победы/поражения."""
from datetime import datetime, timezone

# ============================================================
# УТИЛИТЫ
# ============================================================

def ts_to_dt(ts: int | None) -> datetime | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)


def wl_from_match(m: dict, account_id: int) -> int | None:
    radiant_win = m.get("radiant_win")
    player_slot = m.get("player_slot")
    if radiant_win is None or player_slot is None:
        return None
    is_radiant = player_slot < 128
    return 1 if (radiant_win and is_radiant) or (not radiant_win and not is_radiant) else 0

