"""
Token Manager Server
FastAPI服务端点模块

提供REST API和WebSocket端点，包括：
- Token的CRUD操作API
- WebSocket连接端点
- localhost访问控制中间件
- CORS配置

Requirements: 3.5, 4.1, 4.3, 4.4, 7.1, 9.1
"""

import logging
from typing import Optional, List
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import SERVER_HOST, SERVER_PORT, MANAGEMENT_PASSWORD, get_china_now
from .token_service import (
    TokenService, 
    TokenServiceError, 
    TokenValidationError, 
    TokenNotFoundError,
    get_token_service
)
from .websocket_manager import WebSocketManager, get_websocket_manager
from .message_protocol import (
    MessageType,
    parse_message,
    validate_message,
    validate_register_payload,
    validate_token_upload_payload,
    validate_heartbeat_payload,
    create_register_ack_message,
    create_token_ack_message,
    create_heartbeat_ack_message,
    create_error_message,
    MessageParseError,
    MessageValidationError
)
from .crypto_utils import mask_token, decrypt_token
from .models import TokenStatus

# 配置日志
logger = logging.getLogger(__name__)

# 创建FastAPI应用
app = FastAPI(
    title="Token Manager API",
    description="JMS平台Token管理服务API",
    version="1.0.0"
)


# ============== Pydantic模型 ==============

class TokenCreate(BaseModel):
    """Token创建请求模型"""
    token: str = Field(..., min_length=1, description="Token值")
    user_id: str = Field(..., min_length=1, description="用户标识")
    extension_id: Optional[str] = Field(None, description="插件标识")
    account: Optional[str] = Field(None, description="登录账号")
    account_type: Optional[str] = Field(None, description="账号类型: agent(代理区) 或 network(网点)")


class TokenResponse(BaseModel):
    """Token响应模型"""
    id: int
    user_id: str
    account: Optional[str]  # 登录账号
    account_type: str  # 账号类型: agent 或 network
    token_masked: str  # 脱敏后的Token
    status: str
    extension_id: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]
    last_active_at: Optional[str]
    
    class Config:
        from_attributes = True


class TokenListResponse(BaseModel):
    """Token列表响应模型"""
    total: int
    tokens: List[TokenResponse]


class MessageResponse(BaseModel):
    """通用消息响应模型"""
    success: bool
    message: str


class AuthRequest(BaseModel):
    """密码认证请求模型"""
    password: str = Field(..., min_length=1, description="管理密码")


# ============== 中间件 ==============

# 允许的本地地址
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1", "testclient"}


async def localhost_access_control(request: Request, call_next):
    """
    Localhost访问控制中间件
    
    仅允许来自localhost的请求访问API
    
    Requirements: 9.1
    """
    # 获取客户端IP
    client_host = request.client.host if request.client else None
    
    # WebSocket连接的处理
    if request.url.path == "/ws":
        # WebSocket连接也需要验证来源
        if client_host not in ALLOWED_HOSTS:
            logger.warning(f"WebSocket连接被拒绝: 非本地来源 {client_host}")
            return JSONResponse(
                status_code=403,
                content={"detail": "Forbidden: Only localhost access is allowed"}
            )
        return await call_next(request)
    
    # 静态文件和文档路径放行
    if request.url.path.startswith("/static") or request.url.path.startswith("/management") or request.url.path in ["/docs", "/redoc", "/openapi.json", "/"]:
        return await call_next(request)
    
    # API路径检查localhost
    if request.url.path.startswith("/api"):
        if client_host not in ALLOWED_HOSTS:
            logger.warning(f"API请求被拒绝: 非本地来源 {client_host}")
            return JSONResponse(
                status_code=403,
                content={"detail": "Forbidden: Only localhost access is allowed"}
            )
    
    return await call_next(request)


# 添加中间件
app.middleware("http")(localhost_access_control)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost",
        "http://127.0.0.1",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============== 依赖注入 ==============

def get_service() -> TokenService:
    """获取TokenService实例"""
    return get_token_service()


def get_ws_manager() -> WebSocketManager:
    """获取WebSocketManager实例"""
    return get_websocket_manager()


# ============== 辅助函数 ==============

def token_to_response(token) -> TokenResponse:
    """将Token模型转换为响应模型"""
    # 尝试解密Token，如果失败则显示错误提示
    try:
        token_masked = mask_token(decrypt_token(token.token_value))
    except (ValueError, Exception) as e:
        logger.warning(f"Token解密失败: id={token.id}, error={str(e)}")
        token_masked = "[解密失败-密钥不匹配]"
    
    # 获取账号类型
    account_type_value = "agent"
    if token.account_type:
        account_type_value = token.account_type.value if hasattr(token.account_type, 'value') else str(token.account_type)
    
    return TokenResponse(
        id=token.id,
        user_id=token.user_id,
        account=token.account,
        account_type=account_type_value,
        token_masked=token_masked,
        status=token.status.value if isinstance(token.status, TokenStatus) else token.status,
        extension_id=token.extension_id,
        created_at=token.created_at.isoformat() if token.created_at else None,
        updated_at=token.updated_at.isoformat() if token.updated_at else None,
        last_active_at=token.last_active_at.isoformat() if token.last_active_at else None
    )


