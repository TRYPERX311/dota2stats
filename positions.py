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
    Превращает rank_tier (например, 53) в строку 'Divine 3'.
    None или 0 → 'Calibrating'.
    """
    if not rank_tier:
        return "Calibrating"
    tier = rank_tier // 10
    star = rank_tier % 10
    name = RANK_NAMES.get(tier, "Unknown")
    if tier == 8:      # Immortal без звёзд
        return name
    return f"{name} {star}"
