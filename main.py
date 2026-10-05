from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import RedirectResponse, FileResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
import threading

import config
import db
import steam_auth
import collector
from heroes import get_hero_name, get_hero_image_url
from positions import rank_to_str, POSITION_LABELS


app = FastAPI(title="Dota 2 Stats")

app.add_middleware(
    SessionMiddleware,
    secret_key=config.SECRET_KEY,
    session_cookie="session",
    same_site="lax",
    https_only=False,
)
app.mount("/static", StaticFiles(directory="static"), name="static")

db.init_db()


def _current_user_id(request: Request) -> int:
    """Возвращает user_id из сессии или 401, если не залогинен."""
    user_id = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=401, detail="not_authenticated")
    return int(user_id)


def _winrate(wins: int, games: int) -> float:
    return round(wins / games * 100, 2) if games else 0.0


def _kda(kills_sum: int, deaths_sum: int, assists_sum: int) -> float:
    """KDA = (kills + assists) / deaths, с защитой от деления на ноль."""
    if deaths_sum == 0:
        return float(kills_sum + assists_sum)
    return round((kills_sum + assists_sum) / deaths_sum, 2)


def _hero_rows_to_dict(rows, limit: int | None = None) -> list:
    """HeroStats-строки → список dict для ответа."""
    if limit is not None:
        rows = rows[:limit]
    result = []
    for h in rows:
        result.append({
            "hero_id": h.hero_id,
            "hero_name": get_hero_name(h.hero_id),
            "hero_image": get_hero_image_url(h.hero_id),
            "games": h.games,
            "wins": h.wins,
            "winrate": _winrate(h.wins, h.games),
        })
    return result


# ============================================================
# АВТОРИЗАЦИЯ
# ============================================================

@app.get("/")
def index():
    return FileResponse("templates/index.html")


@app.get("/login")
def login():
    return_to = f"{config.BASE_URL}/processlogin"
    url = steam_auth.get_login_url(return_to)
    return RedirectResponse(url)


@app.get("/processlogin")
def processlogin(request: Request):
    args = dict(request.query_params)
    steam_id64 = steam_auth.validate_steam_response(args)

    if not steam_id64:
        return JSONResponse({"error": "steam_auth_failed"}, status_code=401)

    user = db.get_user_by_steam_id(steam_id64)

    if not user:
        try:
            account_id = steam_auth.steam_id_to_account_id(steam_id64)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        profile = steam_auth.fetch_steam_profile(steam_id64)
        nickname = profile["nickname"] if profile else None
        avatar_url = profile["avatar_url"] if profile else None
        user = db.create_user(
            steam_id64=steam_id64,
            account_id=account_id,
            nickname=nickname,
            avatar_url=avatar_url,
        )
        # Нового пользователя — на сбор статистики в фоне
        threading.Thread(
            target=_collect_single_user_bg,
            args=(user.id,),
            daemon=True,
        ).start()
    else:
        profile = steam_auth.fetch_steam_profile(steam_id64)
        if profile:
            db.update_user_info(user.id, profile["nickname"], profile["avatar_url"])

    request.session["user_id"] = user.id
    return RedirectResponse("/")


def _collect_single_user_bg(user_id: int):
    """Собирает статистику одного пользователя в фоне (после логина)."""
    try:
        user = db.get_user_by_id(user_id)
        if not user:
            return
        current_patch_id = collector.sync_patches()
        current_patch = db.get_current_patch()
        current_patch_dt = current_patch.released_at if current_patch else None
        collector.collect_for_user(user, current_patch_id, current_patch_dt)
    except Exception as e:
        print(f"[main] Фоновый сбор для user_id={user_id} упал: {e}")


@app.get("/me")
def me(request: Request):
    user_id = _current_user_id(request)
    user = db.get_user_by_id(user_id)
    if not user:
        request.session.clear()
        raise HTTPException(status_code=401, detail="user_not_found")
    return user.to_dict()


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/")


# ============================================================
# API: ПОЛЬЗОВАТЕЛИ
# ============================================================

@app.get("/users")
def users_list():
    users = db.get_all_users()
    return [
        {
            "id": u.id,
            "nickname": u.nickname,
            "avatar_url": u.avatar_url,
            "account_id": u.account_id,
            "last_updated": u.last_updated.isoformat() if u.last_updated else None,
        }
        for u in users
    ]


# ============================================================
# API: ПРОФИЛЬ
# ============================================================

@app.get("/profile/{user_id}")
def profile_by_id(user_id: int):
    """Профиль: ранг, MMR, ник, аватар, средний KDA, позиции."""
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user_not_found")

    stats = db.get_user_stats(user_id)
    if not stats:
        return {
            "user": user.to_dict(),
            "profile": None,
            "message": "Статистика ещё не собиралась",
        }

    return {
        "user": user.to_dict(),
        "profile": {
            "rank_tier": stats.rank_tier,
            "rank_str": rank_to_str(stats.rank_tier),
            "mmr_estimate": stats.mmr_estimate,
            "updated_at": stats.updated_at.isoformat() if stats.updated_at else None,
        },
    }


