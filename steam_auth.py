from pysteamsignin.steamsignin import SteamSignIn
import requests
import config


def get_login_url(return_to: str) -> str:
    steam = SteamSignIn()
    return steam.ConstructURL(return_to)


def validate_steam_response(args: dict) -> int | None:
    steam = SteamSignIn()
    steam_id = steam.ValidateResults(args)
    if steam_id:
        return int(steam_id)
    return None


def fetch_steam_profile(steam_id64: int) -> dict | None:
    url = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
    params = {
        "key": config.STEAM_API_KEY,
        "steamids": str(steam_id64),
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        players = r.json().get("response", {}).get("players", [])
        if not players:
            return None
        p = players[0]
        return {
            "nickname": p.get("personaname"),
            "avatar_url": p.get("avatarfull"),
        }
    except requests.RequestException:
        return None


def steam_id_to_account_id(steam_id64: int) -> int:
    """Конвертирует SteamID64 в account_id для Dota 2 с проверкой."""
    if not (76561197960265728 < steam_id64 < 76561202255233023):
        raise ValueError(f"Некорректный SteamID64: {steam_id64}")
    return steam_id64 - 76561197960265728