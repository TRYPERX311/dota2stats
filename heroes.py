import json
import os

_HEROES_PATH = os.path.join(os.path.dirname(__file__), "heroes.json")

with open(_HEROES_PATH, "r", encoding="utf-8") as f:
    _HEROES_RAW = json.load(f)

# Превращаем в удобный словарь: {hero_id: {"name": "invoker", "localized_name": "Invoker"}}
HEROES = {}
for hero_id_str, data in _HEROES_RAW.items():
    HEROES[int(hero_id_str)] = {
        "name": data.get("name"),                       # npc_dota_hero_invoker
        "localized_name": data.get("localized_name"),   # Invoker
        "img": data.get("img"),                         # /apps/dota2/images/dota_react/heroes/invoker.png
    }


def get_hero_name(hero_id: int) -> str:
    """Возвращает читаемое имя героя или Unknown."""
    hero = HEROES.get(hero_id)
    return hero["localized_name"] if hero else f"Unknown ({hero_id})"


def get_hero_image_url(hero_id: int) -> str | None:
    """Возвращает URL картинки героя (относительный)."""
    hero = HEROES.get(hero_id)
    if not hero or not hero.get("img"):
        return None
    return f"https://cdn.cloudflare.steamstatic.com{hero['img']}"