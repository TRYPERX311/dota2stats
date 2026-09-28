import time
import requests
from datetime import datetime, timezone

import config
import db


STEAM_MATCH_HISTORY_URL = "https://api.steampowered.com/IDOTA2Match_570/GetMatchHistory/V001/"


def fetch_matches(account_id: int, count: int = 100) -> list:
    params = {
        "key": config.STEAM_API_KEY,
        "account_id": account_id,
        "matches_requested": count,
    }
    try:
        r = requests.get(STEAM_MATCH_HISTORY_URL, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        print(f"[collector] Ошибка запроса для account_id={account_id}: {e}")
        return []

    matches_raw = data.get("result", {}).get("matches", [])
    result = []

    for m in matches_raw:
        match_id = m.get("match_id")
        duration = m.get("duration")
        start_time = m.get("start_time")

        player = None
        for p in m.get("players", []):
            if p.get("account_id") == account_id:
                player = p
                break
        if not player:
            continue

        hero_id = player.get("hero_id")
        player_slot = player.get("player_slot", 0)
        radiant_win = m.get("radiant_win")

        is_radiant = player_slot < 128
        win = 1 if (radiant_win and is_radiant) or (not radiant_win and not is_radiant) else 0

        result.append({
            "match_id": match_id,
            "hero_id": hero_id,
            "win": win,
            "duration": duration,
            "played_at": datetime.fromtimestamp(start_time, tz=timezone.utc).replace(tzinfo=None) if start_time else None,
        })

    return result


def recalc_player_stats(user_id: int):
    matches = db.get_user_matches(user_id, limit=1000)
    if not matches:
        return

    games_total = len(matches)
    wins_total = sum(m.win for m in matches)

    recent = matches[:100]
    games_recent = len(recent)
    wins_recent = sum(m.win for m in recent)

    db.upsert_player_stats(user_id, games_total, wins_total, games_recent, wins_recent)

    hero_agg = {}
    for m in matches:
        h = hero_agg.setdefault(m.hero_id, {"hero_id": m.hero_id, "games": 0, "wins": 0})
        h["games"] += 1
        h["wins"] += m.win

    heroes_sorted = sorted(hero_agg.values(), key=lambda x: x["games"], reverse=True)
    db.replace_hero_stats(user_id, heroes_sorted)


def collect_for_user(user):
    print(f"[collector] Обрабатываю {user.nickname} (account_id={user.account_id})")

    matches = fetch_matches(user.account_id, count=100)
    if not matches:
        print(f"[collector] Матчей не найдено для {user.nickname}")
        return

    inserted = db.insert_matches(user.id, matches)
    print(f"[collector] Добавлено новых матчей: {inserted}")

    recalc_player_stats(user.id)
    db.update_last_updated(user.id)


def run():
    print(f"[collector] Старт сбора: {datetime.now(timezone.utc)}")

    users = db.get_all_users()
    print(f"[collector] Пользователей в БД: {len(users)}")

    for user in users:
        collect_for_user(user)
        time.sleep(1.5)

    print(f"[collector] Завершено: {datetime.now(timezone.utc)}")


if __name__ == "__main__":
    run()