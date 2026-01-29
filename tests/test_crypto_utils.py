"""
Crypto Utils Tests
加密工具测试
"""

import pytest
import os

from token_manager.crypto_utils import (
    TokenCrypto,
    encrypt_token,
    decrypt_token,
    mask_token
)


class TestTokenCrypto:
    """Token加密工具测试"""
    
    def test_encrypt_decrypt_roundtrip(self):
        """测试加密解密往返"""
        crypto = TokenCrypto()
        original = "test_token_1234567890"
        
        encrypted = crypto.encrypt(original)
        decrypted = crypto.decrypt(encrypted)
        
        assert decrypted == original
    
    def test_encrypt_produces_different_output(self):
        """测试加密后的值与原值不同"""
        crypto = TokenCrypto()
        original = "test_token_1234567890"
        
        encrypted = crypto.encrypt(original)
        
        assert encrypted != original
    
    def test_encrypt_empty_raises_error(self):
        """测试加密空字符串抛出异常"""
        crypto = TokenCrypto()
        
        with pytest.raises(ValueError):
            crypto.encrypt("")
    
    def test_decrypt_invalid_raises_error(self):
        """测试解密无效数据抛出异常"""
        crypto = TokenCrypto()
        
        with pytest.raises(ValueError):
            crypto.decrypt("invalid_encrypted_data")
    
    def test_generate_key(self):
        """测试生成密钥"""
        key = TokenCrypto.generate_key()
        
        assert key is not None
        assert len(key) > 0
        # Fernet密钥是base64编码的32字节
        assert len(key) == 44


class TestMaskToken:
    """Token脱敏测试"""
    
    def test_mask_long_token(self):
        """测试脱敏长Token"""
        token = "abcdefgh12345678ijklmnop"
        masked = mask_token(token)
        
        assert masked == "abcdefgh...ijklmnop"
        assert len(masked) == 19
    
    def test_mask_short_token(self):
        """测试脱敏短Token"""
        token = "short"
        masked = mask_token(token)
        
        assert masked == "****"
    
    def test_mask_exactly_16_chars(self):
        """测试脱敏恰好16字符的Token"""
        token = "1234567890123456"
        masked = mask_token(token)
        
        assert masked == "****"
    
    def test_mask_17_chars(self):
        """测试脱敏17字符的Token"""
        token = "12345678901234567"
        masked = mask_token(token)
        
        # 前8位 + ... + 后8位
        assert masked == "12345678...01234567"
        assert masked.startswith("12345678")
        assert masked.endswith("01234567")
    
    def test_mask_empty_token(self):
        """测试脱敏空Token"""
        masked = mask_token("")
        assert masked == "****"
    
    def test_mask_none_token(self):
        """测试脱敏None"""
        masked = mask_token(None)
        assert masked == "****"


class TestConvenienceFunctions:
    """便捷函数测试"""
    
    def test_encrypt_token_function(self):
        """测试encrypt_token便捷函数"""
        original = "test_token_1234567890"
        encrypted = encrypt_token(original)
        
        assert encrypted != original
        assert len(encrypted) > 0
    
    def test_decrypt_token_function(self):
        """测试decrypt_token便捷函数"""
        original = "test_token_1234567890"
        encrypted = encrypt_token(original)
        decrypted = decrypt_token(encrypted)
        
        assert decrypted == original
