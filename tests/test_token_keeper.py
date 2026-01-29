"""
Token Keeper Tests
Token保活服务测试
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from token_manager.token_keeper import (
    TokenKeeper,
    TokenKeeperError,
    get_token_keeper,
    reset_token_keeper
)
from token_manager.models import Token, TokenStatus, init_database, get_db_session, close_database
from token_manager.token_service import TokenService, reset_token_service
from token_manager.websocket_manager import WebSocketManager, ConnectionInfo, reset_websocket_manager
from token_manager.crypto_utils import encrypt_token


@pytest.fixture(autouse=True)
def setup_and_teardown():
    """每个测试前后的设置和清理"""
    # 重置全局实例
    reset_token_keeper()
    reset_token_service()
    reset_websocket_manager()
    
    # 关闭现有数据库连接
    close_database()
    
    # 重置models模块中的全局变量
    from token_manager import models
    models._engine = None
    models._SessionLocal = None
    
    # 使用内存数据库
    import os
    os.environ["TOKEN_DB_URL"] = "sqlite:///:memory:"
    
    # 重新加载配置
    from token_manager import config
    import importlib
    importlib.reload(config)
    importlib.reload(models)
    
    init_database()
    
    yield
    
    # 清理
    reset_token_keeper()
    reset_token_service()
    reset_websocket_manager()
    close_database()


@pytest.fixture
def token_service():
    """创建Token服务实例"""
    service = TokenService()
    yield service
    service.close()


@pytest.fixture
def websocket_manager():
    """创建WebSocket管理器实例"""
    return WebSocketManager()


@pytest.fixture
def mock_http_client():
    """创建模拟的HTTP客户端"""
    client = AsyncMock()
    return client


class TestTokenKeeperInit:
    """TokenKeeper初始化测试"""
    
    def test_default_init(self):
        """测试默认初始化"""
        keeper = TokenKeeper()
        assert keeper.interval == 300  # 默认5分钟
        assert not keeper.is_running
        assert keeper.stats["total_checks"] == 0
    
    def test_custom_interval(self):
        """测试自定义间隔"""
        keeper = TokenKeeper(interval_seconds=60)
        assert keeper.interval == 60
    
    def test_set_interval(self):
        """测试设置间隔"""
        keeper = TokenKeeper()
        keeper.set_interval(120)
        assert keeper.interval == 120
    
    def test_reset_stats(self):
        """测试重置统计"""
        keeper = TokenKeeper()
        keeper._stats["total_checks"] = 10
        keeper.reset_stats()
        assert keeper.stats["total_checks"] == 0


class TestTokenKeeperStartStop:
    """TokenKeeper启动停止测试"""
    
    @pytest.mark.asyncio
    async def test_start_stop(self):
        """测试启动和停止"""
        keeper = TokenKeeper(interval_seconds=1)
        
        # 启动
        await keeper.start()
        assert keeper.is_running
        
        # 等待一小段时间
        await asyncio.sleep(0.1)
        
        # 停止
        await keeper.stop()
        assert not keeper.is_running
    
    @pytest.mark.asyncio
    async def test_double_start(self):
        """测试重复启动"""
        keeper = TokenKeeper(interval_seconds=1)
        
        await keeper.start()
        await keeper.start()  # 应该被忽略
        assert keeper.is_running
        
        await keeper.stop()
    
    @pytest.mark.asyncio
    async def test_double_stop(self):
        """测试重复停止"""
        keeper = TokenKeeper(interval_seconds=1)
        
        await keeper.start()
        await keeper.stop()
        await keeper.stop()  # 应该被忽略
        assert not keeper.is_running


class TestCheckTokenValidity:
    """Token有效性检查测试"""
    
    @pytest.mark.asyncio
    async def test_valid_token_200(self, mock_http_client):
        """测试有效Token返回200"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_http_client.get = AsyncMock(return_value=mock_response)
        
        keeper = TokenKeeper(http_client=mock_http_client)
        result = await keeper.check_token_validity("valid_token")
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_invalid_token_401(self, mock_http_client):
        """测试无效Token返回401"""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_http_client.get = AsyncMock(return_value=mock_response)
        
        keeper = TokenKeeper(http_client=mock_http_client)
        result = await keeper.check_token_validity("invalid_token")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_forbidden_token_403(self, mock_http_client):
        """测试权限不足返回403"""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_http_client.get = AsyncMock(return_value=mock_response)
        
        keeper = TokenKeeper(http_client=mock_http_client)
        result = await keeper.check_token_validity("forbidden_token")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_server_error_500(self, mock_http_client):
        """测试服务器错误返回500（保守处理，不认为Token失效）"""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_http_client.get = AsyncMock(return_value=mock_response)
        
        keeper = TokenKeeper(http_client=mock_http_client)
        result = await keeper.check_token_validity("some_token")
        
        # 服务器错误不应该导致Token被标记为失效
        assert result is True


