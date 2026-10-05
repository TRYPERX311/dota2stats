"""
Клиент OpenDota API.

Особенности:
- Кэш в памяти с TTL (чтобы не бить по API дважды).
- Retry при 429 (rate limit) и 5xx.
- Без API-ключа (анонимный доступ, 60 req/min, 2000 req/day).
"""

import time
import threading
from typing import Any

import requests


OPENDOTA_BASE = "https://api.opendota.com/api"
TIMEOUT = 20
MAX_RETRIES = 3
RETRY_DELAY = 2.0   # секунды, умножается на номер попытки (exponential-ish)


# ============================================================
# КЭШ В ПАМЯТИ
# ============================================================

_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_LOCK = threading.Lock()


def _cache_get(key: str, ttl: int) -> Any | None:
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
        if not entry:
            return None
        expires_at, value = entry
        if time.time() >= expires_at:
            _CACHE.pop(key, None)
            return None
        return value


def _cache_set(key: str, value: Any, ttl: int) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = (time.time() + ttl, value)


# ============================================================
# БАЗОВЫЙ GET С RETRY
# ============================================================

def _get(path: str, params: dict | None = None, ttl: int = 300) -> Any | None:
    """
    Делает GET-запрос к OpenDota.

    - ttl: сколько секунд держать ответ в кэше. Для статики (патчи, герои) — большие,
      для динамики (матчи, профиль) — маленькие.
    - Возвращает распарсенный JSON или None при неудаче.
    """
    key = path
    if params:
        # Стабильный ключ кэша
        items = sorted(params.items())
        key = f"{path}?{items}"

    cached = _cache_get(key, ttl)
    if cached is not None:
        return cached

    url = f"{OPENDOTA_BASE}{path}"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, params=params, timeout=TIMEOUT)
        except requests.RequestException as e:
            print(f"[opendota] Сетевая ошибка {path}: {e} (попытка {attempt})")
            time.sleep(RETRY_DELAY * attempt)
            continue

        if r.status_code == 200:
            try:
                data = r.json()
            except ValueError:
                print(f"[opendota] Некорректный JSON для {path}")
                return None
            _cache_set(key, data, ttl)
            return data

        if r.status_code == 429:
            retry_after = float(r.headers.get("Retry-After", RETRY_DELAY * attempt))
            print(f"[opendota] 429 Rate limit, ждём {retry_after}с")
            time.sleep(retry_after)
            continue

        if 500 <= r.status_code < 600:
            print(f"[opendota] {r.status_code} для {path}, попытка {attempt}")
            time.sleep(RETRY_DELAY * attempt)
            continue

        # 4xx — обычно нечего ретраить
        print(f"[opendota] HTTP {r.status_code} для {path}: {r.text[:200]}")
        return None

    print(f"[opendota] Исчерпаны попытки для {path}")
    return None


# ============================================================
# ПУБЛИЧНЫЕ ФУНКЦИИ
# ============================================================

def fetch_player(account_id: int) -> dict | None:
    """Профиль игрока: ранг, MMR-оценка, ник, аватар."""
    data = _get(f"/players/{account_id}", ttl=600)
    if not data:
        return None
    return {
        "rank_tier": data.get("rank_tier"),
        "leaderboard_rank": data.get("leaderboard_rank"),
        "mmr_estimate": (data.get("mmr_estimate") or {}).get("estimate"),
        "personaname": (data.get("profile") or {}).get("personaname"),
        "avatarfull": (data.get("profile") or {}).get("avatarfull"),
    }


def fetch_wl(account_id: int) -> dict | None:
    """Победы/поражения за всё время."""
    return _get(f"/players/{account_id}/wl", ttl=600)


def fetch_totals(account_id: int) -> list | None:
    """Агрегаты за всё время: суммарные kills/deaths/assists и т.д."""
    return _get(f"/players/{account_id}/totals", ttl=600)


def fetch_hero_stats(account_id: int) -> list | None:
    """Агрегат по героям за всё время: [{hero_id, games, win}, ...]."""
    return _get(f"/players/{account_id}/heroes", ttl=600)


def fetch_recent_matches(account_id: int, limit: int = 20) -> list | None:
    """Последние матчи (без KDA — только match_id, hero_id, win, duration, start_time)."""
    return _get(f"/players/{account_id}/matches", params={"limit": limit}, ttl=120)


def fetch_matches_for_patch(account_id: int, since_ts: int, limit: int = 200) -> list | None:
    """
    Матчи после указанного timestamp (для фильтра по патчу).
    OpenDota не поддерживает 'since' напрямую для /matches,
    поэтому берём limit=500 и фильтруем на нашей стороне.
    """
    data = _get(f"/players/{account_id}/matches", params={"limit": 500}, ttl=300)
    if not data:
        return None
    return [m for m in data if (m.get("start_time") or 0) >= since_ts][:limit]


def fetch_match_detail(match_id: int) -> dict | None:
    """
    Детали матча: KDA, lane_role, patch, GPM/XPM и т.д.
    Кэш на сутки — матчи не меняются.
    """
    data = _get(f"/matches/{match_id}", ttl=86400)
    if not data:
        return None
    return {
        "match_id": data.get("match_id"),
        "patch": data.get("patch"),
        "duration": data.get("duration"),
        "start_time": data.get("start_time"),
        "radiant_win": data.get("radiant_win"),
        "players": [
            {
                "account_id": p.get("account_id"),
                "player_slot": p.get("player_slot"),
                "hero_id": p.get("hero_id"),
                "kills": p.get("kills"),
                "deaths": p.get("deaths"),
                "assists": p.get("assists"),
                "lane_role": p.get("lane_role"),
                "gold_per_min": p.get("gold_per_min"),
                "xp_per_min": p.get("xp_per_min"),
            }
            for p in (data.get("players") or [])
        ],
    }


def fetch_patches() -> list | None:
    """
    Справочник патчей. Кэш на сутки — патчи меняются раз в несколько недель.
    Возвращает [{id, name, date}, ...] отсортированный по дате.
    """
    data = _get("/constants/patch", ttl=86400)
    if not data:
        return None
    return sorted(data, key=lambda p: p.get("date") or "")