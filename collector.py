"""
Сбор статистики через OpenDota API.

Логика на одного пользователя:
1. Профиль: rank_tier, mmr_estimate.
2. Агрегаты за всё время: wl (win/lose), totals (kills/deaths/assists), heroes.
3. Последние 20 матчей — для "recent" статистики.
4. Матчи за текущий патч (limit=500 + фильтр по дате) — детали
   дотягиваются только для тех, кого ещё нет в БД.
5. Агрегация и сохранение.
"""

import time
from datetime import datetime, timezone

import db
import opendota
from positions import lane_role_to_position


# Сколько последних матчей считаем "recent"
RECENT_LIMIT = 20
# Сколько матчей тянуть за патч
PATCH_MATCH_LIMIT = 200
# Сколько запросов деталей матчей в минуту (чтобы не влететь в rate limit)
DETAILS_THROTTLE_SEC = 1.1
PEERS_LIMIT = 5


# ============================================================
# УТИЛИТЫ
# ============================================================

def _ts_to_dt(ts: int | None) -> datetime | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)


def _wl_from_match(m: dict, account_id: int) -> int | None:
    """
    Определяет win/lose для конкретного матча.
    Возвращает 1 = победа, 0 = поражение, None = не удалось.
    """
    radiant_win = m.get("radiant_win")
    player_slot = m.get("player_slot")
    if radiant_win is None or player_slot is None:
        return None
    is_radiant = player_slot < 128
    return 1 if (radiant_win and is_radiant) or (not radiant_win and not is_radiant) else 0


# ============================================================
# ПАТЧИ
# ============================================================

def sync_patches() -> int | None:
    """
    Обновляет справочник патчей. Возвращает id текущего патча или None.
    """
    patches_raw = opendota.fetch_patches()
    if not patches_raw:
        print("[collector] Не удалось получить список патчей")
        return None

    patches = []
    for p in patches_raw:
        pid = p.get("id")
        name = p.get("name")
        date = p.get("date")
        if not pid or not name or not date:
            continue
        try:
            released = datetime.fromisoformat(date.replace("Z", "+00:00"))
            released = released.replace(tzinfo=None)
        except ValueError:
            continue
        patches.append({"id": pid, "name": name, "released_at": released})

    if not patches:
        return None

    db.upsert_patches(patches)

    current = db.get_current_patch()
    if current:
        print(f"[collector] Текущий патч: {current.name} (id={current.id}, {current.released_at.date()})")
        return current.id
    return None


# ============================================================
# СБОР ПОЛЬЗОВАТЕЛЯ
# ============================================================

def collect_profile(user_id: int, account_id: int) -> dict:
    """Профиль: ранг, MMR. Возвращает поля для PlayerStats."""
    profile = opendota.fetch_player(account_id)
    if not profile:
        return {}
    return {
        "rank_tier": profile.get("rank_tier"),
        "mmr_estimate": profile.get("mmr_estimate"),
    }


def collect_all_time_stats(user_id: int, account_id: int) -> dict:
    """Агрегаты за всё время: wl, totals (KDA), игры по позициям из matches."""
    fields: dict = {}

    wl = opendota.fetch_wl(account_id)
    if wl:
        wins = wl.get("win") or 0
        losses = wl.get("lose") or 0
        fields["wins_total"] = wins
        fields["losses_total"] = losses
        fields["games_total"] = wins + losses

    totals = opendota.fetch_totals(account_id)
    if totals:
        sum_map = {t["field"]: t.get("sum") or 0 for t in totals if "field" in t}
        n_map = {t["field"]: t.get("n") or 0 for t in totals if "field" in t}

        kills_sum = sum_map.get("kills", 0)
        deaths_sum = sum_map.get("deaths", 0)
        assists_sum = sum_map.get("assists", 0)
        n = n_map.get("kills") or n_map.get("deaths") or n_map.get("assists") or 0

        if n:
            avg_kills = kills_sum / n
            avg_deaths = deaths_sum / n
            avg_assists = assists_sum / n
            avg_kda = (kills_sum + assists_sum) / deaths_sum if deaths_sum else float(kills_sum + assists_sum)

            fields["avg_kills"] = int(round(avg_kills * 100))
            fields["avg_deaths"] = int(round(avg_deaths * 100))
            fields["avg_assists"] = int(round(avg_assists * 100))
            fields["avg_kda"] = int(round(avg_kda * 100))

    return fields


def collect_hero_stats_all_time(user_id: int, account_id: int) -> int:
    """
    Топ героев за всё время. Сохраняет в HeroStats (patch_id=0, position='').
    Возвращает число героев.
    """
    heroes_raw = opendota.fetch_hero_stats(account_id)
    if not heroes_raw:
        return 0

    rows = []
    for h in heroes_raw:
        hero_id = h.get("hero_id")
        games = h.get("games") or 0
        wins = h.get("win") or 0
        if not hero_id or not games:
            continue
        rows.append({"hero_id": hero_id, "games": games, "wins": wins})

    db.replace_hero_stats(user_id, patch_id=0, position="", heroes=rows)
    return len(rows)


