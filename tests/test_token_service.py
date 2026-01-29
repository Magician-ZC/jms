"""
Token Service Tests
Token服务核心功能测试
"""

import pytest
import os
import tempfile
from datetime import datetime

# 设置测试数据库
os.environ["TOKEN_DB_URL"] = "sqlite:///:memory:"

from token_manager.models import init_database, close_database, TokenStatus, Base, get_engine
from token_manager.token_service import (
    TokenService, 
    TokenValidationError, 
    TokenNotFoundError,
    reset_token_service
)
from token_manager.crypto_utils import decrypt_token


@pytest.fixture(autouse=True)
def setup_database():
    """每个测试前重置数据库"""
    reset_token_service()
    close_database()
    engine = init_database()
    # 清空所有表数据
    with engine.connect() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
        conn.commit()
    yield
    reset_token_service()
    close_database()


class TestTokenServiceBasic:
    """Token服务基本功能测试"""
    
    def test_create_token(self):
        """测试创建Token"""
        service = TokenService()
        try:
            token = service.create_or_update(
                token="test_token_12345678901234567890",
                user_id="user001"
            )
            assert token is not None
            assert token.user_id == "user001"
            assert token.status == TokenStatus.ACTIVE
        finally:
            service.close()
    
    def test_create_token_with_extension_id(self):
        """测试创建带extension_id的Token"""
        service = TokenService()
        try:
            token = service.create_or_update(
                token="test_token_12345678901234567890",
                user_id="user002",
                extension_id="ext123"
            )
            assert token.extension_id == "ext123"
        finally:
            service.close()
    
    def test_update_existing_token(self):
        """测试更新已存在的Token（幂等性）"""
        service = TokenService()
        try:
            # 创建第一个Token
            token1 = service.create_or_update(
                token="first_token_1234567890",
                user_id="user003"
            )
            token1_id = token1.id
            
            # 更新同一用户的Token
            token2 = service.create_or_update(
                token="second_token_0987654321",
                user_id="user003"
            )
            
            # 应该是同一条记录
            assert token2.id == token1_id
            
            # 验证Token值已更新
            decrypted = decrypt_token(token2.token_value)
            assert decrypted == "second_token_0987654321"
        finally:
            service.close()
    
    def test_get_by_user(self):
        """测试根据用户ID获取Token"""
        service = TokenService()
        try:
            service.create_or_update(
                token="test_token_12345678901234567890",
                user_id="user004"
            )
            
            token = service.get_by_user("user004")
            assert token is not None
            assert token.user_id == "user004"
            
            # 不存在的用户
            token = service.get_by_user("nonexistent")
            assert token is None
        finally:
            service.close()
    
    def test_get_all(self):
        """测试获取所有Token"""
        service = TokenService()
        try:
            service.create_or_update(token="token_a_1234567890", user_id="user_a")
            service.create_or_update(token="token_b_1234567890", user_id="user_b")
            
            tokens = service.get_all()
            assert len(tokens) == 2
        finally:
            service.close()
    
    def test_delete_token(self):
        """测试删除Token"""
        service = TokenService()
        try:
            token = service.create_or_update(
                token="test_token_12345678901234567890",
                user_id="user005"
            )
            token_id = token.id
            
            # 删除Token
            result = service.delete(token_id)
            assert result is True
            
            # 验证已删除
            token = service.get_by_id(token_id)
            assert token is None
        finally:
            service.close()
    
    def test_delete_nonexistent_token(self):
        """测试删除不存在的Token"""
        service = TokenService()
        try:
            with pytest.raises(TokenNotFoundError):
                service.delete(99999)
        finally:
            service.close()
    
    def test_update_status(self):
        """测试更新Token状态"""
        service = TokenService()
        try:
            token = service.create_or_update(
                token="test_token_12345678901234567890",
                user_id="user006"
            )
            
            # 更新状态为过期
            result = service.update_status(token.id, TokenStatus.EXPIRED)
            assert result is True
            
            # 验证状态已更新
            token = service.get_by_id(token.id)
            assert token.status == TokenStatus.EXPIRED
        finally:
            service.close()
    
    def test_update_last_active(self):
        """测试更新最后活跃时间"""
        service = TokenService()
        try:
            token = service.create_or_update(
                token="test_token_12345678901234567890",
                user_id="user007"
            )
            
            # 初始时last_active_at为None
            assert token.last_active_at is None
            
            # 更新活跃时间
            result = service.update_last_active(token.id)
            assert result is True
            
            # 验证时间已更新
            token = service.get_by_id(token.id)
            assert token.last_active_at is not None
        finally:
            service.close()


class TestTokenValidation:
    """Token验证测试"""
    
    def test_empty_token_rejected(self):
        """测试空Token被拒绝"""
        service = TokenService()
        try:
            with pytest.raises(TokenValidationError):
                service.create_or_update(token="", user_id="user")
        finally:
            service.close()
    
    def test_whitespace_token_rejected(self):
        """测试纯空白Token被拒绝"""
        service = TokenService()
        try:
            with pytest.raises(TokenValidationError):
                service.create_or_update(token="   ", user_id="user")
        finally:
            service.close()
    
    def test_short_token_rejected(self):
        """测试过短Token被拒绝"""
        service = TokenService()
        try:
            with pytest.raises(TokenValidationError):
                service.create_or_update(token="short", user_id="user")
        finally:
            service.close()
    
    def test_empty_user_id_rejected(self):
        """测试空用户ID被拒绝"""
        service = TokenService()
        try:
            with pytest.raises(TokenValidationError):
                service.create_or_update(
                    token="valid_token_1234567890",
                    user_id=""
                )
        finally:
            service.close()


class TestDatabaseOperations:
    """数据库操作测试"""
    
    def test_database_persistence(self):
        """测试数据库持久化"""
        service1 = TokenService()
        try:
            service1.create_or_update(
                token="persistent_token_1234567890",
                user_id="persist_user"
            )
        finally:
            service1.close()
        
        # 创建新的服务实例
        service2 = TokenService()
        try:
            token = service2.get_by_user("persist_user")
            assert token is not None
            assert token.user_id == "persist_user"
        finally:
            service2.close()
    
    def test_get_active_tokens(self):
        """测试获取活跃Token"""
        service = TokenService()
        try:
            # 创建两个Token
            token1 = service.create_or_update(
                token="active_token_1234567890",
                user_id="active_user"
            )
            token2 = service.create_or_update(
                token="expired_token_1234567890",
                user_id="expired_user"
            )
            
            # 将一个标记为过期
            service.update_status(token2.id, TokenStatus.EXPIRED)
            
            # 获取活跃Token
            active_tokens = service.get_active_tokens()
            assert len(active_tokens) == 1
            assert active_tokens[0].user_id == "active_user"
        finally:
            service.close()
