import db, steam_auth

friends = [
    76561198065480219,
    76561198141160864,
    76561198357065293,
]

for sid in friends:
    if db.get_user_by_steam_id(sid):
        print(f"{sid} уже есть")
        continue
    account_id = steam_auth.steam_id_to_account_id(sid)
    profile = steam_auth.fetch_steam_profile(sid)
    nickname = profile["nickname"] if profile else f"User_{account_id}"
    avatar = profile["avatar_url"] if profile else None
    db.create_user(sid, account_id, nickname, avatar)
    print(f"Добавлен: {nickname}")