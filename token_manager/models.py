"""
Token Manager Database Models
Token管理系统数据库模型
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Integer, String, DateTime, Enum, create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.pool import StaticPool

from .config import DATABASE_URL, get_china_now

Base = declarative_base()


class TokenStatus(enum.Enum):
    """Token状态枚举"""
    ACTIVE = "active"
    EXPIRED = "expired"
    INVALID = "invalid"


class Token(Base):
    """Token数据模型"""
    __tablename__ = "tokens"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), unique=True, nullable=False, index=True)
    account = Column(String(64), nullable=True)  # 登录账号
    token_value = Column(String(512), nullable=False)  # 加密存储
    status = Column(Enum(TokenStatus), default=TokenStatus.ACTIVE)
    extension_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=get_china_now)
    updated_at = Column(DateTime, default=get_china_now, onupdate=get_china_now)
    last_active_at = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<Token(id={self.id}, user_id={self.user_id}, status={self.status.value})>"
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "account": self.account,
            "token_value": self.token_value,
            "status": self.status.value,
            "extension_id": self.extension_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_active_at": self.last_active_at.isoformat() if self.last_active_at else None,
        }


class ExtensionConnection(Base):
    """插件连接记录"""
    __tablename__ = "extension_connections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    extension_id = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(String(64), nullable=True)
    connected_at = Column(DateTime, default=get_china_now)
    last_heartbeat = Column(DateTime, default=get_china_now)
    
    def __repr__(self):
        return f"<ExtensionConnection(id={self.id}, extension_id={self.extension_id})>"
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "extension_id": self.extension_id,
            "user_id": self.user_id,
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
        }


# 数据库引擎和会话工厂
_engine = None
_SessionLocal = None


def get_engine():
    """获取数据库引擎（单例模式）"""
    global _engine
    if _engine is None:
        # SQLite特殊配置
        if DATABASE_URL.startswith("sqlite"):
            _engine = create_engine(
                DATABASE_URL,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
                echo=False
            )
        else:
            _engine = create_engine(DATABASE_URL, echo=False)
    return _engine


def get_session_factory():
    """获取会话工厂（单例模式）"""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=get_engine()
        )
    return _SessionLocal


def init_database():
    """初始化数据库，创建所有表"""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    return engine


def get_db_session() -> Session:
    """获取数据库会话"""
    SessionLocal = get_session_factory()
    return SessionLocal()


def close_database():
    """关闭数据库连接"""
    global _engine, _SessionLocal
    if _engine:
        _engine.dispose()
        _engine = None
        _SessionLocal = None
