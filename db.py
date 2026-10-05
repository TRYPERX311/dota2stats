import time
from datetime import datetime, timezone

from sqlalchemy import (
    create_engine, Column, BigInteger, Integer, String, DateTime,
    UniqueConstraint, Index,
)
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker

import config


DATABASE_URL = (
    f"mysql+pymysql://{config.DB_USER}:{config.DB_PASSWORD}"
    f"@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}?charset=utf8mb4"
)

engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ============================================================
# МОДЕЛИ
# ============================================================

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    steam_id64 = Column(BigInteger, unique=True, nullable=False, index=True)
    account_id = Column(Integer, nullable=False, index=True)
    nickname = Column(String(255), nullable=True)
    avatar_url = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=_now)
    last_updated = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "steam_id64": str(self.steam_id64),
            "account_id": self.account_id,
            "nickname": self.nickname,
            "avatar_url": self.avatar_url,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }


class Patch(Base):
    """Справочник патчей OpenDota."""
    __tablename__ = "patches"

    id = Column(Integer, primary_key=True)          # совпадает с id OpenDota
    name = Column(String(32), nullable=False)       # "7.35"
    released_at = Column(DateTime, nullable=False)
    is_current = Column(Integer, default=0)         # 1 если последний


class Match(Base):
    """Детали матча для конкретного игрока."""
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    match_id = Column(BigInteger, nullable=False, index=True)
    hero_id = Column(Integer, nullable=False)
    win = Column(Integer, nullable=False)
    duration = Column(Integer, nullable=True)
    played_at = Column(DateTime, nullable=True, index=True)

    # Расширенные поля
    kills = Column(Integer, nullable=True)
    deaths = Column(Integer, nullable=True)
    assists = Column(Integer, nullable=True)
    lane_role = Column(Integer, nullable=True)
    position = Column(String(16), nullable=True)   # carry/mid/offlane/support
    patch_id = Column(Integer, nullable=False, default=0, index=True)
    gold_per_min = Column(Integer, nullable=True)
    xp_per_min = Column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "match_id", name="uq_user_match"),
        Index("ix_match_user_patch", "user_id", "patch_id"),
    )


class PlayerStats(Base):
    """Агрегированная статистика за всё время."""
    __tablename__ = "player_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, unique=True, index=True)

    rank_tier = Column(Integer, nullable=True)
    mmr_estimate = Column(Integer, nullable=True)

    games_total = Column(Integer, default=0)
    wins_total = Column(Integer, default=0)
    losses_total = Column(Integer, default=0)

    games_recent = Column(Integer, default=0)      # последние 20
    wins_recent = Column(Integer, default=0)

    avg_kills = Column(Integer, default=0)          # *100
    avg_deaths = Column(Integer, default=0)
    avg_assists = Column(Integer, default=0)
    avg_kda = Column(Integer, default=0)            # *100

    # Игры по позициям (за всё время)
    games_carry = Column(Integer, default=0)
    wins_carry = Column(Integer, default=0)
    games_mid = Column(Integer, default=0)
    wins_mid = Column(Integer, default=0)
    games_offlane = Column(Integer, default=0)
    wins_offlane = Column(Integer, default=0)
    games_support = Column(Integer, default=0)
    wins_support = Column(Integer, default=0)

    last_match_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class HeroStats(Base):
    """
    Статистика по героям.

    Комбинации patch_id / position:
    - (0, '')         — за всё время
    - (X, '')         — за патч X
    - (X, 'carry')    — за патч X по позиции carry
    - (X, 'mid')      — за патч X по позиции mid
    - (X, 'offlane')  — за патч X по позиции offlane
    - (X, 'support')  — за патч X по позиции support
    """
    __tablename__ = "hero_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    hero_id = Column(Integer, nullable=False)

    patch_id = Column(Integer, nullable=False, default=0, index=True)
    position = Column(String(16), nullable=False, default="")

    games = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint(
            "user_id", "hero_id", "patch_id", "position",
            name="uq_user_hero_patch_pos",
        ),
    )


# ============================================================
# СОЗДАНИЕ ТАБЛИЦ
# ============================================================

def init_db(retries: int = 10, delay: float = 2.0):
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            Base.metadata.create_all(bind=engine)
            return
        except OperationalError as e:
            last_error = e
            print(f"[init_db] MySQL не готов (попытка {attempt}/{retries}): {e}")
            time.sleep(delay)
    raise last_error


# ============================================================
# USERS
# ============================================================

def get_user_by_steam_id(steam_id64: int):
    with SessionLocal() as session:
        return session.query(User).filter(User.steam_id64 == steam_id64).first()


def get_user_by_id(user_id: int):
    with SessionLocal() as session:
        return session.query(User).filter(User.id == user_id).first()


def get_all_users():
    with SessionLocal() as session:
        return session.query(User).all()


