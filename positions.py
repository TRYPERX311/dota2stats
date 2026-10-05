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


# lane_role из OpenDota → наша категория
# 1 = Safe Lane (Carry), 2 = Mid, 3 = Offlane, 4 = Soft Support, 5 = Hard Support
LANE_TO_POSITION = {
    1: "carry",
    2: "mid",
    3: "offlane",
    4: "support",
    5: "support",
}


def lane_role_to_position(lane_role: int | None) -> str:
    """Возвращает 'carry'/'mid'/'offlane'/'support'/'unknown'."""
    if lane_role is None:
        return "unknown"
    return LANE_TO_POSITION.get(lane_role, "unknown")


POSITION_LABELS = {
    "carry": "Carry",
    "mid": "Mid",
    "offlane": "Offlane",
    "support": "Support",
    "unknown": "Unknown",
}