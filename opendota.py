"""
Клиент OpenDota API.

Особенности:
- Кэш в памяти с TTL (чтобы не бить по API дважды).
- Retry при 429 (rate limit) и 5xx.
- Без API-ключа (анонимный доступ, 60 req/min, 2000 req/day).
- Принудительно используется IPv4 (см. _force_ipv4).
"""

import time
import threading
import socket
from typing import Any

import requests
import requests.packages.urllib3.util.connection as urllib3_cn


# Форсируем IPv4 для всех запросов requests.
# Иначе в Docker контейнере DNS может вернуть только IPv6 (Cloudflare),
# и запросы зависают в таймаут, если IPv6 не работает.
def _force_ipv4():
    urllib3_cn.allowed_gai_family = lambda: socket.AF_INET


_force_ipv4()


OPENDOTA_BASE = "https://api.opendota.com/api"
TIMEOUT = 20
MAX_RETRIES = 3
RETRY_DELAY = 2.0


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
    key = path
    if params:
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

        print(f"[opendota] HTTP {r.status_code} для {path}: {r.text[:200]}")
        return None

    print(f"[opendota] Исчерпаны попытки для {path}")
    return None


# ============================================================
# ПУБЛИЧНЫЕ ФУНКЦИИ
# ============================================================

def fetch_player(account_id: int) -> dict | None:
    """Профиль игрока: ранг, MMR, ник, аватар."""
    data = _get(f"/players/{account_id}", ttl=600)
    if not data:
        return None
    return {
        "rank_tier": data.get("rank_tier"),
        "leaderboard_rank": data.get("leaderboard_rank"),
        "mmr_estimate": data.get("computed_mmr") or (data.get("mmr_estimate") or {}).get("estimate"),
        "personaname": (data.get("profile") or {}).get("personaname"),
        "avatarfull": (data.get("profile") or {}).get("avatarfull"),
    }


def fetch_wl(account_id: int) -> dict | None:
    return _get(f"/players/{account_id}/wl", ttl=600)


def fetch_totals(account_id: int) -> list | None:
    return _get(f"/players/{account_id}/totals", ttl=600)


def fetch_hero_stats(account_id: int) -> list | None:
    return _get(f"/players/{account_id}/heroes", ttl=600)


def fetch_recent_matches(account_id: int, limit: int = 20) -> list | None:
    return _get(f"/players/{account_id}/matches", params={"limit": limit}, ttl=120)


def fetch_matches_for_patch(account_id: int, since_ts: int, limit: int = 200) -> list | None:
    data = _get(f"/players/{account_id}/matches", params={"limit": 500}, ttl=300)
    if not data:
        return None
    return [m for m in data if (m.get("start_time") or 0) >= since_ts][:limit]


def fetch_match_detail(match_id: int) -> dict | None:
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
    data = _get("/constants/patch", ttl=86400)
    if not data:
        return None
    return sorted(data, key=lambda p: p.get("date") or "")