def create_user(steam_id64: int, account_id: int, nickname: str = None, avatar_url: str = None):
    with SessionLocal() as session:
        user = User(
            steam_id64=steam_id64,
            account_id=account_id,
            nickname=nickname,
            avatar_url=avatar_url,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def update_last_updated(user_id: int, when: datetime = None):
    with SessionLocal() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if user:
            user.last_updated = when or _now()
            session.commit()


def update_user_info(user_id: int, nickname: str = None, avatar_url: str = None):
    with SessionLocal() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            return None
        if nickname is not None:
            user.nickname = nickname
        if avatar_url is not None:
            user.avatar_url = avatar_url
        session.commit()
        session.refresh(user)
        return user


# ============================================================
# PATCHES
# ============================================================

def get_current_patch():
    with SessionLocal() as session:
        return (
            session.query(Patch)
            .filter(Patch.is_current == 1)
            .order_by(Patch.released_at.desc())
            .first()
        )


def get_patch_by_id(patch_id: int):
    with SessionLocal() as session:
        return session.query(Patch).filter(Patch.id == patch_id).first()


def upsert_patches(patches: list):
    """
    patches: [{"id": 45, "name": "7.35", "released_at": datetime}, ...]
    Помечает самый свежий как is_current=1, остальные — 0.
    """
    if not patches:
        return
    with SessionLocal() as session:
        session.query(Patch).update({Patch.is_current: 0})
        for p in patches:
            existing = session.query(Patch).filter(Patch.id == p["id"]).first()
            if existing:
                existing.name = p["name"]
                existing.released_at = p["released_at"]
            else:
                session.add(Patch(
                    id=p["id"],
                    name=p["name"],
                    released_at=p["released_at"],
                    is_current=0,
                ))
        session.commit()

        latest = (
            session.query(Patch)
            .order_by(Patch.released_at.desc())
            .first()
        )
        if latest:
            latest.is_current = 1
            session.commit()


# ============================================================
# MATCHES
# ============================================================

def get_user_matches(user_id: int, limit: int = 1000):
    with SessionLocal() as session:
        return (
            session.query(Match)
            .filter(Match.user_id == user_id)
            .order_by(Match.played_at.desc())
            .limit(limit)
            .all()
        )


def get_user_matches_by_patch(user_id: int, patch_id: int, limit: int = 200):
    with SessionLocal() as session:
        return (
            session.query(Match)
            .filter(Match.user_id == user_id, Match.patch_id == patch_id)
            .order_by(Match.played_at.desc())
            .limit(limit)
            .all()
        )


def get_existing_match_ids(user_id: int) -> set:
    """Множество match_id, уже сохранённых для пользователя."""
    with SessionLocal() as session:
        rows = (
            session.query(Match.match_id)
            .filter(Match.user_id == user_id)
            .all()
        )
        return {r[0] for r in rows}


def insert_matches(user_id: int, matches: list) -> int:
    """
    matches: [{"match_id", "hero_id", "win", "duration", "played_at",
               "kills", "deaths", "assists", "lane_role", "position",
               "patch_id", "gold_per_min", "xp_per_min"}, ...]
    Возвращает количество вставленных.
    """
    inserted = 0
    with SessionLocal() as session:
        for m in matches:
            exists = (
                session.query(Match)
                .filter(Match.user_id == user_id, Match.match_id == m["match_id"])
                .first()
            )
            if exists:
                continue
            session.add(Match(user_id=user_id, **m))
            inserted += 1
        session.commit()
    return inserted


def update_match_details(user_id: int, match_id: int, details: dict):
    """Дополняет существующий матч деталями (kda, position, patch_id)."""
    with SessionLocal() as session:
        m = (
            session.query(Match)
            .filter(Match.user_id == user_id, Match.match_id == match_id)
            .first()
        )
        if not m:
            return False
        for k, v in details.items():
            setattr(m, k, v)
        session.commit()
        return True


# ============================================================
# PLAYER_STATS
# ============================================================

def get_user_stats(user_id: int):
    with SessionLocal() as session:
        return (
            session.query(PlayerStats)
            .filter(PlayerStats.user_id == user_id)
            .first()
        )


def upsert_player_stats(user_id: int, fields: dict):
    """fields: любые поля PlayerStats, кроме id и user_id."""
    with SessionLocal() as session:
        stats = (
            session.query(PlayerStats)
            .filter(PlayerStats.user_id == user_id)
            .first()
        )
        if not stats:
            stats = PlayerStats(user_id=user_id)
            session.add(stats)
        for k, v in fields.items():
            setattr(stats, k, v)
        stats.updated_at = _now()
        session.commit()


# ============================================================
# HERO_STATS
# ============================================================

def get_hero_stats(user_id: int, patch_id: int = 0, position: str = ""):
    with SessionLocal() as session:
        return (
            session.query(HeroStats)
            .filter(
                HeroStats.user_id == user_id,
                HeroStats.patch_id == patch_id,
                HeroStats.position == position,
            )
            .order_by(HeroStats.games.desc())
            .all()
        )


def replace_hero_stats(user_id: int, patch_id: int, position: str, heroes: list):
    """
    heroes: [{"hero_id", "games", "wins"}, ...]
    Полностью заменяет набор для (user_id, patch_id, position).
    """
    with SessionLocal() as session:
        session.query(HeroStats).filter(
            HeroStats.user_id == user_id,
            HeroStats.patch_id == patch_id,
            HeroStats.position == position,
        ).delete()
        for h in heroes:
            session.add(HeroStats(
                user_id=user_id,
                patch_id=patch_id,
                position=position,
                **h,
            ))
        session.commit()