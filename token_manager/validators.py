"""
Token Validators
Token格式验证模块
"""

import re
from typing import Tuple


# Token格式要求
MIN_TOKEN_LENGTH = 10  # 最小长度
MAX_TOKEN_LENGTH = 500  # 最大长度
# Token允许的字符集：字母、数字、下划线、连字符、点、等号（base64常见字符）
TOKEN_PATTERN = re.compile(r'^[A-Za-z0-9_\-\.=+/]+$')


def validate_token(token: str) -> Tuple[bool, str]:
    """
    验证Token格式有效性
    
    验证规则：
    1. Token不能为空或纯空白
    2. Token长度必须在MIN_TOKEN_LENGTH到MAX_TOKEN_LENGTH之间
    3. Token只能包含允许的字符集
    
    Args:
        token: 待验证的Token字符串
        
    Returns:
        Tuple[bool, str]: (是否有效, 错误信息或空字符串)
    """
    # 检查空值
    if token is None:
        return False, "Token不能为空"
    
    # 检查纯空白
    if not token or not token.strip():
        return False, "Token不能为空或纯空白"
    
    # 去除首尾空白后检查
    token = token.strip()
    
    # 检查长度
    if len(token) < MIN_TOKEN_LENGTH:
        return False, f"Token长度不能小于{MIN_TOKEN_LENGTH}个字符"
    
    if len(token) > MAX_TOKEN_LENGTH:
        return False, f"Token长度不能超过{MAX_TOKEN_LENGTH}个字符"
    
    # 检查字符集
    if not TOKEN_PATTERN.match(token):
        return False, "Token包含非法字符，只允许字母、数字和特定符号(_-.=+/)"
    
    return True, ""


def is_valid_token(token: str) -> bool:
    """
    简化的Token验证函数
    
    Args:
        token: 待验证的Token字符串
        
    Returns:
        bool: Token是否有效
    """
    valid, _ = validate_token(token)
    return valid


def validate_user_id(user_id: str) -> Tuple[bool, str]:
    """
    验证用户ID格式
    
    Args:
        user_id: 待验证的用户ID
        
    Returns:
        Tuple[bool, str]: (是否有效, 错误信息或空字符串)
    """
    if user_id is None:
        return False, "用户ID不能为空"
    
    if not user_id or not user_id.strip():
        return False, "用户ID不能为空或纯空白"
    
    user_id = user_id.strip()
    
    if len(user_id) > 64:
        return False, "用户ID长度不能超过64个字符"
    
    return True, ""


def is_valid_user_id(user_id: str) -> bool:
    """
    简化的用户ID验证函数
    
    Args:
        user_id: 待验证的用户ID
        
    Returns:
        bool: 用户ID是否有效
    """
    valid, _ = validate_user_id(user_id)
    return valid
