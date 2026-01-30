"""
Token Service
Token服务核心逻辑模块
"""

import logging
from datetime import datetime
from typing import Optional, List

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from .models import Token, TokenStatus, get_db_session, init_database
from .crypto_utils import encrypt_token, decrypt_token, mask_token
from .validators import validate_token, validate_user_id
from .config import get_china_now

# 配置日志
logger = logging.getLogger(__name__)


class TokenServiceError(Exception):
    """Token服务异常基类"""
    pass


class TokenValidationError(TokenServiceError):
    """Token验证异常"""
    pass


class TokenNotFoundError(TokenServiceError):
    """Token未找到异常"""
    pass


class TokenService:
    """
    Token服务类
    
    提供Token的CRUD操作，包括：
    - 创建或更新Token（幂等存储）
    - 获取所有Token
    - 根据用户ID获取Token
    - 删除Token
    - 更新Token状态
    - 更新最后活跃时间
    """
    
    def __init__(self, session: Optional[Session] = None):
        """
        初始化Token服务
        
        Args:
            session: 可选的数据库会话，如果不提供则自动创建
        """
        self._session = session
        self._owns_session = session is None
        
        # 确保数据库已初始化
        init_database()
    
    @property
    def session(self) -> Session:
        """获取数据库会话"""
        if self._session is None:
            self._session = get_db_session()
        return self._session
    
    def close(self):
        """关闭服务，释放资源"""
        if self._owns_session and self._session is not None:
            self._session.close()
            self._session = None

    def create_or_update(
        self,
        token: str,
        user_id: str,
        extension_id: Optional[str] = None,
        account: Optional[str] = None
    ) -> Token:
        """
        创建或更新Token（幂等存储）
        
        如果用户已存在Token，则更新；否则创建新记录。
        Token会被加密后存储。
        
        Args:
            token: 原始Token字符串
            user_id: 用户标识
            extension_id: 可选的插件标识
            account: 可选的登录账号
            
        Returns:
            Token: 创建或更新后的Token对象
            
        Raises:
            TokenValidationError: Token或用户ID格式无效
            TokenServiceError: 数据库操作失败
        """
        # 验证Token格式
        valid, error_msg = validate_token(token)
        if not valid:
            logger.warning(f"Token验证失败: {error_msg}, token={mask_token(token)}")
            raise TokenValidationError(error_msg)
        
        # 验证用户ID
        valid, error_msg = validate_user_id(user_id)
        if not valid:
            logger.warning(f"用户ID验证失败: {error_msg}")
            raise TokenValidationError(error_msg)
        
        # 清理输入
        token = token.strip()
        user_id = user_id.strip()
        if account:
            account = account.strip()
            # user_id 使用 account 的值
            user_id = account
        
        try:
            # 加密Token
            encrypted_token = encrypt_token(token)
            
            # 按 account 查找现有记录（account 是唯一标识）
            existing = None
            if account:
                existing = self.session.query(Token).filter(
                    Token.account == account
                ).first()
            
            if existing:
                # 更新现有记录
                existing.token_value = encrypted_token
                existing.status = TokenStatus.ACTIVE
                existing.extension_id = extension_id
                if account:
                    existing.account = account
                existing.updated_at = get_china_now()
                logger.info(f"更新Token: user_id={user_id}, account={account}, token={mask_token(token)}")
            else:
                # 创建新记录
                now = get_china_now()
                existing = Token(
                    user_id=user_id,
                    account=account,
                    token_value=encrypted_token,
                    status=TokenStatus.ACTIVE,
                    extension_id=extension_id,
                    created_at=now,
                    updated_at=now
                )
                self.session.add(existing)
                logger.info(f"创建Token: user_id={user_id}, account={account}, token={mask_token(token)}")
            
            self.session.commit()
            self.session.refresh(existing)
            return existing
            
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"数据库操作失败: {str(e)}")
            raise TokenServiceError(f"存储Token失败: {str(e)}")
    
    def get_all(self, include_expired: bool = True) -> List[Token]:
        """
        获取所有Token
        
        Args:
            include_expired: 是否包含已过期的Token，默认True
            
        Returns:
            List[Token]: Token列表
        """
        try:
            query = self.session.query(Token)
            if not include_expired:
                query = query.filter(Token.status == TokenStatus.ACTIVE)
            return query.all()
        except SQLAlchemyError as e:
            logger.error(f"查询Token列表失败: {str(e)}")
            raise TokenServiceError(f"查询Token列表失败: {str(e)}")
    
    def get_by_user(self, user_id: str) -> Optional[Token]:
        """
        根据用户ID获取Token
        
        Args:
            user_id: 用户标识
            
        Returns:
            Optional[Token]: Token对象，如果不存在则返回None
        """
        try:
            return self.session.query(Token).filter(
                Token.user_id == user_id.strip()
            ).first()
        except SQLAlchemyError as e:
            logger.error(f"查询Token失败: user_id={user_id}, error={str(e)}")
            raise TokenServiceError(f"查询Token失败: {str(e)}")
    
    def get_by_id(self, token_id: int) -> Optional[Token]:
        """
        根据ID获取Token
        
        Args:
            token_id: Token ID
            
        Returns:
            Optional[Token]: Token对象，如果不存在则返回None
        """
        try:
            return self.session.query(Token).filter(
                Token.id == token_id
            ).first()
        except SQLAlchemyError as e:
            logger.error(f"查询Token失败: id={token_id}, error={str(e)}")
            raise TokenServiceError(f"查询Token失败: {str(e)}")

    def delete(self, token_id: int) -> bool:
        """
        删除Token
        
        Args:
            token_id: Token ID
            
        Returns:
            bool: 是否删除成功
            
        Raises:
            TokenNotFoundError: Token不存在
            TokenServiceError: 数据库操作失败
        """
        try:
            token = self.session.query(Token).filter(
                Token.id == token_id
            ).first()
            
            if token is None:
                logger.warning(f"删除Token失败: Token不存在, id={token_id}")
                raise TokenNotFoundError(f"Token不存在: id={token_id}")
            
            user_id = token.user_id
            self.session.delete(token)
            self.session.commit()
            logger.info(f"删除Token成功: id={token_id}, user_id={user_id}")
            return True
            
        except TokenNotFoundError:
            raise
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"删除Token失败: id={token_id}, error={str(e)}")
            raise TokenServiceError(f"删除Token失败: {str(e)}")
    
    def delete_by_user(self, user_id: str) -> bool:
        """
        根据用户ID删除Token
        
        Args:
            user_id: 用户标识
            
        Returns:
            bool: 是否删除成功
            
        Raises:
            TokenNotFoundError: Token不存在
            TokenServiceError: 数据库操作失败
        """
        try:
            token = self.session.query(Token).filter(
                Token.user_id == user_id.strip()
            ).first()
            
            if token is None:
                logger.warning(f"删除Token失败: Token不存在, user_id={user_id}")
                raise TokenNotFoundError(f"Token不存在: user_id={user_id}")
            
            self.session.delete(token)
            self.session.commit()
            logger.info(f"删除Token成功: user_id={user_id}")
            return True
            
        except TokenNotFoundError:
            raise
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"删除Token失败: user_id={user_id}, error={str(e)}")
            raise TokenServiceError(f"删除Token失败: {str(e)}")
    
    def update_status(self, token_id: int, status: TokenStatus) -> bool:
        """
        更新Token状态
        
        Args:
            token_id: Token ID
            status: 新状态
            
        Returns:
            bool: 是否更新成功
            
        Raises:
            TokenNotFoundError: Token不存在
            TokenServiceError: 数据库操作失败
        """
        try:
            token = self.session.query(Token).filter(
                Token.id == token_id
            ).first()
            
            if token is None:
                logger.warning(f"更新Token状态失败: Token不存在, id={token_id}")
                raise TokenNotFoundError(f"Token不存在: id={token_id}")
            
            old_status = token.status
            token.status = status
            token.updated_at = get_china_now()
            self.session.commit()
            logger.info(f"更新Token状态: id={token_id}, {old_status.value} -> {status.value}")
            return True
            
        except TokenNotFoundError:
            raise
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"更新Token状态失败: id={token_id}, error={str(e)}")
            raise TokenServiceError(f"更新Token状态失败: {str(e)}")
    
    def update_last_active(self, token_id: int) -> bool:
        """
        更新Token最后活跃时间
        
        Args:
            token_id: Token ID
            
        Returns:
            bool: 是否更新成功
            
        Raises:
            TokenNotFoundError: Token不存在
            TokenServiceError: 数据库操作失败
        """
        try:
            token = self.session.query(Token).filter(
                Token.id == token_id
            ).first()
            
            if token is None:
                logger.warning(f"更新活跃时间失败: Token不存在, id={token_id}")
                raise TokenNotFoundError(f"Token不存在: id={token_id}")
            
            token.last_active_at = get_china_now()
            token.updated_at = get_china_now()
            self.session.commit()
            logger.info(f"更新Token活跃时间: id={token_id}")
            return True
            
        except TokenNotFoundError:
            raise
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"更新活跃时间失败: id={token_id}, error={str(e)}")
            raise TokenServiceError(f"更新活跃时间失败: {str(e)}")
    
    def get_decrypted_token(self, token_id: int) -> Optional[str]:
        """
        获取解密后的Token值
        
        Args:
            token_id: Token ID
            
        Returns:
            Optional[str]: 解密后的Token值，如果不存在则返回None
        """
        token = self.get_by_id(token_id)
        if token is None:
            return None
        return decrypt_token(token.token_value)
    
    def get_active_tokens(self) -> List[Token]:
        """
        获取所有活跃状态的Token
        
        Returns:
            List[Token]: 活跃Token列表
        """
        return self.get_all(include_expired=False)


# 全局服务实例（延迟初始化）
_service_instance: Optional[TokenService] = None


def get_token_service() -> TokenService:
    """获取全局Token服务实例"""
    global _service_instance
    if _service_instance is None:
        _service_instance = TokenService()
    return _service_instance


def reset_token_service():
    """重置全局Token服务实例（主要用于测试）"""
    global _service_instance
    if _service_instance is not None:
        _service_instance.close()
        _service_instance = None
