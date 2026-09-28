import time
from datetime import datetime, timezone

from sqlalchemy import create_engine, Column, BigInteger, Integer, String, DateTime, UniqueConstraint
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker

import config
DATABASE_URL = f"mysql+pymysql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}?charset=utf8mb4"

# === ДВИЖОК И СЕССИЯ ===
engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
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


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    match_id = Column(BigInteger, nullable=False, index=True)
    hero_id = Column(Integer, nullable=False)
    win = Column(Integer, nullable=False)
    duration = Column(Integer, nullable=True)
    played_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "match_id", name="uq_user_match"),
    )


class PlayerStats(Base):
    __tablename__ = "player_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, unique=True, index=True)
    games_total = Column(Integer, default=0)
    wins_total = Column(Integer, default=0)
    games_recent = Column(Integer, default=0)
    wins_recent = Column(Integer, default=0)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )


class HeroStats(Base):
    __tablename__ = "hero_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    hero_id = Column(Integer, nullable=False)
    games = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    __table_args__ = (
        UniqueConstraint("user_id", "hero_id", name="uq_user_hero"),
    )


# ============================================================
# СОЗДАНИЕ ТАБЛИЦ
# ============================================================

def init_db(retries: int = 10, delay: float = 2.0):
    """Ждём готовности MySQL и создаём таблицы.

    В Docker MySQL может стартовать дольше приложения, поэтому делаем retry.
    """
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
            user.last_updated = when or datetime.now(timezone.utc).replace(tzinfo=None)
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
# MATCHES
# ============================================================

def get_user_matches(user_id: int, limit: int = 100):
    with SessionLocal() as session:
        return (
            session.query(Match)
            .filter(Match.user_id == user_id)
            .order_by(Match.played_at.desc())
            .limit(limit)
            .all()
        )


def insert_matches(user_id: int, matches: list):
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


# ============================================================
# PLAYER_STATS
# ============================================================

def get_user_stats(user_id: int):
    with SessionLocal() as session:
        return session.query(PlayerStats).filter(PlayerStats.user_id == user_id).first()


def upsert_player_stats(user_id: int, games_total: int, wins_total: int,
                        games_recent: int, wins_recent: int):
    with SessionLocal() as session:
        stats = session.query(PlayerStats).filter(PlayerStats.user_id == user_id).first()
        if not stats:
            stats = PlayerStats(user_id=user_id)
            session.add(stats)
        stats.games_total = games_total
        stats.wins_total = wins_total
        stats.games_recent = games_recent
        stats.wins_recent = wins_recent
        stats.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        session.commit()


# ============================================================
# HERO_STATS
# ============================================================

def get_hero_stats(user_id: int):
    with SessionLocal() as session:
        return (
            session.query(HeroStats)
            .filter(HeroStats.user_id == user_id)
            .order_by(HeroStats.games.desc())
            .all()
        )


def replace_hero_stats(user_id: int, heroes: list):
    with SessionLocal() as session:
        session.query(HeroStats).filter(HeroStats.user_id == user_id).delete()
        for h in heroes:
            session.add(HeroStats(user_id=user_id, **h))
        session.commit()