# ============== REST API端点 ==============

@app.get("/api/tokens", response_model=TokenListResponse, tags=["Tokens"])
async def get_all_tokens(
    include_expired: bool = True,
    service: TokenService = Depends(get_service)
):
    """
    获取所有Token
    
    Requirements: 4.1
    
    Args:
        include_expired: 是否包含已过期的Token
        
    Returns:
        TokenListResponse: Token列表
    """
    try:
        tokens = service.get_all(include_expired=include_expired)
        token_responses = [token_to_response(t) for t in tokens]
        return TokenListResponse(total=len(token_responses), tokens=token_responses)
    except TokenServiceError as e:
        logger.error(f"获取Token列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tokens", response_model=TokenResponse, tags=["Tokens"])
async def create_or_update_token(
    data: TokenCreate,
    service: TokenService = Depends(get_service)
):
    """
    创建或更新Token
    
    如果用户已存在Token，则更新；否则创建新记录。
    
    Requirements: 3.5
    
    Args:
        data: Token创建请求数据
        
    Returns:
        TokenResponse: 创建或更新后的Token
    """
    try:
        token = service.create_or_update(
            token=data.token,
            user_id=data.user_id,
            extension_id=data.extension_id,
            account=data.account,
            account_type=data.account_type
        )
        logger.info(f"Token创建/更新成功: user_id={data.user_id}, account={data.account}, type={data.account_type}")
        return token_to_response(token)
    except TokenValidationError as e:
        logger.warning(f"Token验证失败: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except TokenServiceError as e:
        logger.error(f"Token创建/更新失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tokens/{user_id}", response_model=TokenResponse, tags=["Tokens"])
async def get_token_by_user(
    user_id: str,
    service: TokenService = Depends(get_service)
):
    """
    获取指定用户的Token
    
    Requirements: 4.1
    
    Args:
        user_id: 用户标识
        
    Returns:
        TokenResponse: Token信息
    """
    try:
        token = service.get_by_user(user_id)
        if token is None:
            raise HTTPException(status_code=404, detail=f"Token不存在: user_id={user_id}")
        return token_to_response(token)
    except TokenServiceError as e:
        logger.error(f"获取Token失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/tokens/{token_id}", response_model=MessageResponse, tags=["Tokens"])
async def delete_token(
    token_id: int,
    service: TokenService = Depends(get_service),
    ws_manager: WebSocketManager = Depends(get_ws_manager)
):
    """
    删除指定Token
    
    删除Token后会通过WebSocket通知对应的插件清除本地Token
    
    Requirements: 4.3, 4.4
    
    Args:
        token_id: Token ID
        
    Returns:
        MessageResponse: 操作结果
    """
    try:
        # 先获取Token信息，用于发送删除通知
        token = service.get_by_id(token_id)
        if token is None:
            raise HTTPException(status_code=404, detail=f"Token不存在: id={token_id}")
        
        user_id = token.user_id
        extension_id = token.extension_id
        
        # 删除Token
        service.delete(token_id)
        logger.info(f"Token删除成功: id={token_id}, user_id={user_id}")
        
        # 通过WebSocket通知对应的插件
        if extension_id:
            from .message_protocol import create_token_deleted_message
            message = create_token_deleted_message(user_id, "Token已被管理员删除")
            sent = await ws_manager.send_to_extension(extension_id, message)
            if sent:
                logger.info(f"已通知插件Token被删除: extension_id={extension_id}")
            else:
                logger.warning(f"插件未连接，无法发送删除通知: extension_id={extension_id}")
        
        return MessageResponse(success=True, message=f"Token已删除: id={token_id}")
    except TokenNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TokenServiceError as e:
        logger.error(f"删除Token失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== WebSocket端点 ==============

@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    ws_manager: WebSocketManager = Depends(get_ws_manager),
    service: TokenService = Depends(get_service)
):
    """
    WebSocket连接端点
    
    处理Chrome Extension的WebSocket连接，支持：
    - 插件注册
    - Token上报
    - 心跳保持
    
    Requirements: 7.1
    """
    extension_id = None
    
    try:
        # 等待第一条消息（应该是注册消息）
        await websocket.accept()
        
        # 接收注册消息
        raw_data = await websocket.receive_text()
        message = parse_message(raw_data)
        validate_message(message)
        
        if message["type"] != MessageType.REGISTER.value:
            # 第一条消息必须是注册消息
            await websocket.send_json(create_error_message(
                code=400,
                message="第一条消息必须是注册消息"
            ))
            await websocket.close(code=1008, reason="未注册")
            return
        
        # 验证注册消息
        validate_register_payload(message["payload"])
        extension_id = message["payload"]["extensionId"]
        
        # 关闭之前的accept，重新通过manager连接
        # 注意：这里websocket已经accept了，所以直接存储连接信息
        ws_manager._connections[extension_id] = type('ConnectionInfo', (), {
            'websocket': websocket,
            'extension_id': extension_id,
            'user_id': None,
            'connected_at': get_china_now(),
            'last_heartbeat': get_china_now()
        })()
        
        logger.info(f"插件注册成功: extension_id={extension_id}")
        
        # 发送注册确认
        await websocket.send_json(create_register_ack_message(
            success=True,
            message="注册成功"
        ))
        
        # 消息处理循环
        while True:
            raw_data = await websocket.receive_text()
            await handle_websocket_message(
                websocket=websocket,
                extension_id=extension_id,
                raw_data=raw_data,
                ws_manager=ws_manager,
                service=service
            )
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket连接断开: extension_id={extension_id}")
    except MessageParseError as e:
        logger.warning(f"消息解析失败: {str(e)}")
        try:
            await websocket.send_json(create_error_message(code=400, message=str(e)))
        except:
            pass
    except MessageValidationError as e:
        logger.warning(f"消息验证失败: {str(e)}")
        try:
            await websocket.send_json(create_error_message(code=400, message=str(e)))
        except:
            pass
    except Exception as e:
        logger.error(f"WebSocket处理异常: {str(e)}")
    finally:
        # 清理连接
        if extension_id:
            await ws_manager.disconnect(extension_id)


async def handle_websocket_message(
    websocket: WebSocket,
    extension_id: str,
    raw_data: str,
    ws_manager: WebSocketManager,
    service: TokenService
):
    """
    处理WebSocket消息
    
    Args:
        websocket: WebSocket连接
        extension_id: 插件标识
        raw_data: 原始消息数据
        ws_manager: WebSocket管理器
        service: Token服务
    """
    try:
        message = parse_message(raw_data)
        validate_message(message)
        
        msg_type = message["type"]
        payload = message["payload"]
        
        if msg_type == MessageType.TOKEN_UPLOAD.value:
            # 处理Token上报
            validate_token_upload_payload(payload)
            
            token_value = payload["token"]
            user_id = payload["userId"]
            account = payload.get("account")  # 获取账号信息
            account_type = payload.get("accountType")  # 获取账号类型
            
            try:
                token = service.create_or_update(
                    token=token_value,
                    user_id=user_id,
                    extension_id=extension_id,
                    account=account,
                    account_type=account_type
                )
                
                # 关联用户ID到连接
                ws_manager.set_user_id(extension_id, user_id)
                
                await websocket.send_json(create_token_ack_message(
                    success=True,
                    token_id=token.id,
                    message="Token已保存"
                ))
                logger.info(f"Token上报成功: user_id={user_id}, account={account}, type={account_type}, extension_id={extension_id}")
                
            except TokenValidationError as e:
                await websocket.send_json(create_token_ack_message(
                    success=False,
                    message=str(e)
                ))
            except TokenServiceError as e:
                await websocket.send_json(create_token_ack_message(
                    success=False,
                    message=f"存储失败: {str(e)}"
                ))
        
        elif msg_type == MessageType.HEARTBEAT.value:
            # 处理心跳
            ws_manager.update_heartbeat(extension_id)
            await websocket.send_json(create_heartbeat_ack_message())
            logger.debug(f"心跳响应: extension_id={extension_id}")
        
        else:
            # 未知消息类型
            logger.warning(f"未处理的消息类型: {msg_type}")
            await websocket.send_json(create_error_message(
                code=400,
                message=f"不支持的消息类型: {msg_type}"
            ))
    
    except MessageParseError as e:
        await websocket.send_json(create_error_message(code=400, message=str(e)))
    except MessageValidationError as e:
        await websocket.send_json(create_error_message(code=400, message=str(e)))


# ============== 认证端点 ==============

@app.post("/api/auth/verify", response_model=MessageResponse, tags=["Auth"])
async def verify_password(data: AuthRequest):
    """
    验证管理密码
    
    Requirements: 9.2
    
    Args:
        data: 包含密码的请求数据
        
    Returns:
        MessageResponse: 验证结果
    """
    if data.password == MANAGEMENT_PASSWORD:
        logger.info("管理界面认证成功")
        return MessageResponse(success=True, message="认证成功")
    else:
        logger.warning("管理界面认证失败: 密码错误")
        return MessageResponse(success=False, message="密码错误")


# ============== 管理界面路由 ==============

@app.get("/", tags=["Management"])
async def redirect_to_management():
    """重定向到管理界面"""
    return FileResponse(Path(__file__).parent / "static" / "management.html")


@app.get("/management", tags=["Management"])
async def management_page():
    """管理界面入口"""
    return FileResponse(Path(__file__).parent / "static" / "management.html")


# ============== 健康检查端点 ==============

@app.get("/health", tags=["Health"])
async def health_check():
    """健康检查端点"""
    return {"status": "healthy", "timestamp": get_china_now().isoformat()}


# ============== 虚假签收报表API ==============

class FalseSignReportRequest(BaseModel):
    """虚假签收报表请求模型"""
    date: Optional[str] = Field(None, description="报表日期，格式：YYYY-MM-DD，默认昨天")


@app.post("/api/false-sign-report/{token_id}", tags=["Reports"])
async def download_false_sign_report(
    token_id: int,
    data: FalseSignReportRequest = None,
    service: TokenService = Depends(get_service)
):
    """
    下载虚假签收报表
    
    使用指定Token的凭证下载虚假签收报表Excel文件
    根据Token的账号类型自动选择代理区或网点API
    
    Args:
        token_id: Token ID
        data: 请求数据，包含可选的日期参数
        
    Returns:
        FileResponse: Excel文件
    """
    import sys
    import os
    from datetime import timedelta
    
    # 添加项目根目录到路径
    project_root = Path(__file__).parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    
    try:
        # 获取Token
        token = service.get_by_id(token_id)
        if token is None:
            raise HTTPException(status_code=404, detail=f"Token不存在: id={token_id}")
        
        if token.status.value != 'active':
            raise HTTPException(status_code=400, detail="Token已过期或无效")
        
        # 解密Token
        decrypted_token = decrypt_token(token.token_value)
        
        # 获取账号类型
        account_type = "agent"
        if token.account_type:
            account_type = token.account_type.value if hasattr(token.account_type, 'value') else str(token.account_type)
        
        # 确定日期
        target_date = None
        if data and data.date:
            target_date = data.date
        else:
            target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        
        # 调用虚假签收模块，传入账号类型
        from modules.false_sign import FalseSignModule
        
        module = FalseSignModule(authtoken=decrypted_token, account_type=account_type)
        output_path = module.export_excel(date=target_date)
        
        if not output_path or not os.path.exists(output_path):
            return JSONResponse(
                status_code=200,
                content={
                    "success": False,
                    "message": f"日期 {target_date} 无虚假签收数据",
                    "date": target_date,
                    "account_type": account_type
                }
            )
        
        # 返回文件
        filename = os.path.basename(output_path)
        return FileResponse(
            path=output_path,
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"下载虚假签收报表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")


@app.get("/api/connections", tags=["WebSocket"])
async def get_connections(ws_manager: WebSocketManager = Depends(get_ws_manager)):
    """
    获取当前WebSocket连接列表
    
    Returns:
        连接信息列表（不包含管理界面连接）
    """
    connections = ws_manager.get_all_connections()
    # 过滤掉管理界面的连接（以management-ui-开头的）
    plugin_connections = [
        conn for conn in connections 
        if not conn.extension_id.startswith('management-ui-')
    ]
    return {
        "total": len(plugin_connections),
        "connections": [
            {
                "extension_id": conn.extension_id,
                "user_id": conn.user_id,
                "connected_at": conn.connected_at.isoformat() if conn.connected_at else None,
                "last_heartbeat": conn.last_heartbeat.isoformat() if conn.last_heartbeat else None
            }
            for conn in plugin_connections
        ]
    }


# ============== 应用生命周期事件 ==============

@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info("Token Manager服务启动中...")
    
    # 初始化数据库
    from .models import init_database
    init_database()
    
    # 挂载静态文件目录
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
        logger.info(f"静态文件目录已挂载: {static_dir}")
    
    # 启动WebSocket心跳检测
    ws_manager = get_websocket_manager()
    await ws_manager.start_heartbeat_checker()
    
    logger.info(f"Token Manager服务已启动: http://{SERVER_HOST}:{SERVER_PORT}")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    logger.info("Token Manager服务关闭中...")
    
    # 关闭所有WebSocket连接
    ws_manager = get_websocket_manager()
    await ws_manager.close_all()
    
    # 关闭数据库连接
    from .models import close_database
    close_database()
    
    logger.info("Token Manager服务已关闭")
