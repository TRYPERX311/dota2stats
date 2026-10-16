"""Справочники: ранги, позиции, патчи."""


RANK_NAMES = {
    1: "Herald",
    2: "Guardian",
    3: "Crusader",
    4: "Archon",
    5: "Legend",
    6: "Ancient",
    7: "Divine",
    8: "Immortal",
}


def rank_to_str(rank_tier: int | None) -> str:
    """
    Превращает rank_tier (например, 53) в строку 'Legend 3'.
    None или 0 → 'Calibrating'.
    Невалидный вход → 'Unknown'.
    """
    if not rank_tier:
        return "Calibrating"

    tier = rank_tier // 10
    star = rank_tier % 10

    if tier not in RANK_NAMES:
        return "Unknown"

    if tier == 8:      # Immortal — без звёзд
        return RANK_NAMES[8]

    if not (1 <= star <= 5):
        return "Unknown"

    return f"{RANK_NAMES[tier]} {star}"