def collect_recent(user_id: int, account_id: int) -> dict:
    """
    Последние RECENT_LIMIT матчей: считает games_recent / wins_recent.
    Не трогает детали (kda) — для этого есть патч.
    """
    matches = opendota.fetch_recent_matches(account_id, limit=RECENT_LIMIT)
    if not matches:
        return {}

    games = 0
    wins = 0
    last_ts = None

    for m in matches:
        w = _wl_from_match(m, account_id)
        if w is None:
            continue
        games += 1
        wins += w
        ts = m.get("start_time")
        if ts and (last_ts is None or ts > last_ts):
            last_ts = ts

    fields = {
        "games_recent": games,
        "wins_recent": wins,
    }
    if last_ts:
        fields["last_match_at"] = _ts_to_dt(last_ts)
    return fields


def collect_patch_matches(user_id: int, account_id: int, patch_id: int, patch_dt: datetime) -> dict:
    """
    Матчи за текущий патч:
    1. Тянем список матчей (limit=500), фильтруем по дате.
    2. Для тех, чьих деталей нет в БД, тянем /matches/{id} (с троттлингом).
    3. Сохраняем/обновляем Match.
    4. Считаем агрегаты по патчу: hero_stats и позиции.

    Возвращает поля для PlayerStats (games_carry/wins_carry/...), посчитанные
    по данным за патч.
    """
    since_ts = int(patch_dt.replace(tzinfo=timezone.utc).timestamp())
    matches_raw = opendota.fetch_matches_for_patch(
        account_id, since_ts=since_ts, limit=PATCH_MATCH_LIMIT
    )
    if not matches_raw:
        print(f"[collector] Нет матчей за патч для account_id={account_id}")
        return {}

    existing_ids = db.get_existing_match_ids(user_id)

    # Куда складывать новые детали, а куда — базовые строки без деталей
    new_matches: list[dict] = []
    detail_match_ids: list[int] = []

    for m in matches_raw:
        match_id = m.get("match_id")
        if not match_id:
            continue
        w = _wl_from_match(m, account_id)
        if w is None:
            continue

        base = {
            "match_id": match_id,
            "hero_id": m.get("hero_id"),
            "win": w,
            "duration": m.get("duration"),
            "played_at": _ts_to_dt(m.get("start_time")),
            "patch_id": patch_id,
        }

        if match_id in existing_ids:
            # Уже есть — возможно, без деталей. Тянем детали, если не заполнены.
            continue
        new_matches.append(base)
        detail_match_ids.append(match_id)

    # Вставляем базовые строки
    inserted = db.insert_matches(user_id, new_matches)
    print(f"[collector] [{account_id}] Новых базовых матчей: {inserted}")

    # Дотягиваем детали для вставленных
    detailed = 0
    for match_id in detail_match_ids:
        detail = opendota.fetch_match_detail(match_id)
        if not detail:
            time.sleep(DETAILS_THROTTLE_SEC)
            continue

        player = None
        for p in detail.get("players") or []:
            if p.get("account_id") == account_id:
                player = p
                break

        if not player:
            time.sleep(DETAILS_THROTTLE_SEC)
            continue

        lane_role = player.get("lane_role")
        details_update = {
            "kills": player.get("kills"),
            "deaths": player.get("deaths"),
            "assists": player.get("assists"),
            "lane_role": lane_role,
            "position": lane_role_to_position(lane_role),
            "gold_per_min": player.get("gold_per_min"),
            "xp_per_min": player.get("xp_per_min"),
        }
        # Если в деталях есть patch — уточняем
        if detail.get("patch"):
            details_update["patch_id"] = detail["patch"]

        db.update_match_details(user_id, match_id, details_update)
        detailed += 1
        time.sleep(DETAILS_THROTTLE_SEC)

    print(f"[collector] [{account_id}] Загружено деталей: {detailed}")

    # Агрегируем из БД: hero_stats + позиции за патч
    return _aggregate_patch(user_id, patch_id)


