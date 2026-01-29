"""
Token Encryption Utilities
Token加密工具模块
"""

import os
import base64
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from .config import TOKEN_ENCRYPT_KEY


class TokenCrypto:
    """Token加密工具类"""
    
    def __init__(self, key: Optional[str] = None):
        """
        初始化加密工具
        
        Args:
            key: 加密密钥，如果不提供则使用环境变量或自动生成
        """
        self._key = key or TOKEN_ENCRYPT_KEY
        
        if self._key is None:
            # 自动生成密钥并保存
            self._key = self.generate_key()
            self._save_key_to_env()
        
        # 确保密钥是bytes类型
        if isinstance(self._key, str):
            self._key_bytes = self._key.encode()
        else:
            self._key_bytes = self._key
            
        self._cipher = Fernet(self._key_bytes)
    
    def encrypt(self, token: str) -> str:
        """
        加密Token
        
        Args:
            token: 原始Token字符串
            
        Returns:
            加密后的Token字符串（base64编码）
        """
        if not token:
            raise ValueError("Token cannot be empty")
        
        encrypted_bytes = self._cipher.encrypt(token.encode())
        return encrypted_bytes.decode()
    
    def decrypt(self, encrypted_token: str) -> str:
        """
        解密Token
        
        Args:
            encrypted_token: 加密后的Token字符串
            
        Returns:
            解密后的原始Token字符串
            
        Raises:
            InvalidToken: 如果解密失败
        """
        if not encrypted_token:
            raise ValueError("Encrypted token cannot be empty")
        
        try:
            decrypted_bytes = self._cipher.decrypt(encrypted_token.encode())
            return decrypted_bytes.decode()
        except InvalidToken:
            raise ValueError("Failed to decrypt token: invalid token or key")
    
    @staticmethod
    def mask_token(token: str) -> str:
        """
        Token脱敏显示
        
        对于长度大于16的Token，显示前8位和后8位，中间用...代替
        对于长度小于等于16的Token，显示****
        
        Args:
            token: 原始Token字符串
            
        Returns:
            脱敏后的Token字符串
        """
        if not token or len(token) <= 16:
            return "****"
        return f"{token[:8]}...{token[-8:]}"
    
    @staticmethod
    def generate_key() -> str:
        """
        生成新的加密密钥
        
        Returns:
            Fernet兼容的加密密钥字符串
        """
        return Fernet.generate_key().decode()
    
    def _save_key_to_env(self):
        """将生成的密钥保存到环境变量（仅用于开发环境）"""
        os.environ["TOKEN_ENCRYPT_KEY"] = self._key
    
    @property
    def key(self) -> str:
        """获取当前使用的密钥"""
        if isinstance(self._key, bytes):
            return self._key.decode()
        return self._key


# 全局加密实例（延迟初始化）
_crypto_instance: Optional[TokenCrypto] = None


def get_crypto() -> TokenCrypto:
    """获取全局加密实例"""
    global _crypto_instance
    if _crypto_instance is None:
        _crypto_instance = TokenCrypto()
    return _crypto_instance


def encrypt_token(token: str) -> str:
    """便捷函数：加密Token"""
    return get_crypto().encrypt(token)


def decrypt_token(encrypted_token: str) -> str:
    """便捷函数：解密Token"""
    return get_crypto().decrypt(encrypted_token)


def mask_token(token: str) -> str:
    """便捷函数：Token脱敏"""
    return TokenCrypto.mask_token(token)