class TestKeepAlive:
    """单Token保活测试"""
    
    @pytest.mark.asyncio
    async def test_keep_alive_success(self, token_service, mock_http_client):
        """测试保活成功"""
        # 创建测试Token
        token = token_service.create_or_update(
            token="test_token_12345678901234567890",
            user_id="test_user"
        )
        
        # 模拟成功响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_http_client.get = AsyncMock(return_value=mock_response)
        
        keeper = TokenKeeper(
            token_service=token_service,
            http_client=mock_http_client
        )
        
        result = await keeper.keep_alive(token.id, "test_token_12345678901234567890")
        
        assert result is True
        
        # 验证最后活跃时间已更新
        updated_token = token_service.get_by_id(token.id)
        assert updated_token.last_active_at is not None
    
    @pytest.mark.asyncio
    async def test_keep_alive_expired(self, token_service, mock_http_client):
        """测试保活失败导致Token过期"""
        # 创建测试Token
        token = token_service.create_or_update(
            token="test_token_12345678901234567890",
            user_id="test_user"
        )
        
        # 模拟401响应
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_http_client.get = AsyncMock(return_value=mock_response)
        
        keeper = TokenKeeper(
            token_service=token_service,
            http_client=mock_http_client
        )
        
        result = await keeper.keep_alive(token.id, "test_token_12345678901234567890")
        
        assert result is False
        
        # 验证Token状态已更新为过期
        updated_token = token_service.get_by_id(token.id)
        assert updated_token.status == TokenStatus.EXPIRED


class TestRunKeepAliveCycle:
    """保活循环测试"""
    
    @pytest.mark.asyncio
    async def test_cycle_no_tokens(self, token_service, mock_http_client):
        """测试没有Token时的保活循环"""
        keeper = TokenKeeper(
            token_service=token_service,
            http_client=mock_http_client
        )
        
        result = await keeper.run_keep_alive_cycle()
        
        assert result["total"] == 0
        assert result["success"] == 0
    
    @pytest.mark.asyncio
    async def test_cycle_with_tokens(self, token_service, mock_http_client):
        """测试有Token时的保活循环"""
        # 创建测试Token
        token_service.create_or_update(
            token="test_token_12345678901234567890",
            user_id="test_user_1"
        )
        token_service.create_or_update(
            token="test_token_09876543210987654321",
            user_id="test_user_2"
        )
        
        # 模拟成功响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_http_client.get = AsyncMock(return_value=mock_response)
        
        keeper = TokenKeeper(
            token_service=token_service,
            http_client=mock_http_client
        )
        
        result = await keeper.run_keep_alive_cycle()
        
        assert result["total"] == 2
        assert result["success"] == 2
        assert result["expired"] == 0


class TestNotifyTokenExpired:
    """Token失效通知测试"""
    
    @pytest.mark.asyncio
    async def test_notify_no_connection(self, websocket_manager):
        """测试没有连接时的通知"""
        keeper = TokenKeeper(websocket_manager=websocket_manager)
        
        result = await keeper.notify_token_expired("unknown_user", "Token已过期")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_notify_with_connection(self):
        """测试有连接时的通知"""
        # 创建模拟的WebSocket管理器
        mock_manager = MagicMock(spec=WebSocketManager)
        mock_conn = MagicMock(spec=ConnectionInfo)
        mock_conn.extension_id = "ext_123"
        mock_manager.get_connection_by_user = MagicMock(return_value=mock_conn)
        mock_manager.send_to_extension = AsyncMock(return_value=True)
        
        keeper = TokenKeeper(websocket_manager=mock_manager)
        
        result = await keeper.notify_token_expired("test_user", "Token已过期")
        
        assert result is True
        mock_manager.send_to_extension.assert_called_once()


class TestGlobalInstance:
    """全局实例测试"""
    
    def test_get_token_keeper(self):
        """测试获取全局实例"""
        keeper1 = get_token_keeper()
        keeper2 = get_token_keeper()
        
        assert keeper1 is keeper2
    
    def test_reset_token_keeper(self):
        """测试重置全局实例"""
        keeper1 = get_token_keeper()
        reset_token_keeper()
        keeper2 = get_token_keeper()
        
        assert keeper1 is not keeper2
