"""
WebSocket Manager
WebSocket连接管理器模块

负责管理所有Chrome Extension的WebSocket连接，包括：
- 连接建立与断开
- 消息定向发送与广播
- 心跳检测与超时处理
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, field

from fastapi import WebSocket, WebSocketDisconnect

from .config import WS_HEARTBEAT_INTERVAL, get_china_now

# 配置日志
logger = logging.getLogger(__name__)


@dataclass
class ConnectionInfo:
    """
    WebSocket连接信息
    
    存储单个插件连接的所有相关信息
    """
    websocket: WebSocket
    extension_id: str
    user_id: Optional[str] = None
    connected_at: datetime = field(default_factory=get_china_now)
    last_heartbeat: datetime = field(default_factory=get_china_now)
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "extension_id": self.extension_id,
            "user_id": self.user_id,
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
        }


class WebSocketManager:
    """
    WebSocket连接管理器
    
    管理所有已连接的Chrome Extension，提供：
    - 连接管理（connect/disconnect）
    - 消息发送（定向/广播）
    - 心跳检测
    
    Requirements: 7.1, 7.2, 7.3, 7.4, 7.6
    """
    
    def __init__(self, heartbeat_interval: int = WS_HEARTBEAT_INTERVAL):
        """
        初始化WebSocket管理器
        
        Args:
            heartbeat_interval: 心跳检测间隔（秒），默认从配置读取
        """
        # 存储所有连接，key为extension_id
        self._connections: Dict[str, ConnectionInfo] = {}
        # 心跳检测间隔
        self._heartbeat_interval = heartbeat_interval
        # 心跳检测任务
        self._heartbeat_task: Optional[asyncio.Task] = None
        # 运行状态
        self._running = False
        # 锁，用于线程安全
        self._lock = asyncio.Lock()
        
        logger.info(f"WebSocket管理器初始化完成, 心跳间隔={heartbeat_interval}秒")
    
    async def connect(self, websocket: WebSocket, extension_id: str) -> bool:
        """
        接受新的WebSocket连接
        
        Args:
            websocket: FastAPI WebSocket对象
            extension_id: 插件唯一标识
            
        Returns:
            bool: 连接是否成功
            
        Requirements: 7.1, 7.3
        """
        async with self._lock:
            try:
                # 接受WebSocket连接
                await websocket.accept()
                
                # 检查是否已存在该插件的连接
                if extension_id in self._connections:
                    # 关闭旧连接
                    old_conn = self._connections[extension_id]
                    try:
                        await old_conn.websocket.close(code=1000, reason="新连接替换")
                    except Exception:
                        pass  # 忽略关闭旧连接时的错误
                    logger.info(f"替换已存在的连接: extension_id={extension_id}")
                
                # 创建新的连接信息
                conn_info = ConnectionInfo(
                    websocket=websocket,
                    extension_id=extension_id,
                    connected_at=get_china_now(),
                    last_heartbeat=get_china_now()
                )
                
                # 存储连接
                self._connections[extension_id] = conn_info
                
                logger.info(f"新连接建立: extension_id={extension_id}, 当前连接数={len(self._connections)}")
                return True
                
            except Exception as e:
                logger.error(f"建立连接失败: extension_id={extension_id}, error={str(e)}")
                return False
    
    async def disconnect(self, extension_id: str) -> bool:
        """
        断开指定插件的连接
        
        Args:
            extension_id: 插件唯一标识
            
        Returns:
            bool: 是否成功断开
            
        Requirements: 7.3
        """
        async with self._lock:
            if extension_id not in self._connections:
                logger.warning(f"断开连接失败: 连接不存在, extension_id={extension_id}")
                return False
            
            conn_info = self._connections.pop(extension_id)
            
            try:
                await conn_info.websocket.close(code=1000, reason="正常断开")
            except Exception as e:
                logger.debug(f"关闭WebSocket时出错（可忽略）: {str(e)}")
            
            logger.info(f"连接已断开: extension_id={extension_id}, 当前连接数={len(self._connections)}")
            return True
    
    async def send_to_extension(self, extension_id: str, message: dict) -> bool:
        """
        向指定插件发送消息
        
        Args:
            extension_id: 目标插件标识
            message: 要发送的消息（字典格式）
            
        Returns:
            bool: 是否发送成功
            
        Requirements: 7.4
        """
        async with self._lock:
            if extension_id not in self._connections:
                logger.warning(f"发送消息失败: 连接不存在, extension_id={extension_id}")
                return False
            
            conn_info = self._connections[extension_id]
        
        try:
            await conn_info.websocket.send_json(message)
            logger.debug(f"消息已发送: extension_id={extension_id}, type={message.get('type', 'unknown')}")
            return True
        except Exception as e:
            logger.error(f"发送消息失败: extension_id={extension_id}, error={str(e)}")
            # 发送失败，移除该连接
            await self.disconnect(extension_id)
            return False
    
    async def broadcast(self, message: dict, exclude: Optional[List[str]] = None) -> int:
        """
        广播消息给所有连接的插件
        
        Args:
            message: 要广播的消息（字典格式）
            exclude: 要排除的插件ID列表
            
        Returns:
            int: 成功发送的数量
            
        Requirements: 7.4
        """
        exclude = exclude or []
        success_count = 0
        failed_extensions = []
        
        # 获取所有需要发送的连接
        async with self._lock:
            targets = [
                (ext_id, conn_info)
                for ext_id, conn_info in self._connections.items()
                if ext_id not in exclude
            ]
        
        # 发送消息
        for ext_id, conn_info in targets:
            try:
                await conn_info.websocket.send_json(message)
                success_count += 1
            except Exception as e:
                logger.error(f"广播消息失败: extension_id={ext_id}, error={str(e)}")
                failed_extensions.append(ext_id)
        
        # 清理失败的连接
        for ext_id in failed_extensions:
            await self.disconnect(ext_id)
        
        logger.info(f"广播完成: 成功={success_count}, 失败={len(failed_extensions)}, type={message.get('type', 'unknown')}")
        return success_count
    
    def update_heartbeat(self, extension_id: str) -> bool:
        """
        更新指定插件的心跳时间
        
        Args:
            extension_id: 插件标识
            
        Returns:
            bool: 是否更新成功
            
        Requirements: 7.6
        """
        if extension_id not in self._connections:
            return False
        
        self._connections[extension_id].last_heartbeat = get_china_now()
        logger.debug(f"心跳更新: extension_id={extension_id}")
        return True
    
    def set_user_id(self, extension_id: str, user_id: str) -> bool:
        """
        设置连接关联的用户ID
        
        Args:
            extension_id: 插件标识
            user_id: 用户标识
            
        Returns:
            bool: 是否设置成功
        """
        if extension_id not in self._connections:
            return False
        
        self._connections[extension_id].user_id = user_id
        logger.info(f"关联用户: extension_id={extension_id}, user_id={user_id}")
        return True
    
    def get_connection(self, extension_id: str) -> Optional[ConnectionInfo]:
        """
        获取指定插件的连接信息
        
        Args:
            extension_id: 插件标识
            
        Returns:
            Optional[ConnectionInfo]: 连接信息，不存在则返回None
        """
        return self._connections.get(extension_id)
    
    def get_connection_by_user(self, user_id: str) -> Optional[ConnectionInfo]:
        """
        根据用户ID获取连接信息
        
        Args:
            user_id: 用户标识
            
        Returns:
            Optional[ConnectionInfo]: 连接信息，不存在则返回None
        """
        for conn_info in self._connections.values():
            if conn_info.user_id == user_id:
                return conn_info
        return None
    
    def get_all_connections(self) -> List[ConnectionInfo]:
        """
        获取所有连接信息
        
        Returns:
            List[ConnectionInfo]: 所有连接信息列表
        """
        return list(self._connections.values())
    
    def get_connection_count(self) -> int:
        """
        获取当前连接数量
        
        Returns:
            int: 连接数量
        """
        return len(self._connections)
    
    def is_connected(self, extension_id: str) -> bool:
        """
        检查指定插件是否已连接
        
        Args:
            extension_id: 插件标识
            
        Returns:
            bool: 是否已连接
        """
        return extension_id in self._connections

    
    async def start_heartbeat_checker(self) -> None:
        """
        启动心跳检测任务
        
        定期检查所有连接的心跳状态，断开超时的连接
        
        Requirements: 7.6
        """
        if self._running:
            logger.warning("心跳检测任务已在运行")
            return
        
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("心跳检测任务已启动")
    
    async def stop_heartbeat_checker(self) -> None:
        """
        停止心跳检测任务
        """
        self._running = False
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
        
        logger.info("心跳检测任务已停止")
    
    async def _heartbeat_loop(self) -> None:
        """
        心跳检测循环
        
        每隔一定时间检查所有连接的心跳状态
        """
        # 超时阈值：心跳间隔的3倍
        timeout_threshold = self._heartbeat_interval * 3
        
        while self._running:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                
                if not self._running:
                    break
                
                await self._check_heartbeats(timeout_threshold)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"心跳检测循环出错: {str(e)}")
    
    async def _check_heartbeats(self, timeout_threshold: int) -> None:
        """
        检查所有连接的心跳状态
        
        Args:
            timeout_threshold: 超时阈值（秒）
        """
        now = get_china_now()
        expired_extensions = []
        
        # 检查所有连接
        async with self._lock:
            for ext_id, conn_info in self._connections.items():
                elapsed = (now - conn_info.last_heartbeat).total_seconds()
                if elapsed > timeout_threshold:
                    expired_extensions.append(ext_id)
                    logger.warning(f"连接心跳超时: extension_id={ext_id}, elapsed={elapsed:.1f}秒")
        
        # 断开超时的连接
        for ext_id in expired_extensions:
            await self.disconnect(ext_id)
            logger.info(f"已断开超时连接: extension_id={ext_id}")
    
    async def close_all(self) -> None:
        """
        关闭所有连接并停止心跳检测
        """
        # 停止心跳检测
        await self.stop_heartbeat_checker()
        
        # 关闭所有连接
        async with self._lock:
            for ext_id, conn_info in list(self._connections.items()):
                try:
                    await conn_info.websocket.close(code=1001, reason="服务器关闭")
                except Exception:
                    pass
            self._connections.clear()
        
        logger.info("所有WebSocket连接已关闭")


# 全局WebSocket管理器实例（单例模式）
_manager_instance: Optional[WebSocketManager] = None


def get_websocket_manager() -> WebSocketManager:
    """
    获取全局WebSocket管理器实例
    
    Returns:
        WebSocketManager: 管理器实例
    """
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = WebSocketManager()
    return _manager_instance


def reset_websocket_manager() -> None:
    """
    重置全局WebSocket管理器实例（主要用于测试）
    """
    global _manager_instance
    _manager_instance = None
