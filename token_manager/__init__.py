"""
Token Management System
Token管理系统 - 用于管理JMS平台的用户认证Token
"""

__version__ = "1.0.0"

# 导出核心组件
from .models import Token, TokenStatus, ExtensionConnection, init_database, close_database
from .token_service import TokenService, get_token_service, TokenServiceError
from .websocket_manager import WebSocketManager, get_websocket_manager, ConnectionInfo
from .token_keeper import TokenKeeper, get_token_keeper, TokenKeeperError
from .crypto_utils import encrypt_token, decrypt_token, mask_token
from .validators import validate_token, validate_user_id
from .message_protocol import (
    MessageType,
    create_register_message,
    create_register_ack_message,
    create_token_upload_message,
    create_token_ack_message,
    create_heartbeat_message,
    create_heartbeat_ack_message,
    create_token_expired_message,
    create_error_message,
    parse_message,
    validate_message
)
from .main import TokenManagerService, run_server

__all__ = [
    # 版本
    "__version__",
    # 模型
    "Token",
    "TokenStatus",
    "ExtensionConnection",
    "init_database",
    "close_database",
    # Token服务
    "TokenService",
    "get_token_service",
    "TokenServiceError",
    # WebSocket管理
    "WebSocketManager",
    "get_websocket_manager",
    "ConnectionInfo",
    # Token保活
    "TokenKeeper",
    "get_token_keeper",
    "TokenKeeperError",
    # 加密工具
    "encrypt_token",
    "decrypt_token",
    "mask_token",
    # 验证器
    "validate_token",
    "validate_user_id",
    # 消息协议
    "MessageType",
    "create_register_message",
    "create_register_ack_message",
    "create_token_upload_message",
    "create_token_ack_message",
    "create_heartbeat_message",
    "create_heartbeat_ack_message",
    "create_token_expired_message",
    "create_error_message",
    "parse_message",
    "validate_message",
    # 服务入口
    "TokenManagerService",
    "run_server",
]
