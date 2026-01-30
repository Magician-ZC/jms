"""
Token Keeper
Token保活服务模块

负责定时对所有活跃Token执行保活操作，包括：
- 定时保活循环
- 单Token保活
- Token有效性验证
- 失效通知推送

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 6.1
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Callable, Awaitable

import httpx

from .config import (
    KEEP_ALIVE_INTERVAL, 
    KEEP_ALIVE_URL, 
    AGENT_KEEP_ALIVE_URL,
    NETWORK_KEEP_ALIVE_URL,
    NETWORK_KEEP_ALIVE_HEADERS,
    NETWORK_KEEP_ALIVE_BODY,
    get_china_now
)
from .models import Token, TokenStatus, AccountType
from .token_service import TokenService, get_token_service
from .crypto_utils import decrypt_token, mask_token
from .websocket_manager import WebSocketManager, get_websocket_manager
from .message_protocol import create_token_expired_message

# 配置日志
logger = logging.getLogger(__name__)


class TokenKeeperError(Exception):
    """Token保活服务异常基类"""
    pass


class TokenKeeper:
    """
    Token保活服务
    
    定时对所有活跃状态的Token执行保活操作，防止Token因长时间未使用而过期。
    
    Features:
    - 可配置的保活间隔
    - 异步HTTP请求
    - 自动标记失效Token
    - WebSocket失效通知推送
    
    Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 6.1
    """
    
    # HTTP状态码
    HTTP_UNAUTHORIZED = 401
    HTTP_FORBIDDEN = 403
    
    def __init__(
        self,
        interval_seconds: int = KEEP_ALIVE_INTERVAL,
        token_service: Optional[TokenService] = None,
        websocket_manager: Optional[WebSocketManager] = None,
        http_client: Optional[httpx.AsyncClient] = None
    ):
        """
        初始化Token保活服务
        
        Args:
            interval_seconds: 保活间隔（秒），默认从配置读取
            token_service: Token服务实例，如果不提供则使用全局实例
            websocket_manager: WebSocket管理器实例，如果不提供则使用全局实例
            http_client: HTTP客户端实例，如果不提供则自动创建
        """
        self._interval = interval_seconds
        self._token_service = token_service
        self._websocket_manager = websocket_manager
        self._http_client = http_client
        self._owns_http_client = http_client is None
        
        # 运行状态
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # 统计信息
        self._stats = {
            "total_checks": 0,
            "successful_checks": 0,
            "failed_checks": 0,
            "expired_tokens": 0,
            "last_check_time": None
        }
        
        logger.info(f"TokenKeeper初始化完成, 保活间隔={interval_seconds}秒")
    
    @property
    def token_service(self) -> TokenService:
        """获取Token服务实例"""
        if self._token_service is None:
            self._token_service = get_token_service()
        return self._token_service
    
    @property
    def websocket_manager(self) -> WebSocketManager:
        """获取WebSocket管理器实例"""
        if self._websocket_manager is None:
            self._websocket_manager = get_websocket_manager()
        return self._websocket_manager
    
    @property
    def http_client(self) -> httpx.AsyncClient:
        """获取HTTP客户端实例"""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                follow_redirects=True
            )
        return self._http_client
    
    @property
    def is_running(self) -> bool:
        """检查服务是否正在运行"""
        return self._running
    
    @property
    def interval(self) -> int:
        """获取保活间隔（秒）"""
        return self._interval
    
    @property
    def stats(self) -> dict:
        """获取统计信息"""
        return self._stats.copy()

    async def start(self) -> None:
        """
        启动保活服务
        
        开始定时保活循环，如果服务已在运行则忽略
        
        Requirements: 5.1
        """
        if self._running:
            logger.warning("TokenKeeper已在运行，忽略重复启动")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._keep_alive_loop())
        logger.info("TokenKeeper保活服务已启动")
    
    async def stop(self) -> None:
        """
        停止保活服务
        
        停止定时保活循环并清理资源
        """
        if not self._running:
            logger.warning("TokenKeeper未在运行，忽略停止请求")
            return
        
        self._running = False
        
        # 取消任务
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        
        # 关闭HTTP客户端
        if self._owns_http_client and self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        
        logger.info("TokenKeeper保活服务已停止")
    
    async def _keep_alive_loop(self) -> None:
        """
        保活循环
        
        定时执行保活操作
        
        Requirements: 5.1
        """
        logger.info(f"保活循环开始，间隔={self._interval}秒")
        
        while self._running:
            try:
                # 等待指定间隔
                await asyncio.sleep(self._interval)
                
                if not self._running:
                    break
                
                # 执行一轮保活
                await self.run_keep_alive_cycle()
                
            except asyncio.CancelledError:
                logger.info("保活循环被取消")
                break
            except Exception as e:
                logger.error(f"保活循环出错: {str(e)}")
                # 继续运行，不因单次错误停止服务
    
    async def run_keep_alive_cycle(self) -> dict:
        """
        执行一轮保活循环
        
        获取所有活跃Token并逐个执行保活操作
        
        Returns:
            dict: 本轮保活结果统计
            
        Requirements: 5.1, 5.2
        """
        logger.info("开始执行保活循环")
        
        cycle_stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "expired": 0
        }
        
        try:
            # 获取所有活跃Token
            active_tokens = self.token_service.get_active_tokens()
            cycle_stats["total"] = len(active_tokens)
            
            if not active_tokens:
                logger.info("没有活跃Token需要保活")
                return cycle_stats
            
            logger.info(f"发现{len(active_tokens)}个活跃Token需要保活")
            
            # 逐个执行保活
            for token in active_tokens:
                try:
                    # 解密Token
                    decrypted_token = decrypt_token(token.token_value)
                    
                    # 获取账号类型
                    account_type = token.account_type or AccountType.AGENT
                    
                    # 执行保活
                    is_valid = await self.keep_alive(token.id, decrypted_token, account_type)
                    
                    if is_valid:
                        cycle_stats["success"] += 1
                        self._stats["successful_checks"] += 1
                    else:
                        cycle_stats["expired"] += 1
                        self._stats["expired_tokens"] += 1
                        
                        # 发送失效通知
                        await self.notify_token_expired(token.user_id, "保活检测失败，Token已过期")
                        
                except Exception as e:
                    logger.error(f"Token保活失败: user_id={token.user_id}, type={token.account_type}, error={str(e)}")
                    cycle_stats["failed"] += 1
                    self._stats["failed_checks"] += 1
            
            # 更新统计
            self._stats["total_checks"] += cycle_stats["total"]
            self._stats["last_check_time"] = get_china_now().isoformat()
            
            logger.info(
                f"保活循环完成: 总数={cycle_stats['total']}, "
                f"成功={cycle_stats['success']}, "
                f"失效={cycle_stats['expired']}, "
                f"失败={cycle_stats['failed']}"
            )
            
            return cycle_stats
            
        except Exception as e:
            logger.error(f"保活循环执行失败: {str(e)}")
            raise TokenKeeperError(f"保活循环执行失败: {str(e)}")
    
    async def keep_alive(self, token_id: int, token: str, account_type: AccountType = AccountType.AGENT) -> bool:
        """
        执行单个Token的保活操作
        
        根据账号类型使用不同的保活策略：
        - 代理区(agent): 访问数据平台页面
        - 网点(network): 调用轻量级API
        
        Args:
            token_id: Token ID
            token: 解密后的Token值
            account_type: 账号类型
            
        Returns:
            bool: Token是否有效
            
        Requirements: 5.2, 5.3, 5.4
        """
        logger.debug(f"执行Token保活: id={token_id}, type={account_type.value}, token={mask_token(token)}")
        
        try:
            # 根据账号类型选择保活方式
            if account_type == AccountType.NETWORK:
                is_valid = await self.check_network_token_validity(token)
            else:
                is_valid = await self.check_token_validity(token)
            
            if is_valid:
                # Token有效，更新最后活跃时间
                self.token_service.update_last_active(token_id)
                logger.info(f"Token保活成功: id={token_id}, type={account_type.value}")
                return True
            else:
                # Token无效，标记为过期
                self.token_service.update_status(token_id, TokenStatus.EXPIRED)
                logger.warning(f"Token已过期: id={token_id}, type={account_type.value}")
                return False
                
        except Exception as e:
            logger.error(f"Token保活操作失败: id={token_id}, error={str(e)}")
            # 保活失败不改变Token状态，等待下次重试
            raise
    
    async def check_token_validity(self, token: str) -> bool:
        """
        检查代理区Token是否有效
        
        通过访问数据平台页面验证Token的有效性（模拟点击"数据平台"）
        
        Args:
            token: Token值
            
        Returns:
            bool: Token是否有效
            
        Requirements: 5.2
        """
        api_url = AGENT_KEEP_ALIVE_URL
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://jms.jtexpress.com.cn/"
        }
        
        try:
            response = await self.http_client.get(api_url, headers=headers)
            return self._check_response_validity(response, token)
            
        except httpx.TimeoutException:
            logger.warning(f"代理区保活请求超时: token={mask_token(token)}")
            return True  # 超时不认为Token失效
            
        except httpx.RequestError as e:
            logger.error(f"代理区保活请求失败: {str(e)}")
            return True  # 网络错误不认为Token失效

    async def check_network_token_validity(self, token: str) -> bool:
        """
        检查网点Token是否有效
        
        通过调用网点轻量级API验证Token的有效性
        
        Args:
            token: Token值
            
        Returns:
            bool: Token是否有效
        """
        api_url = NETWORK_KEEP_ALIVE_URL
        
        # 构建请求头
        headers = {
            **NETWORK_KEEP_ALIVE_HEADERS,
            "authToken": token,  # 网点使用驼峰命名
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        
        # 构建请求体（添加动态日期）
        now = get_china_now()
        body = {
            **NETWORK_KEEP_ALIVE_BODY,
            "startDate": now.strftime("%Y-%m-01"),
            "endDate": now.strftime("%Y-%m-%d"),
        }
        
        try:
            response = await self.http_client.post(api_url, headers=headers, json=body)
            
            # 检查响应
            if response.status_code == self.HTTP_UNAUTHORIZED:
                logger.warning(f"网点Token认证失败(401): token={mask_token(token)}")
                return False
            
            if response.status_code == self.HTTP_FORBIDDEN:
                logger.warning(f"网点Token权限不足(403): token={mask_token(token)}")
                return False
            
            # 检查业务响应
            if response.status_code == 200:
                try:
                    data = response.json()
                    # 网点API返回 code=1 表示成功
                    if data.get("code") == 1 or data.get("succ") is True:
                        logger.debug(f"网点Token验证成功: token={mask_token(token)}")
                        return True
                    else:
                        logger.warning(f"网点Token验证失败: code={data.get('code')}, msg={data.get('msg')}")
                        return False
                except Exception:
                    pass
            
            # 2xx状态码但无法解析响应，保守处理
            if 200 <= response.status_code < 300:
                return True
            
            logger.warning(f"网点保活请求返回异常状态码: {response.status_code}")
            return True  # 保守处理
            
        except httpx.TimeoutException:
            logger.warning(f"网点保活请求超时: token={mask_token(token)}")
            return True
            
        except httpx.RequestError as e:
            logger.error(f"网点保活请求失败: {str(e)}")
            return True

    def _check_response_validity(self, response: httpx.Response, token: str) -> bool:
        """检查HTTP响应判断Token有效性"""
        if response.status_code == self.HTTP_UNAUTHORIZED:
            logger.warning(f"Token认证失败(401): token={mask_token(token)}")
            return False
        
        if response.status_code == self.HTTP_FORBIDDEN:
            logger.warning(f"Token权限不足(403): token={mask_token(token)}")
            return False
        
        if 200 <= response.status_code < 400:
            logger.debug(f"Token验证成功: token={mask_token(token)}, status={response.status_code}")
            return True
        
        logger.warning(f"保活请求返回异常状态码: {response.status_code}")
        return True  # 保守处理

    async def notify_token_expired(self, user_id: str, reason: str = "Token已过期") -> bool:
        """
        发送Token失效通知
        
        通过WebSocket向关联的Chrome Extension发送Token失效通知
        
        Args:
            user_id: 用户标识
            reason: 失效原因
            
        Returns:
            bool: 是否成功发送通知
            
        Requirements: 6.1
        """
        logger.info(f"发送Token失效通知: user_id={user_id}, reason={reason}")
        
        try:
            # 查找用户关联的WebSocket连接
            conn_info = self.websocket_manager.get_connection_by_user(user_id)
            
            if conn_info is None:
                logger.warning(f"未找到用户的WebSocket连接: user_id={user_id}")
                return False
            
            # 创建失效通知消息
            message = create_token_expired_message(user_id, reason)
            
            # 发送消息
            success = await self.websocket_manager.send_to_extension(
                conn_info.extension_id,
                message
            )
            
            if success:
                logger.info(f"Token失效通知已发送: user_id={user_id}, extension_id={conn_info.extension_id}")
            else:
                logger.warning(f"Token失效通知发送失败: user_id={user_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"发送Token失效通知失败: user_id={user_id}, error={str(e)}")
            return False
    
    async def notify_all_expired_tokens(self) -> int:
        """
        通知所有已过期Token的用户
        
        遍历所有过期状态的Token，向关联的插件发送失效通知
        
        Returns:
            int: 成功发送通知的数量
        """
        success_count = 0
        
        try:
            # 获取所有Token（包括过期的）
            all_tokens = self.token_service.get_all(include_expired=True)
            
            # 筛选过期Token
            expired_tokens = [t for t in all_tokens if t.status == TokenStatus.EXPIRED]
            
            if not expired_tokens:
                logger.info("没有过期Token需要通知")
                return 0
            
            logger.info(f"发现{len(expired_tokens)}个过期Token需要通知")
            
            for token in expired_tokens:
                if await self.notify_token_expired(token.user_id, "Token已过期"):
                    success_count += 1
            
            logger.info(f"过期Token通知完成: 成功={success_count}/{len(expired_tokens)}")
            return success_count
            
        except Exception as e:
            logger.error(f"批量发送过期通知失败: {str(e)}")
            return success_count
    
    def set_interval(self, interval_seconds: int) -> None:
        """
        设置保活间隔
        
        Args:
            interval_seconds: 新的保活间隔（秒）
        """
        if interval_seconds < 60:
            logger.warning(f"保活间隔过短，建议至少60秒: {interval_seconds}")
        
        self._interval = interval_seconds
        logger.info(f"保活间隔已更新: {interval_seconds}秒")
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        self._stats = {
            "total_checks": 0,
            "successful_checks": 0,
            "failed_checks": 0,
            "expired_tokens": 0,
            "last_check_time": None
        }
        logger.info("统计信息已重置")


# 全局TokenKeeper实例（单例模式）
_keeper_instance: Optional[TokenKeeper] = None


def get_token_keeper() -> TokenKeeper:
    """
    获取全局TokenKeeper实例
    
    Returns:
        TokenKeeper: 保活服务实例
    """
    global _keeper_instance
    if _keeper_instance is None:
        _keeper_instance = TokenKeeper()
    return _keeper_instance


def reset_token_keeper() -> None:
    """
    重置全局TokenKeeper实例（主要用于测试）
    """
    global _keeper_instance
    _keeper_instance = None
