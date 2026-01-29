"""
Validators Tests
验证器测试
"""

import pytest

from token_manager.validators import (
    validate_token,
    is_valid_token,
    validate_user_id,
    is_valid_user_id,
    MIN_TOKEN_LENGTH,
    MAX_TOKEN_LENGTH
)


class TestTokenValidation:
    """Token验证测试"""
    
    def test_valid_token(self):
        """测试有效Token"""
        valid, msg = validate_token("valid_token_1234567890")
        assert valid is True
        assert msg == ""
    
    def test_empty_token(self):
        """测试空Token"""
        valid, msg = validate_token("")
        assert valid is False
        assert "空" in msg
    
    def test_none_token(self):
        """测试None Token"""
        valid, msg = validate_token(None)
        assert valid is False
        assert "空" in msg
    
    def test_whitespace_token(self):
        """测试纯空白Token"""
        valid, msg = validate_token("   ")
        assert valid is False
        assert "空" in msg
    
    def test_short_token(self):
        """测试过短Token"""
        valid, msg = validate_token("short")
        assert valid is False
        assert str(MIN_TOKEN_LENGTH) in msg
    
    def test_token_at_min_length(self):
        """测试最小长度Token"""
        token = "a" * MIN_TOKEN_LENGTH
        valid, msg = validate_token(token)
        assert valid is True
    
    def test_token_below_min_length(self):
        """测试低于最小长度Token"""
        token = "a" * (MIN_TOKEN_LENGTH - 1)
        valid, msg = validate_token(token)
        assert valid is False
    
    def test_token_at_max_length(self):
        """测试最大长度Token"""
        token = "a" * MAX_TOKEN_LENGTH
        valid, msg = validate_token(token)
        assert valid is True
    
    def test_token_above_max_length(self):
        """测试超过最大长度Token"""
        token = "a" * (MAX_TOKEN_LENGTH + 1)
        valid, msg = validate_token(token)
        assert valid is False
    
    def test_token_with_valid_chars(self):
        """测试包含有效字符的Token"""
        # 字母、数字、下划线、连字符、点、等号、加号、斜杠
        valid, msg = validate_token("Token_123-abc.def=ghi+jkl/mno")
        assert valid is True
    
    def test_token_with_invalid_chars(self):
        """测试包含无效字符的Token"""
        valid, msg = validate_token("token@invalid#chars!")
        assert valid is False
        assert "非法字符" in msg
    
    def test_is_valid_token_helper(self):
        """测试is_valid_token辅助函数"""
        assert is_valid_token("valid_token_1234567890") is True
        assert is_valid_token("") is False
        assert is_valid_token("short") is False


class TestUserIdValidation:
    """用户ID验证测试"""
    
    def test_valid_user_id(self):
        """测试有效用户ID"""
        valid, msg = validate_user_id("user123")
        assert valid is True
        assert msg == ""
    
    def test_empty_user_id(self):
        """测试空用户ID"""
        valid, msg = validate_user_id("")
        assert valid is False
        assert "空" in msg
    
    def test_none_user_id(self):
        """测试None用户ID"""
        valid, msg = validate_user_id(None)
        assert valid is False
        assert "空" in msg
    
    def test_whitespace_user_id(self):
        """测试纯空白用户ID"""
        valid, msg = validate_user_id("   ")
        assert valid is False
        assert "空" in msg
    
    def test_long_user_id(self):
        """测试过长用户ID"""
        user_id = "a" * 65
        valid, msg = validate_user_id(user_id)
        assert valid is False
        assert "64" in msg
    
    def test_max_length_user_id(self):
        """测试最大长度用户ID"""
        user_id = "a" * 64
        valid, msg = validate_user_id(user_id)
        assert valid is True
    
    def test_is_valid_user_id_helper(self):
        """测试is_valid_user_id辅助函数"""
        assert is_valid_user_id("user123") is True
        assert is_valid_user_id("") is False
        assert is_valid_user_id("a" * 65) is False
