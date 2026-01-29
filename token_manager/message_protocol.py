"""
Message Protocol
WebSocket消息协议处理模块

定义插件与服务器之间的消息格式和处理逻辑，包括：
- 消息类型定义
- 消息序列化/反序列化
- 各类消息的创建函数

Requirements: 7.2
"""

import json
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, Union
from dataclasses import dataclass, asdict

from .config import get_china_now

# 配置日志
logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    """
    消息类型枚举
    
    定义所有支持的消息类型
    """
    # 插件到服务器
    REGISTER = "register"           # 注册消息
    TOKEN_UPLOAD = "token_upload"   # Token上报
    HEARTBEAT = "heartbeat"         # 心跳消息
    
    # 服务器到插件
    REGISTER_ACK = "register_ack"   # 注册确认
    TOKEN_ACK = "token_ack"         # Token上报确认
    TOKEN_EXPIRED = "token_expired" # Token失效通知
    TOKEN_DELETED = "token_deleted" # Token删除通知
    HEARTBEAT_ACK = "heartbeat_ack" # 心跳确认
    ERROR = "error"                 # 错误消息


class TokenSource(str, Enum):
    """Token来源枚举"""
    RESPONSE = "response"
    COOKIE = "cookie"
    LOCAL_STORAGE = "localStorage"


@dataclass
class BaseMessage:
    """
    消息基类
    
    所有消息都包含类型和时间戳
    """
    type: str
    timestamp: int  # Unix时间戳（毫秒）
    payload: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "type": self.type,
            "timestamp": self.timestamp,
            "payload": self.payload
        }
    
    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False)


def get_timestamp() -> int:
    """
    获取当前时间戳（毫秒）- 使用中国时间
    
    Returns:
        int: Unix时间戳（毫秒）
    """
    return int(get_china_now().timestamp() * 1000)


# ============== 消息创建函数 ==============

def create_register_message(extension_id: str, version: str = "1.0.0") -> Dict[str, Any]:
    """
    创建注册消息
    
    插件连接后发送此消息进行注册
    
    Args:
        extension_id: 插件唯一标识
        version: 插件版本号
        
    Returns:
        Dict: 注册消息字典
    """
    return {
        "type": MessageType.REGISTER.value,
        "timestamp": get_timestamp(),
        "payload": {
            "extensionId": extension_id,
            "version": version
        }
    }


def create_register_ack_message(success: bool, message: str = "") -> Dict[str, Any]:
    """
    创建注册确认消息
    
    服务器响应插件的注册请求
    
    Args:
        success: 注册是否成功
        message: 附加消息
        
    Returns:
        Dict: 注册确认消息字典
    """
    return {
        "type": MessageType.REGISTER_ACK.value,
        "timestamp": get_timestamp(),
        "payload": {
            "success": success,
            "message": message
        }
    }


def create_token_upload_message(
    token: str,
    user_id: str,
    source: Union[TokenSource, str] = TokenSource.RESPONSE
) -> Dict[str, Any]:
    """
    创建Token上报消息
    
    插件获取到Token后发送此消息
    
    Args:
        token: Token值
        user_id: 用户标识
        source: Token来源
        
    Returns:
        Dict: Token上报消息字典
    """
    if isinstance(source, TokenSource):
        source = source.value
    
    return {
        "type": MessageType.TOKEN_UPLOAD.value,
        "timestamp": get_timestamp(),
        "payload": {
            "token": token,
            "userId": user_id,
            "source": source
        }
    }


def create_token_ack_message(success: bool, token_id: Optional[int] = None, message: str = "") -> Dict[str, Any]:
    """
    创建Token上报确认消息
    
    服务器响应插件的Token上报
    
    Args:
        success: 是否成功
        token_id: 存储后的Token ID
        message: 附加消息
        
    Returns:
        Dict: Token确认消息字典
    """
    payload = {
        "success": success,
        "message": message
    }
    if token_id is not None:
        payload["tokenId"] = token_id
    
    return {
        "type": MessageType.TOKEN_ACK.value,
        "timestamp": get_timestamp(),
        "payload": payload
    }


def create_heartbeat_message(extension_id: str) -> Dict[str, Any]:
    """
    创建心跳消息
    
    插件定期发送心跳保持连接
    
    Args:
        extension_id: 插件标识
        
    Returns:
        Dict: 心跳消息字典
    """
    return {
        "type": MessageType.HEARTBEAT.value,
        "timestamp": get_timestamp(),
        "payload": {
            "extensionId": extension_id
        }
    }


def create_heartbeat_ack_message() -> Dict[str, Any]:
    """
    创建心跳确认消息
    
    服务器响应插件的心跳
    
    Returns:
        Dict: 心跳确认消息字典
    """
    return {
        "type": MessageType.HEARTBEAT_ACK.value,
        "timestamp": get_timestamp(),
        "payload": {}
    }


def create_token_expired_message(user_id: str, reason: str = "Token已过期") -> Dict[str, Any]:
    """
    创建Token失效通知消息
    
    服务器检测到Token失效后发送给插件
    
    Args:
        user_id: 用户标识
        reason: 失效原因
        
    Returns:
        Dict: Token失效消息字典
    """
    return {
        "type": MessageType.TOKEN_EXPIRED.value,
        "timestamp": get_timestamp(),
        "payload": {
            "userId": user_id,
            "reason": reason
        }
    }


