from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import RedirectResponse, FileResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
import config
import db
import steam_auth
from heroes import get_hero_name, get_hero_image_url

app = FastAPI(title="Dota 2 Stats")

# Cookie-сессия: тот же формат, что у Flask (itsdangerous).
# Ключ берём из config.SECRET_KEY — cookies, выданные Flask, будут читаться.
app.add_middleware(
    SessionMiddleware,
    secret_key=config.SECRET_KEY,
    session_cookie="session",      # имя cookie как во Flask по умолчанию
    same_site="lax",
    https_only=False,              # на проде за HTTPS поставишь True
)
app.mount("/static", StaticFiles(directory="static"), name="static")

db.init_db()


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
    else:
        profile = steam_auth.fetch_steam_profile(steam_id64)
        if profile:
            db.update_user_info(user.id, profile["nickname"], profile["avatar_url"])

    request.session["user_id"] = user.id
    return RedirectResponse("/")


@app.get("/me")
def me(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="not_authenticated")
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
# API: СТАТИСТИКА
# ============================================================

def _build_stats_payload(user_id: int):
    """Собирает полный ответ статистики. Возвращает dict или None."""
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

    return {
        "user": user.to_dict(),
        "stats": {
            "games_total": stats.games_total,
            "wins_total": stats.wins_total,
            "winrate_total": round(stats.wins_total / stats.games_total * 100, 2) if stats.games_total else 0,
            "games_recent": stats.games_recent,
            "wins_recent": stats.wins_recent,
            "winrate_recent": round(stats.wins_recent / stats.games_recent * 100, 2) if stats.games_recent else 0,
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
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="not_authenticated")
    payload = _build_stats_payload(user_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    return payload


@app.get("/stats/{user_id}/heroes")
def heroes_by_id(
    user_id: int,
    limit: int = Query(10, ge=1, le=50),
):
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user_not_found")

    hero_stats = db.get_hero_stats(user_id)[:limit]

    result = []
    for h in hero_stats:
        winrate = round(h.wins / h.games * 100, 2) if h.games else 0
        result.append({
            "hero_id": h.hero_id,
            "hero_name": get_hero_name(h.hero_id),
            "hero_image": get_hero_image_url(h.hero_id),
            "games": h.games,
            "wins": h.wins,
            "winrate": winrate,
        })

    return {
        "user": {"id": user.id, "nickname": user.nickname},
        "heroes": result,
    }


# ============================================================
# ТЕСТОВЫЙ РОУТ (только в DEBUG)
# ============================================================

if config.DEBUG:
    @app.get("/test-login")
    def test_login(request: Request, steamid: str | None = None):
        if not steamid:
            return JSONResponse(
                {"error": "Укажи ?steamid=76561198XXXXXXXXX"},
                status_code=400,
            )
        try:
            steam_id64 = int(steamid)
        except ValueError:
            return JSONResponse({"error": "steamid должен быть числом"}, status_code=400)

        user = db.get_user_by_steam_id(steam_id64)

        if not user:
            try:
                account_id = steam_auth.steam_id_to_account_id(steam_id64)
            except ValueError as e:
                return JSONResponse({"error": str(e)}, status_code=400)
            profile = steam_auth.fetch_steam_profile(steam_id64)
            nickname = profile["nickname"] if profile else f"TestUser_{account_id}"
            avatar_url = profile["avatar_url"] if profile else None
            user = db.create_user(
                steam_id64=steam_id64,
                account_id=account_id,
                nickname=nickname,
                avatar_url=avatar_url,
            )
        else:
            profile = steam_auth.fetch_steam_profile(steam_id64)
            if profile:
                db.update_user_info(user.id, profile["nickname"], profile["avatar_url"])

        request.session["user_id"] = user.id
        return RedirectResponse("/")


# ============================================================
# ЗАПУСК (для локальной разработки)
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=5000, reload=config.DEBUG)