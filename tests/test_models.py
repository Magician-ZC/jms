"""
Models Tests
数据库模型测试
"""

import pytest
import os
from datetime import datetime

# 设置测试数据库
os.environ["TOKEN_DB_URL"] = "sqlite:///:memory:"

from token_manager.models import (
    Token,
    TokenStatus,
    ExtensionConnection,
    init_database,
    close_database,
    get_db_session,
    Base,
    get_engine
)


@pytest.fixture(autouse=True)
def setup_database():
    """每个测试前重置数据库"""
    close_database()
    engine = init_database()
    # 清空所有表数据
    with engine.connect() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
        conn.commit()
    yield
    close_database()


class TestTokenModel:
    """Token模型测试"""
    
    def test_create_token(self):
        """测试创建Token记录"""
        session = get_db_session()
        try:
            token = Token(
                user_id="test_user",
                token_value="encrypted_token_value",
                status=TokenStatus.ACTIVE
            )
            session.add(token)
            session.commit()
            
            assert token.id is not None
            assert token.user_id == "test_user"
            assert token.status == TokenStatus.ACTIVE
            assert token.created_at is not None
        finally:
            session.close()
    
    def test_token_status_enum(self):
        """测试Token状态枚举"""
        assert TokenStatus.ACTIVE.value == "active"
        assert TokenStatus.EXPIRED.value == "expired"
        assert TokenStatus.INVALID.value == "invalid"
    
    def test_token_to_dict(self):
        """测试Token转字典"""
        session = get_db_session()
        try:
            token = Token(
                user_id="dict_user",
                token_value="token_value",
                status=TokenStatus.ACTIVE,
                extension_id="ext123"
            )
            session.add(token)
            session.commit()
            
            token_dict = token.to_dict()
            
            assert token_dict["user_id"] == "dict_user"
            assert token_dict["status"] == "active"
            assert token_dict["extension_id"] == "ext123"
            assert "created_at" in token_dict
        finally:
            session.close()
    
    def test_token_unique_user_id(self):
        """测试用户ID唯一约束"""
        session = get_db_session()
        try:
            token1 = Token(
                user_id="unique_user",
                token_value="token1"
            )
            session.add(token1)
            session.commit()
            
            token2 = Token(
                user_id="unique_user",
                token_value="token2"
            )
            session.add(token2)
            
            with pytest.raises(Exception):  # IntegrityError
                session.commit()
        finally:
            session.rollback()
            session.close()


class TestExtensionConnectionModel:
    """插件连接模型测试"""
    
    def test_create_connection(self):
        """测试创建连接记录"""
        session = get_db_session()
        try:
            conn = ExtensionConnection(
                extension_id="ext_001",
                user_id="user_001"
            )
            session.add(conn)
            session.commit()
            
            assert conn.id is not None
            assert conn.extension_id == "ext_001"
            assert conn.connected_at is not None
        finally:
            session.close()
    
    def test_connection_to_dict(self):
        """测试连接记录转字典"""
        session = get_db_session()
        try:
            conn = ExtensionConnection(
                extension_id="ext_002",
                user_id="user_002"
            )
            session.add(conn)
            session.commit()
            
            conn_dict = conn.to_dict()
            
            assert conn_dict["extension_id"] == "ext_002"
            assert conn_dict["user_id"] == "user_002"
            assert "connected_at" in conn_dict
        finally:
            session.close()


class TestDatabaseOperations:
    """数据库操作测试"""
    
    def test_query_token_by_user_id(self):
        """测试按用户ID查询Token"""
        session = get_db_session()
        try:
            token = Token(
                user_id="query_user",
                token_value="query_token"
            )
            session.add(token)
            session.commit()
            
            result = session.query(Token).filter(
                Token.user_id == "query_user"
            ).first()
            
            assert result is not None
            assert result.token_value == "query_token"
        finally:
            session.close()
    
    def test_query_tokens_by_status(self):
        """测试按状态查询Token"""
        session = get_db_session()
        try:
            token1 = Token(
                user_id="active_user",
                token_value="token1",
                status=TokenStatus.ACTIVE
            )
            token2 = Token(
                user_id="expired_user",
                token_value="token2",
                status=TokenStatus.EXPIRED
            )
            session.add_all([token1, token2])
            session.commit()
            
            active_tokens = session.query(Token).filter(
                Token.status == TokenStatus.ACTIVE
            ).all()
            
            assert len(active_tokens) == 1
            assert active_tokens[0].user_id == "active_user"
        finally:
            session.close()
    
    def test_update_token(self):
        """测试更新Token"""
        session = get_db_session()
        try:
            token = Token(
                user_id="update_user",
                token_value="old_token"
            )
            session.add(token)
            session.commit()
            
            token.token_value = "new_token"
            token.status = TokenStatus.EXPIRED
            session.commit()
            
            result = session.query(Token).filter(
                Token.user_id == "update_user"
            ).first()
            
            assert result.token_value == "new_token"
            assert result.status == TokenStatus.EXPIRED
        finally:
            session.close()
    
    def test_delete_token(self):
        """测试删除Token"""
        session = get_db_session()
        try:
            token = Token(
                user_id="delete_user",
                token_value="delete_token"
            )
            session.add(token)
            session.commit()
            token_id = token.id
            
            session.delete(token)
            session.commit()
            
            result = session.query(Token).filter(
                Token.id == token_id
            ).first()
            
            assert result is None
        finally:
            session.close()