def create_token_deleted_message(user_id: str, reason: str = "Token已被管理员删除") -> Dict[str, Any]:
    """
    创建Token删除通知消息
    
    服务器删除Token后发送给对应的插件
    
    Args:
        user_id: 用户标识
        reason: 删除原因
        
    Returns:
        Dict: Token删除消息字典
    """
    return {
        "type": MessageType.TOKEN_DELETED.value,
        "timestamp": get_timestamp(),
        "payload": {
            "userId": user_id,
            "reason": reason
        }
    }


def create_error_message(code: int, message: str, details: Optional[Dict] = None) -> Dict[str, Any]:
    """
    创建错误消息
    
    服务器发送错误信息给插件
    
    Args:
        code: 错误代码
        message: 错误消息
        details: 错误详情
        
    Returns:
        Dict: 错误消息字典
    """
    payload = {
        "code": code,
        "message": message
    }
    if details:
        payload["details"] = details
    
    return {
        "type": MessageType.ERROR.value,
        "timestamp": get_timestamp(),
        "payload": payload
    }


# ============== 消息解析函数 ==============

class MessageParseError(Exception):
    """消息解析异常"""
    pass


class MessageValidationError(Exception):
    """消息验证异常"""
    pass


def parse_message(data: Union[str, bytes, Dict]) -> Dict[str, Any]:
    """
    解析消息
    
    将原始数据解析为消息字典
    
    Args:
        data: 原始消息数据（JSON字符串、字节或字典）
        
    Returns:
        Dict: 解析后的消息字典
        
    Raises:
        MessageParseError: 解析失败
    """
    try:
        if isinstance(data, dict):
            return data
        
        if isinstance(data, bytes):
            data = data.decode('utf-8')
        
        return json.loads(data)
    except json.JSONDecodeError as e:
        logger.error(f"消息JSON解析失败: {str(e)}")
        raise MessageParseError(f"无效的JSON格式: {str(e)}")
    except Exception as e:
        logger.error(f"消息解析失败: {str(e)}")
        raise MessageParseError(f"消息解析失败: {str(e)}")


def validate_message(message: Dict[str, Any]) -> bool:
    """
    验证消息格式
    
    检查消息是否包含必要字段
    
    Args:
        message: 消息字典
        
    Returns:
        bool: 是否有效
        
    Raises:
        MessageValidationError: 验证失败
    """
    # 检查必要字段
    if "type" not in message:
        raise MessageValidationError("消息缺少type字段")
    
    if "timestamp" not in message:
        raise MessageValidationError("消息缺少timestamp字段")
    
    if "payload" not in message:
        raise MessageValidationError("消息缺少payload字段")
    
    # 检查类型是否有效
    msg_type = message["type"]
    valid_types = [t.value for t in MessageType]
    if msg_type not in valid_types:
        raise MessageValidationError(f"无效的消息类型: {msg_type}")
    
    return True


def validate_register_payload(payload: Dict[str, Any]) -> bool:
    """
    验证注册消息的payload
    
    Args:
        payload: 消息payload
        
    Returns:
        bool: 是否有效
        
    Raises:
        MessageValidationError: 验证失败
    """
    if "extensionId" not in payload:
        raise MessageValidationError("注册消息缺少extensionId")
    
    if not payload["extensionId"] or not isinstance(payload["extensionId"], str):
        raise MessageValidationError("extensionId必须是非空字符串")
    
    return True


def validate_token_upload_payload(payload: Dict[str, Any]) -> bool:
    """
    验证Token上报消息的payload
    
    Args:
        payload: 消息payload
        
    Returns:
        bool: 是否有效
        
    Raises:
        MessageValidationError: 验证失败
    """
    required_fields = ["token", "userId"]
    
    for field in required_fields:
        if field not in payload:
            raise MessageValidationError(f"Token上报消息缺少{field}")
        
        if not payload[field] or not isinstance(payload[field], str):
            raise MessageValidationError(f"{field}必须是非空字符串")
    
    # 验证source（可选）
    if "source" in payload:
        valid_sources = [s.value for s in TokenSource]
        if payload["source"] not in valid_sources:
            raise MessageValidationError(f"无效的Token来源: {payload['source']}")
    
    return True


def validate_heartbeat_payload(payload: Dict[str, Any]) -> bool:
    """
    验证心跳消息的payload
    
    Args:
        payload: 消息payload
        
    Returns:
        bool: 是否有效
        
    Raises:
        MessageValidationError: 验证失败
    """
    if "extensionId" not in payload:
        raise MessageValidationError("心跳消息缺少extensionId")
    
    return True


def get_message_type(message: Dict[str, Any]) -> Optional[MessageType]:
    """
    获取消息类型
    
    Args:
        message: 消息字典
        
    Returns:
        Optional[MessageType]: 消息类型枚举，无效则返回None
    """
    msg_type = message.get("type")
    if not msg_type:
        return None
    
    try:
        return MessageType(msg_type)
    except ValueError:
        return None


def serialize_message(message: Dict[str, Any]) -> str:
    """
    序列化消息为JSON字符串
    
    Args:
        message: 消息字典
        
    Returns:
        str: JSON字符串
    """
    return json.dumps(message, ensure_ascii=False)


def deserialize_message(data: str) -> Dict[str, Any]:
    """
    反序列化JSON字符串为消息字典
    
    Args:
        data: JSON字符串
        
    Returns:
        Dict: 消息字典
        
    Raises:
        MessageParseError: 解析失败
    """
    return parse_message(data)