@app.get("/me/profile")
def my_profile(request: Request):
    user_id = _current_user_id(request)
    return profile_by_id(user_id)


# ============================================================
# API: СТАТИСТИКА — ЗА ВСЁ ВРЕМЯ
# ============================================================

def _build_stats_payload(user_id: int):
    user = db.get_user_by_id(user_id)
    if not user:
        return None

    stats = db.get_user_stats(user_id)
    if not stats:
        return {
            "user": user.to_dict(),
            "stats": None,
            "message": "Статистика ещё не собиралась",
        }

    # KDA: в БД хранятся *100 как int
    avg_kills = (stats.avg_kills or 0) / 100
    avg_deaths = (stats.avg_deaths or 0) / 100
    avg_assists = (stats.avg_assists or 0) / 100
    avg_kda = (stats.avg_kda or 0) / 100

    # Позиции (за всё время по матчам за текущий патч)
    positions = {
        "carry": {
            "games": stats.games_carry or 0,
            "wins": stats.wins_carry or 0,
            "winrate": _winrate(stats.wins_carry or 0, stats.games_carry or 0),
        },
        "mid": {
            "games": stats.games_mid or 0,
            "wins": stats.wins_mid or 0,
            "winrate": _winrate(stats.wins_mid or 0, stats.games_mid or 0),
        },
        "offlane": {
            "games": stats.games_offlane or 0,
            "wins": stats.wins_offlane or 0,
            "winrate": _winrate(stats.wins_offlane or 0, stats.games_offlane or 0),
        },
        "support": {
            "games": stats.games_support or 0,
            "wins": stats.wins_support or 0,
            "winrate": _winrate(stats.wins_support or 0, stats.games_support or 0),
        },
    }

    return {
        "user": user.to_dict(),
        "stats": {
            "rank_tier": stats.rank_tier,
            "rank_str": rank_to_str(stats.rank_tier),
            "mmr_estimate": stats.mmr_estimate,

            "games_total": stats.games_total or 0,
            "wins_total": stats.wins_total or 0,
            "losses_total": stats.losses_total or 0,
            "winrate_total": _winrate(stats.wins_total or 0, stats.games_total or 0),

            "games_recent": stats.games_recent or 0,
            "wins_recent": stats.wins_recent or 0,
            "winrate_recent": _winrate(stats.wins_recent or 0, stats.games_recent or 0),

            "avg_kills": round(avg_kills, 2),
            "avg_deaths": round(avg_deaths, 2),
            "avg_assists": round(avg_assists, 2),
            "avg_kda": round(avg_kda, 2),

            "positions": positions,

            "last_match_at": stats.last_match_at.isoformat() if stats.last_match_at else None,
            "updated_at": stats.updated_at.isoformat() if stats.updated_at else None,
        },
    }