def _aggregate_patch(user_id: int, patch_id: int) -> dict:
    """
    Считает по матчам пользователя за патч:
    - hero_stats (patch_id, position='')
    - hero_stats по позициям (patch_id, position=carry/mid/offlane/support)
    - games_carry/wins_carry/... для PlayerStats
    """
    matches = db.get_user_matches_by_patch(user_id, patch_id, limit=1000)

    if not matches:
        return {}

    # Все герои за патч
    hero_all: dict[int, dict] = {}
    # Герои по позициям
    hero_by_pos: dict[str, dict[int, dict]] = {}
    # Счётчики по позициям
    pos_games: dict[str, int] = {"carry": 0, "mid": 0, "offlane": 0, "support": 0}
    pos_wins: dict[str, int] = {"carry": 0, "mid": 0, "offlane": 0, "support": 0}

    for m in matches:
        # Все герои
        h = hero_all.setdefault(m.hero_id, {"hero_id": m.hero_id, "games": 0, "wins": 0})
        h["games"] += 1
        h["wins"] += m.win

        # По позиции
        pos = m.position
        if pos in pos_games:
            pos_games[pos] += 1
            pos_wins[pos] += m.win
            bucket = hero_by_pos.setdefault(pos, {})
            hp = bucket.setdefault(m.hero_id, {"hero_id": m.hero_id, "games": 0, "wins": 0})
            hp["games"] += 1
            hp["wins"] += m.win

    # Сохраняем "все герои за патч"
    heroes_sorted = sorted(hero_all.values(), key=lambda x: x["games"], reverse=True)
    db.replace_hero_stats(user_id, patch_id=patch_id, position="", heroes=heroes_sorted)

    # Сохраняем "герои по позициям за патч"
    for pos in ("carry", "mid", "offlane", "support"):
        bucket = hero_by_pos.get(pos)
        if not bucket:
            db.replace_hero_stats(user_id, patch_id=patch_id, position=pos, heroes=[])
            continue
        rows = sorted(bucket.values(), key=lambda x: x["games"], reverse=True)
        db.replace_hero_stats(user_id, patch_id=patch_id, position=pos, heroes=rows)

    # Возвращаем поля для PlayerStats
    return {
        "games_carry": pos_games["carry"],
        "wins_carry": pos_wins["carry"],
        "games_mid": pos_games["mid"],
        "wins_mid": pos_wins["mid"],
        "games_offlane": pos_games["offlane"],
        "wins_offlane": pos_wins["offlane"],
        "games_support": pos_games["support"],
        "wins_support": pos_wins["support"],
    }


# ============================================================
# ГЛАВНАЯ ФУНКЦИЯ НА ПОЛЬЗОВАТЕЛЯ
# ============================================================
def collect_peers(user_id: int, account_id: int) -> int:
    """
    Топ-5 сокомандников. Для каждого подтягивает ник и аватар.
    Возвращает число сохранённых.
    """
    raw = opendota.fetch_peers(account_id)
    if not raw:
        return 0

    # Сортируем по числу совместных игр, берём топ-5
    sorted_peers = sorted(
        raw,
        key=lambda p: p.get("with_games") or 0,
        reverse=True,
    )[:PEERS_LIMIT]

    rows = []
    for p in sorted_peers:
        peer_account_id = p.get("account_id")
        if not peer_account_id:
            continue

        profile = opendota.fetch_player(peer_account_id)
        rows.append({
            "peer_account_id": peer_account_id,
            "peer_nickname": (profile or {}).get("personaname"),
            "peer_avatar": (profile or {}).get("avatarfull"),
            "with_games": p.get("with_games") or 0,
            "with_win": p.get("with_win") or 0,
            "last_played": _ts_to_dt(p.get("last_played")),
        })

    db.replace_peers(user_id, rows)
    print(f"[collector] [{account_id}] Сокомандников: {len(rows)}")
    return len(rows)

def collect_for_user(user, current_patch_id: int | None, current_patch_dt: datetime | None):
    print(f"[collector] === {user.nickname} (account_id={user.account_id}) ===")

    stats_fields: dict = {}

    # 1. Профиль
    stats_fields.update(collect_profile(user.id, user.account_id))

    # 2. За всё время
    stats_fields.update(collect_all_time_stats(user.id, user.account_id))
    heroes_count = collect_hero_stats_all_time(user.id, user.account_id)
    print(f"[collector] [{user.account_id}] Героев за всё время: {heroes_count}")

    # 3. Последние 20
    stats_fields.update(collect_recent(user.id, user.account_id))
    collect_peers(user.id, user.account_id)

    # 4. За текущий патч
    if current_patch_id and current_patch_dt:
        patch_fields = collect_patch_matches(
            user.id, user.account_id, current_patch_id, current_patch_dt
        )
        stats_fields.update(patch_fields)

    # 5. Сохраняем PlayerStats
    if stats_fields:
        db.upsert_player_stats(user.id, stats_fields)

    db.update_last_updated(user.id)
    print(f"[collector] === {user.nickname}: готово ===")


# ============================================================
# ЗАПУСК
# ============================================================

def run():
    print(f"[collector] Старт сбора: {datetime.now(timezone.utc)}")

    # Синхронизируем патчи
    current_patch_id = sync_patches()
    current_patch = db.get_current_patch()
    current_patch_dt = current_patch.released_at if current_patch else None

    users = db.get_all_users()
    print(f"[collector] Пользователей в БД: {len(users)}")

    for i, user in enumerate(users):
        try:
            collect_for_user(user, current_patch_id, current_patch_dt)
        except Exception as e:
            print(f"[collector] Ошибка для {user.nickname}: {e}")
            import traceback
            traceback.print_exc()
        # Пауза между пользователями
        if i < len(users) - 1:
            time.sleep(2.0)

    print(f"[collector] Завершено: {datetime.now(timezone.utc)}")


if __name__ == "__main__":
    run()