@app.get("/stats/{user_id}")
def stats_by_id(user_id: int):
    payload = _build_stats_payload(user_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    return payload


@app.get("/me/stats")
def my_stats(request: Request):
    user_id = _current_user_id(request)
    payload = _build_stats_payload(user_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    return payload


# ============================================================
# API: ГЕРОИ — ЗА ВСЁ ВРЕМЯ ИЛИ ЗА ПАТЧ
# ============================================================

@app.get("/stats/{user_id}/heroes")
def heroes_by_id(
    user_id: int,
    limit: int = Query(10, ge=1, le=100),
    scope: str = Query("all", pattern="^(all|patch)$"),
    position: str = Query("", pattern="^(|carry|mid|offlane|support)$"),
):
    """
    scope=all   → HeroStats (patch_id=0)
    scope=patch → HeroStats (patch_id=текущий)

    position — фильтр по позиции (только для scope=patch):
      пусто       — все
      carry/mid/offlane/support — только эта позиция
    """
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user_not_found")

    if scope == "all":
        rows = db.get_hero_stats(user_id, patch_id=0, position="")
        meta = {"scope": "all", "patch": None}
    else:
        current = db.get_current_patch()
        if not current:
            return {"user": {"id": user.id, "nickname": user.nickname},
                    "heroes": [], "meta": {"scope": "patch", "patch": None,
                                           "message": "Патч ещё не синхронизирован"}}
        rows = db.get_hero_stats(user_id, patch_id=current.id, position=position)
        meta = {
            "scope": "patch",
            "patch": {"id": current.id, "name": current.name,
                      "released_at": current.released_at.isoformat()},
            "position": position or "all",
        }

    return {
        "user": {"id": user.id, "nickname": user.nickname},
        "heroes": _hero_rows_to_dict(rows, limit=limit),
        "meta": meta,
    }


# ============================================================
# API: ПОСЛЕДНИЕ 20 МАТЧЕЙ
# ============================================================

@app.get("/stats/{user_id}/recent")
def recent_by_id(user_id: int):
    """
    Статистика за последние 20 матчей:
    - суммарный винрейт,
    - по каждому герою: игры и винрейт.
    """
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user_not_found")

    matches = db.get_user_matches(user_id, limit=20)
    if not matches:
        return {
            "user": {"id": user.id, "nickname": user.nickname},
            "recent": None,
            "message": "Матчи ещё не собирались",
        }

    games = len(matches)
    wins = sum(m.win for m in matches)

    # Агрегация по героям
    hero_agg: dict[int, dict] = {}
    for m in matches:
        h = hero_agg.setdefault(m.hero_id, {"hero_id": m.hero_id, "games": 0, "wins": 0})
        h["games"] += 1
        h["wins"] += m.win

    heroes_sorted = sorted(hero_agg.values(), key=lambda x: x["games"], reverse=True)

    return {
        "user": {"id": user.id, "nickname": user.nickname},
        "recent": {
            "games": games,
            "wins": wins,
            "winrate": _winrate(wins, games),
            "heroes": [
                {
                    "hero_id": h["hero_id"],
                    "hero_name": get_hero_name(h["hero_id"]),
                    "hero_image": get_hero_image_url(h["hero_id"]),
                    "games": h["games"],
                    "wins": h["wins"],
                    "winrate": _winrate(h["wins"], h["games"]),
                }
                for h in heroes_sorted
            ],
        },
    }


# ============================================================
# API: СТАТИСТИКА ЗА ПАТЧ
# ============================================================

@app.get("/stats/{user_id}/patch")
def patch_stats_by_id(user_id: int):
    """
    Статистика за текущий патч:
    - количество игр, суммарный винрейт,
    - топ-5 героев по играм и винрейту,
    - разбивка по позициям.
    """
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user_not_found")

    current = db.get_current_patch()
    if not current:
        return {
            "user": {"id": user.id, "nickname": user.nickname},
            "patch": None,
            "message": "Патч ещё не синхронизирован",
        }

    matches = db.get_user_matches_by_patch(user_id, current.id, limit=1000)
    games = len(matches)
    wins = sum(m.win for m in matches)

    # Топ героев за патч
    heroes = db.get_hero_stats(user_id, patch_id=current.id, position="")
    top_by_games = _hero_rows_to_dict(heroes, limit=5)

    # Топ-5 по винрейту (минимум 3 игры, чтобы не было 1-0-статистики)
    candidates = [h for h in heroes if h.games >= 3]
    candidates_sorted = sorted(
        candidates,
        key=lambda h: (h.wins / h.games) if h.games else 0,
        reverse=True,
    )[:5]
    top_by_winrate = _hero_rows_to_dict(candidates_sorted)

    # Позиции за патч
    positions = {}
    for pos in ("carry", "mid", "offlane", "support"):
        pos_rows = db.get_hero_stats(user_id, patch_id=current.id, position=pos)
        pos_games = sum(h.games for h in pos_rows)
        pos_wins = sum(h.wins for h in pos_rows)
        positions[pos] = {
            "label": POSITION_LABELS.get(pos, pos),
            "games": pos_games,
            "wins": pos_wins,
            "winrate": _winrate(pos_wins, pos_games),
        }

    return {
        "user": {"id": user.id, "nickname": user.nickname},
        "patch": {
            "id": current.id,
            "name": current.name,
            "released_at": current.released_at.isoformat(),
        },
        "summary": {
            "games": games,
            "wins": wins,
            "winrate": _winrate(wins, games),
        },
        "heroes_by_games": top_by_games,
        "heroes_by_winrate": top_by_winrate,
        "positions": positions,
    }
# ============================================================
# API: СОКОМАНДНИКИ
# ============================================================

@app.get("/stats/{user_id}/peers")
def peers_by_id(user_id: int, limit: int = Query(5, ge=1, le=20)):
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user_not_found")

    peers = db.get_peers(user_id, limit=limit)
    return {
        "user": {"id": user.id, "nickname": user.nickname},
        "peers": [
            {
                "account_id": p.peer_account_id,
                "nickname": p.peer_nickname,
                "avatar": p.peer_avatar,
                "with_games": p.with_games,
                "with_win": p.with_win,
                "winrate": _winrate(p.with_win, p.with_games),
                "last_played": p.last_played.isoformat() if p.last_played else None,
            }
            for p in peers
        ],
    }

# ============================================================
# ЗАПУСК (для локальной разработки)
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=5000, reload=config.DEBUG)