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

import asyncio
import logging
from typing import Optional, List
from datetime import datetime, timedelta
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
    network_code: Optional[str]  # 网点编码
    network_name: Optional[str]  # 网点名称
    network_id: Optional[int]  # 网点ID
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

# 允许的局域网网段
ALLOWED_NETWORKS = ["10.", "192.168.", "172.16.", "172.17.", "172.18.", "172.19.", "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.", "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31."]


def is_allowed_host(host: str) -> bool:
    """检查是否是允许的主机地址"""
    if not host:
        return False
    
    # 检查本地地址
    if host in ALLOWED_HOSTS:
        return True
    
    # 检查局域网地址
    for network in ALLOWED_NETWORKS:
        if host.startswith(network):
            return True
    
    return False


async def localhost_access_control(request: Request, call_next):
    """
    访问控制中间件
    
    允许来自localhost和局域网的请求访问API
    
    Requirements: 9.1
    """
    # 获取客户端IP
    client_host = request.client.host if request.client else None
    
    # WebSocket连接的处理
    if request.url.path == "/ws":
        # WebSocket连接也需要验证来源
        if not is_allowed_host(client_host):
            logger.warning(f"WebSocket连接被拒绝: 非允许来源 {client_host}")
            return JSONResponse(
                status_code=403,
                content={"detail": "Forbidden: Only local/LAN access is allowed"}
            )
        return await call_next(request)
    
    # 静态文件和文档路径放行
    if request.url.path.startswith("/static") or request.url.path.startswith("/management") or request.url.path in ["/docs", "/redoc", "/openapi.json", "/"]:
        return await call_next(request)
    
    # API路径检查
    if request.url.path.startswith("/api"):
        if not is_allowed_host(client_host):
            logger.warning(f"API请求被拒绝: 非允许来源 {client_host}")
            return JSONResponse(
                status_code=403,
                content={"detail": "Forbidden: Only local/LAN access is allowed"}
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
        network_code=token.network_code,
        network_name=token.network_name,
        network_id=token.network_id,
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
            # 获取网点信息（仅网点账号有）
            network_code = payload.get("networkCode")
            network_name = payload.get("networkName")
            network_id = payload.get("networkId")
            
            try:
                token = service.create_or_update(
                    token=token_value,
                    user_id=user_id,
                    extension_id=extension_id,
                    account=account,
                    account_type=account_type,
                    network_code=network_code,
                    network_name=network_name,
                    network_id=network_id
                )
                
                # 关联用户ID到连接
                ws_manager.set_user_id(extension_id, user_id)
                
                await websocket.send_json(create_token_ack_message(
                    success=True,
                    token_id=token.id,
                    message="Token已保存"
                ))
                logger.info(f"Token上报成功: user_id={user_id}, account={account}, type={account_type}, network={network_code}, extension_id={extension_id}")
                
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


class WaybillDownloadSubmitRequest(BaseModel):
    """寄件运单下载提交请求模型"""
    start_date: str = Field(..., description="录入开始日期，格式：YYYY-MM-DD")
    end_date: str = Field(..., description="录入结束日期，格式：YYYY-MM-DD")


class WaybillDownloadFileRequest(BaseModel):
    """寄件运单文件下载请求模型"""
    job_id: str = Field(..., description="任务ID")
    file_url: str = Field(..., description="文件URL路径")


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


# ============== 寄件运单下载API ==============

# 后台任务存储
waybill_download_tasks = {}  # task_id -> task_info


@app.post("/api/waybill-download/{token_id}/submit", tags=["Waybill"])
async def submit_waybill_download_task(
    token_id: int,
    data: WaybillDownloadSubmitRequest,
    service: TokenService = Depends(get_service)
):
    """
    提交寄件运单下载任务到下载中心
    将日期范围拆分为4个时间段分别提交
    
    Args:
        token_id: Token ID
        data: 包含日期范围的请求数据
        
    Returns:
        任务提交结果
    """
    import httpx
    import asyncio
    import uuid
    
    try:
        # 获取Token
        token = service.get_by_id(token_id)
        if token is None:
            raise HTTPException(status_code=404, detail=f"Token不存在: id={token_id}")
        
        if token.status.value != 'active':
            raise HTTPException(status_code=400, detail="Token已过期或无效")
        
        # 解密Token
        decrypted_token = decrypt_token(token.token_value)
        
        # pickFinanceCode应该是代理区编码（如350000），从user_id中提取前6位数字
        user_id_digits = ''.join(filter(str.isdigit, token.user_id))
        pick_finance_code = user_id_digits[:6] if len(user_id_digits) >= 6 else user_id_digits
        
        # 生成任务ID
        task_id = str(uuid.uuid4())[:8]
        
        # 4个时间段
        time_periods = [
            ("00:00:00", "13:59:59", "T1"),
            ("14:00:00", "17:59:59", "T2"),
            ("18:00:00", "20:59:59", "T3"),
            ("21:00:00", "23:59:59", "T4")
        ]
        
        # 创建任务记录
        now = get_china_now()
        task_info = {
            "task_id": task_id,
            "token_id": token_id,
            "user_id": token.user_id,
            "user_name": token.account or token.user_id,
            "start_date": data.start_date,
            "end_date": data.end_date,
            "status": "pending",
            "created_at": now.isoformat(),
            "sub_tasks": [],
            "completed_count": 0,
            "total_count": 0,
            "downloaded_files": []
        }
        
        # 为每个日期和时间段创建子任务
        from datetime import datetime, timedelta
        start_dt = datetime.strptime(data.start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(data.end_date, "%Y-%m-%d")
        
        current_dt = start_dt
        while current_dt <= end_dt:
            date_str = current_dt.strftime("%Y-%m-%d")
            for start_time, end_time, period_name in time_periods:
                job_name = f"寄件运单管理_{current_dt.strftime('%Y%m%d')}_{period_name}_{now.strftime('%H%M%S')}_{token.user_id}"
                sub_task = {
                    "job_name": job_name,
                    "date": date_str,
                    "period": period_name,
                    "time_start": f"{date_str} {start_time}",
                    "time_end": f"{date_str} {end_time}",
                    "status": "pending",
                    "file_url": None,
                    "job_id": None,
                    "error": None
                }
                task_info["sub_tasks"].append(sub_task)
            current_dt += timedelta(days=1)
        
        task_info["total_count"] = len(task_info["sub_tasks"])
        task_info["status"] = "running"
        waybill_download_tasks[task_id] = task_info
        
        # 启动后台任务
        asyncio.create_task(run_waybill_download_task(
            task_id=task_id,
            token_value=decrypted_token,
            pick_finance_code=pick_finance_code,
            user_id=token.user_id
        ))
        
        logger.info(f"寄件运单下载任务已创建: task_id={task_id}, sub_tasks={task_info['total_count']}")
        
        return {
            "success": True,
            "task_id": task_id,
            "total_tasks": task_info["total_count"],
            "message": f"已创建{task_info['total_count']}个下载子任务"
        }
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"提交寄件运单下载任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"提交失败: {str(e)}")


async def run_waybill_download_task(task_id: str, token_value: str, pick_finance_code: str, user_id: str):
    """后台执行下载任务"""
    import httpx
    import asyncio
    
    task_info = waybill_download_tasks.get(task_id)
    if not task_info:
        return
    
    headers = {
        "authtoken": token_value,
        "Content-Type": "application/json;charset=UTF-8",
        "lang": "zh_CN",
        "routename": "sendWaybillSite"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. 提交所有子任务
        for sub_task in task_info["sub_tasks"]:
            try:
                request_data = {
                    "current": 1,
                    "size": 20,
                    "timeStart": sub_task["time_start"],
                    "timeEnd": sub_task["time_end"],
                    "waybillNos": [],
                    "manageRegionCode": "",
                    "pickFinanceCode": pick_finance_code,
                    "franchiseeCodes": [],
                    "pickNetworkCodes": [],
                    "customerNames": [],
                    "customerCodes": [],
                    "packageChargeWeightStart": "",
                    "packageChargeWeightEnd": "",
                    "inputTimeStart": sub_task["time_start"],
                    "inputTimeEnd": sub_task["time_end"],
                    "countryCode": "CN",
                    "jobName": sub_task["job_name"],
                    "countryId": "1"
                }
                
                response = await client.post(
                    "https://jmsgw.jtexpress.com.cn/networkmanagement/omsWaybill/export",
                    json=request_data,
                    headers=headers
                )
                result = response.json()
                
                if result.get("code") == 1 and result.get("succ"):
                    sub_task["status"] = "submitted"
                    logger.info(f"子任务提交成功: {sub_task['job_name']}")
                else:
                    sub_task["status"] = "failed"
                    sub_task["error"] = result.get("msg", "提交失败")
                    logger.warning(f"子任务提交失败: {sub_task['job_name']}, {sub_task['error']}")
                
                # 间隔1秒避免请求过快
                await asyncio.sleep(1)
                
            except Exception as e:
                sub_task["status"] = "failed"
                sub_task["error"] = str(e)
                logger.error(f"子任务提交异常: {sub_task['job_name']}, {str(e)}")
        
        # 2. 轮询检查任务状态并下载
        max_polls = 30  # 最多轮询30次
        poll_interval = 60  # 60秒轮询一次
        
        for poll_count in range(max_polls):
            # 检查是否所有任务都完成
            pending_tasks = [t for t in task_info["sub_tasks"] if t["status"] in ["submitted", "pending"]]
            if not pending_tasks:
                break
            
            await asyncio.sleep(poll_interval)
            
            # 查询下载中心列表
            try:
                now = get_china_now()
                params = {
                    "current": 1,
                    "size": 100,
                    "total": 0,
                    "operatorCode": user_id,
                    "jobName": "",
                    "dlStatus": "",
                    "operatingStartTime": (now - timedelta(days=1)).strftime("%Y-%m-%d 00:00:00"),
                    "operatingEndTime": now.strftime("%Y-%m-%d 23:59:59")
                }
                
                response = await client.get(
                    "https://jmsgw.jtexpress.com.cn/networkmanagement/ft/ftExport/pageBalance",
                    params=params,
                    headers={**headers, "Content-Type": "application/json;charset=utf-8"}
                )
                result = response.json()
                
                if result.get("code") == 1 and result.get("succ"):
                    records = result.get("data", {}).get("records", [])
                    
                    for sub_task in task_info["sub_tasks"]:
                        if sub_task["status"] != "submitted":
                            continue
                        
                        # 查找匹配的记录
                        for record in records:
                            if record.get("jobName") == sub_task["job_name"]:
                                status_type = record.get("statusType")
                                file_url = record.get("fileUrl")
                                job_id = record.get("id")
                                
                                if status_type == 1 and file_url:
                                    # 下载文件
                                    sub_task["file_url"] = file_url
                                    sub_task["job_id"] = job_id
                                    
                                    try:
                                        await download_single_waybill_file(
                                            client, headers, job_id, file_url, 
                                            sub_task["job_name"], task_info
                                        )
                                        sub_task["status"] = "completed"
                                        task_info["completed_count"] += 1
                                    except Exception as e:
                                        sub_task["status"] = "download_failed"
                                        sub_task["error"] = str(e)
                                        
                                elif status_type in [2, 3]:  # 2=进行中, 3=排队中，继续等待
                                    # 保持submitted状态，继续等待
                                    pass
                                elif status_type == 4:  # 失败状态
                                    sub_task["status"] = "failed"
                                    sub_task["error"] = record.get("statusRemark") or "任务失败"
                                # 其他未知状态也继续等待
                                break
                                
            except Exception as e:
                logger.error(f"轮询任务状态失败: {str(e)}")
        
        # 更新任务最终状态
        failed_count = len([t for t in task_info["sub_tasks"] if "failed" in t["status"]])
        if task_info["completed_count"] == task_info["total_count"]:
            task_info["status"] = "completed"
        elif task_info["completed_count"] > 0:
            task_info["status"] = "partial"
        else:
            task_info["status"] = "failed"
        
        logger.info(f"任务完成: task_id={task_id}, completed={task_info['completed_count']}/{task_info['total_count']}")


async def download_single_waybill_file(client, headers, job_id, file_url, job_name, task_info):
    """下载单个文件"""
    import os
    import tempfile
    
    # 获取下载URL
    request_data = {
        "fileUrl": file_url,
        "jobId": job_id,
        "countryId": "1"
    }
    
    response = await client.post(
        "https://jmsgw.jtexpress.com.cn/networkmanagement/ft/ftExport/fileUrl",
        json=request_data,
        headers=headers
    )
    result = response.json()
    
    if result.get("code") != 1 or not result.get("data"):
        raise Exception("获取下载链接失败")
    
    download_url = result.get("data")
    
    # 下载文件
    file_response = await client.get(download_url, timeout=120.0)
    if file_response.status_code != 200:
        raise Exception("下载文件失败")
    
    # 保存文件
    filename = file_url.split("/")[-1] if "/" in file_url else f"{job_name}.xlsx"
    download_dir = Path(__file__).parent.parent / "downloads"
    download_dir.mkdir(exist_ok=True)
    
    file_path = download_dir / filename
    with open(file_path, "wb") as f:
        f.write(file_response.content)
    
    task_info["downloaded_files"].append({
        "filename": filename,
        "path": str(file_path),
        "job_name": job_name
    })
    
    logger.info(f"文件下载成功: {filename}")


@app.get("/api/waybill-download/tasks", tags=["Waybill"])
async def get_waybill_download_tasks():
    """获取所有下载任务列表"""
    tasks = []
    for task_id, task_info in waybill_download_tasks.items():
        tasks.append({
            "task_id": task_id,
            "user_name": task_info.get("user_name"),
            "start_date": task_info.get("start_date"),
            "end_date": task_info.get("end_date"),
            "status": task_info.get("status"),
            "created_at": task_info.get("created_at"),
            "completed_count": task_info.get("completed_count", 0),
            "total_count": task_info.get("total_count", 0),
            "downloaded_files": len(task_info.get("downloaded_files", []))
        })
    
    # 按创建时间倒序
    tasks.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"tasks": tasks}


@app.get("/api/waybill-download/tasks/{task_id}", tags=["Waybill"])
async def get_waybill_download_task_detail(task_id: str):
    """获取下载任务详情"""
    task_info = waybill_download_tasks.get(task_id)
    if not task_info:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task_info


@app.get("/api/waybill-download/tasks/{task_id}/files/{filename}", tags=["Waybill"])
async def download_waybill_task_file(task_id: str, filename: str):
    """下载任务中的文件"""
    task_info = waybill_download_tasks.get(task_id)
    if not task_info:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    for file_info in task_info.get("downloaded_files", []):
        if file_info.get("filename") == filename:
            file_path = file_info.get("path")
            if file_path and Path(file_path).exists():
                return FileResponse(
                    path=file_path,
                    filename=filename,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
    
    raise HTTPException(status_code=404, detail="文件不存在")


@app.post("/api/waybill-download/tasks/{task_id}/retry", tags=["Waybill"])
async def retry_waybill_download_task(
    task_id: str,
    service: TokenService = Depends(get_service)
):
    """
    重试下载任务
    先查询下载中心检查任务是否已存在，存在则更新状态/下载文件，不存在则重新提交
    """
    import httpx
    
    task_info = waybill_download_tasks.get(task_id)
    if not task_info:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 获取Token
    token = service.get_by_id(task_info["token_id"])
    if token is None:
        raise HTTPException(status_code=404, detail="Token不存在")
    
    if token.status.value != 'active':
        raise HTTPException(status_code=400, detail="Token已过期或无效")
    
    # 解密Token
    decrypted_token = decrypt_token(token.token_value)
    
    # pickFinanceCode
    user_id_digits = ''.join(filter(str.isdigit, token.user_id))
    pick_finance_code = user_id_digits[:6] if len(user_id_digits) >= 6 else user_id_digits
    
    # 重置任务状态
    task_info["status"] = "running"
    
    # 启动后台重试任务
    asyncio.create_task(run_waybill_retry_task(
        task_id=task_id,
        token_value=decrypted_token,
        pick_finance_code=pick_finance_code,
        user_id=token.user_id
    ))
    
    return {
        "success": True,
        "message": "重试任务已启动"
    }


async def run_waybill_retry_task(task_id: str, token_value: str, pick_finance_code: str, user_id: str):
    """后台执行重试任务"""
    import httpx
    
    task_info = waybill_download_tasks.get(task_id)
    if not task_info:
        return
    
    headers = {
        "authtoken": token_value,
        "Content-Type": "application/json;charset=UTF-8",
        "lang": "zh_CN",
        "routename": "sendWaybillSite"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. 先查询下载中心，检查哪些任务已存在
        try:
            now = get_china_now()
            params = {
                "current": 1,
                "size": 100,
                "total": 0,
                "operatorCode": user_id,
                "jobName": "",
                "dlStatus": "",
                "operatingStartTime": (now - timedelta(days=7)).strftime("%Y-%m-%d 00:00:00"),
                "operatingEndTime": now.strftime("%Y-%m-%d 23:59:59")
            }
            
            response = await client.get(
                "https://jmsgw.jtexpress.com.cn/networkmanagement/ft/ftExport/pageBalance",
                params=params,
                headers={**headers, "Content-Type": "application/json;charset=utf-8"}
            )
            result = response.json()
            
            existing_jobs = {}
            if result.get("code") == 1 and result.get("succ"):
                records = result.get("data", {}).get("records", [])
                for record in records:
                    existing_jobs[record.get("jobName")] = record
            
            logger.info(f"重试任务: 下载中心已有{len(existing_jobs)}个任务记录")
            
        except Exception as e:
            logger.error(f"查询下载中心失败: {str(e)}")
            existing_jobs = {}
        
        # 2. 处理每个子任务
        for sub_task in task_info["sub_tasks"]:
            # 跳过已完成的任务
            if sub_task["status"] == "completed":
                continue
            
            job_name = sub_task["job_name"]
            
            # 检查是否在下载中心已存在
            if job_name in existing_jobs:
                record = existing_jobs[job_name]
                status_type = record.get("statusType")
                file_url = record.get("fileUrl")
                job_id = record.get("id")
                
                logger.info(f"任务已存在: {job_name}, statusType={status_type}")
                
                if status_type == 1 and file_url:
                    # 已完成，下载文件
                    sub_task["file_url"] = file_url
                    sub_task["job_id"] = job_id
                    sub_task["status"] = "submitted"  # 标记为已提交，等待下载
                    
                    try:
                        await download_single_waybill_file(
                            client, headers, job_id, file_url,
                            job_name, task_info
                        )
                        sub_task["status"] = "completed"
                        task_info["completed_count"] += 1
                        logger.info(f"文件下载成功: {job_name}")
                    except Exception as e:
                        sub_task["status"] = "download_failed"
                        sub_task["error"] = str(e)
                        logger.error(f"文件下载失败: {job_name}, {str(e)}")
                        
                elif status_type in [2, 3]:
                    # 进行中或排队中，标记为已提交继续等待
                    sub_task["status"] = "submitted"
                    sub_task["job_id"] = job_id
                    logger.info(f"任务进行中/排队中: {job_name}")
                    
                elif status_type == 4:
                    # 失败，需要重新提交
                    sub_task["status"] = "pending"
                    logger.info(f"任务失败，需重新提交: {job_name}")
                else:
                    # 其他状态，标记为已提交
                    sub_task["status"] = "submitted"
                    sub_task["job_id"] = job_id
            else:
                # 不存在，标记为待提交
                sub_task["status"] = "pending"
                sub_task["error"] = None
        
        # 3. 提交所有pending状态的任务
        pending_tasks = [t for t in task_info["sub_tasks"] if t["status"] == "pending"]
        for sub_task in pending_tasks:
            try:
                request_data = {
                    "current": 1,
                    "size": 20,
                    "timeStart": sub_task["time_start"],
                    "timeEnd": sub_task["time_end"],
                    "waybillNos": [],
                    "manageRegionCode": "",
                    "pickFinanceCode": pick_finance_code,
                    "franchiseeCodes": [],
                    "pickNetworkCodes": [],
                    "customerNames": [],
                    "customerCodes": [],
                    "packageChargeWeightStart": "",
                    "packageChargeWeightEnd": "",
                    "inputTimeStart": sub_task["time_start"],
                    "inputTimeEnd": sub_task["time_end"],
                    "countryCode": "CN",
                    "jobName": sub_task["job_name"],
                    "countryId": "1"
                }
                
                response = await client.post(
                    "https://jmsgw.jtexpress.com.cn/networkmanagement/omsWaybill/export",
                    json=request_data,
                    headers=headers
                )
                result = response.json()
                
                if result.get("code") == 1 and result.get("succ"):
                    sub_task["status"] = "submitted"
                    logger.info(f"重新提交成功: {sub_task['job_name']}")
                else:
                    sub_task["status"] = "failed"
                    sub_task["error"] = result.get("msg", "提交失败")
                    logger.warning(f"重新提交失败: {sub_task['job_name']}, {sub_task['error']}")
                
                await asyncio.sleep(1)
                
            except Exception as e:
                sub_task["status"] = "failed"
                sub_task["error"] = str(e)
                logger.error(f"重新提交异常: {sub_task['job_name']}, {str(e)}")
        
        # 4. 轮询等待submitted状态的任务完成
        max_polls = 30
        poll_interval = 60
        
        for poll_count in range(max_polls):
            pending_tasks = [t for t in task_info["sub_tasks"] if t["status"] == "submitted"]
            if not pending_tasks:
                break
            
            await asyncio.sleep(poll_interval)
            
            try:
                now = get_china_now()
                params = {
                    "current": 1,
                    "size": 100,
                    "total": 0,
                    "operatorCode": user_id,
                    "jobName": "",
                    "dlStatus": "",
                    "operatingStartTime": (now - timedelta(days=7)).strftime("%Y-%m-%d 00:00:00"),
                    "operatingEndTime": now.strftime("%Y-%m-%d 23:59:59")
                }
                
                response = await client.get(
                    "https://jmsgw.jtexpress.com.cn/networkmanagement/ft/ftExport/pageBalance",
                    params=params,
                    headers={**headers, "Content-Type": "application/json;charset=utf-8"}
                )
                result = response.json()
                
                if result.get("code") == 1 and result.get("succ"):
                    records = result.get("data", {}).get("records", [])
                    
                    for sub_task in task_info["sub_tasks"]:
                        if sub_task["status"] != "submitted":
                            continue
                        
                        for record in records:
                            if record.get("jobName") == sub_task["job_name"]:
                                status_type = record.get("statusType")
                                file_url = record.get("fileUrl")
                                job_id = record.get("id")
                                
                                if status_type == 1 and file_url:
                                    sub_task["file_url"] = file_url
                                    sub_task["job_id"] = job_id
                                    
                                    try:
                                        await download_single_waybill_file(
                                            client, headers, job_id, file_url,
                                            sub_task["job_name"], task_info
                                        )
                                        sub_task["status"] = "completed"
                                        task_info["completed_count"] += 1
                                    except Exception as e:
                                        sub_task["status"] = "download_failed"
                                        sub_task["error"] = str(e)
                                        
                                elif status_type == 4:
                                    sub_task["status"] = "failed"
                                    sub_task["error"] = record.get("statusRemark") or "任务失败"
                                break
                                
            except Exception as e:
                logger.error(f"轮询任务状态失败: {str(e)}")
        
        # 更新任务最终状态
        failed_count = len([t for t in task_info["sub_tasks"] if "failed" in t["status"]])
        if task_info["completed_count"] == task_info["total_count"]:
            task_info["status"] = "completed"
        elif task_info["completed_count"] > 0:
            task_info["status"] = "partial"
        else:
            task_info["status"] = "failed"
        
        logger.info(f"重试任务完成: task_id={task_id}, completed={task_info['completed_count']}/{task_info['total_count']}")


@app.delete("/api/waybill-download/tasks/{task_id}", tags=["Waybill"])
async def delete_waybill_download_task(task_id: str):
    """删除下载任务"""
    if task_id in waybill_download_tasks:
        del waybill_download_tasks[task_id]
        return {"success": True, "message": "任务已删除"}
    raise HTTPException(status_code=404, detail="任务不存在")


# ============== Chrome插件管理API ==============

# GitHub仓库配置
GITHUB_REPO = "https://raw.githubusercontent.com/panlilu/jms/main/chrome_extension"
EXTENSION_FILES = [
    "manifest.json",
    "background.js",
    "content.js",
    "popup.html",
    "popup.css",
    "popup.js",
    "token_extractor.js",
    "ws_client.js",
]


@app.get("/api/extension/version", tags=["Extension"])
async def get_extension_version():
    """
    获取Chrome插件最新版本信息
    从本地manifest.json读取版本号
    """
    import json
    
    extension_dir = Path(__file__).parent.parent / "chrome_extension"
    manifest_path = extension_dir / "manifest.json"
    
    if not manifest_path.exists():
        raise HTTPException(status_code=500, detail="插件manifest.json不存在")
    
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        
        version = manifest.get("version", "1.0.0")
        
        # 读取更新日志（如果存在）
        changelog = "功能优化和Bug修复"
        changelog_path = extension_dir / "CHANGELOG.md"
        if changelog_path.exists():
            try:
                content = changelog_path.read_text(encoding='utf-8')
                # 提取最新版本的更新内容（简单处理）
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if line.startswith('## ') and version in line:
                        # 获取该版本的更新内容
                        changelog_lines = []
                        for j in range(i + 1, min(i + 10, len(lines))):
                            if lines[j].startswith('## '):
                                break
                            if lines[j].strip():
                                changelog_lines.append(lines[j].strip().lstrip('- '))
                        if changelog_lines:
                            changelog = '; '.join(changelog_lines[:3])
                        break
            except:
                pass
        
        return {
            "version": version,
            "changelog": changelog,
            "download_url": "/api/extension/download"
        }
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="manifest.json格式错误")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取版本信息失败: {str(e)}")


@app.post("/api/extension/update", tags=["Extension"])
async def update_extension():
    """
    从GitHub更新Chrome插件代码
    """
    import httpx
    
    extension_dir = Path(__file__).parent.parent / "chrome_extension"
    if not extension_dir.exists():
        raise HTTPException(status_code=500, detail="插件目录不存在")
    
    updated_files = []
    errors = []
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for filename in EXTENSION_FILES:
            try:
                url = f"{GITHUB_REPO}/{filename}"
                response = await client.get(url)
                
                if response.status_code == 200:
                    file_path = extension_dir / filename
                    file_path.write_text(response.text, encoding='utf-8')
                    updated_files.append(filename)
                    logger.info(f"插件文件更新成功: {filename}")
                else:
                    errors.append(f"{filename}: HTTP {response.status_code}")
                    logger.warning(f"插件文件下载失败: {filename}, status={response.status_code}")
                    
            except Exception as e:
                errors.append(f"{filename}: {str(e)}")
                logger.error(f"插件文件更新失败: {filename}, error={str(e)}")
    
    if not updated_files:
        raise HTTPException(status_code=500, detail=f"更新失败: {'; '.join(errors)}")
    
    return {
        "success": True,
        "message": f"已更新 {len(updated_files)} 个文件",
        "updated_files": len(updated_files),
        "files": updated_files,
        "errors": errors if errors else None
    }


@app.get("/api/extension/download", tags=["Extension"])
async def download_extension():
    """
    下载Chrome插件压缩包
    """
    import zipfile
    import io
    from fastapi.responses import StreamingResponse
    
    extension_dir = Path(__file__).parent.parent / "chrome_extension"
    if not extension_dir.exists():
        raise HTTPException(status_code=500, detail="插件目录不存在")
    
    # 创建内存中的ZIP文件
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for file_path in extension_dir.rglob('*'):
            if file_path.is_file():
                arcname = file_path.relative_to(extension_dir)
                zip_file.write(file_path, arcname)
    
    zip_buffer.seek(0)
    
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=chrome_extension.zip"}
    )


# ============== 问题件登记API ==============

# 问题件图片路径（相对于项目根目录）
PROBLEM_PIECE_IMAGE_PATH = Path(__file__).parent.parent / "wentijian.png"

class ProblemPieceRequest(BaseModel):
    """问题件登记请求模型"""
    waybill_no: str = Field(..., min_length=1, description="运单号")


class ProblemPieceListRequest(BaseModel):
    """获取问题件列表请求模型"""
    date: Optional[str] = Field(None, description="查询日期，格式：YYYY-MM-DD，默认今天")


async def get_network_id_from_api(token_value: str) -> Optional[int]:
    """
    从网点系统API获取网点ID
    
    Args:
        token_value: 解密后的Token值
        
    Returns:
        网点ID，获取失败返回None
    """
    import httpx
    
    headers = {
        "authToken": token_value,
        "Content-Type": "application/json;charset=UTF-8",
        "lang": "zh_CN"
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 尝试获取用户信息
            response = await client.get(
                "https://wdgw.jtexpress.com.cn/base/user/getUserInfo",
                headers=headers
            )
            result = response.json()
            
            if result.get("code") == 1 and result.get("succ") and result.get("data"):
                data = result["data"]
                # 尝试多个可能的字段名
                network_id = (
                    data.get("receiveNetworkId") or 
                    data.get("networkId") or 
                    data.get("siteId") or
                    data.get("id")
                )
                if network_id:
                    logger.info(f"从API获取到网点ID: {network_id}")
                    return int(network_id)
    except Exception as e:
        logger.warning(f"获取网点ID失败: {str(e)}")
    
    return None


async def upload_problem_piece_image(token_value: str, client) -> Optional[str]:
    """
    上传问题件图片
    
    Args:
        token_value: 解密后的Token值
        client: httpx.AsyncClient实例
        
    Returns:
        上传成功返回图片路径，失败返回None
    """
    # 检查图片文件是否存在
    if not PROBLEM_PIECE_IMAGE_PATH.exists():
        logger.warning(f"问题件图片不存在: {PROBLEM_PIECE_IMAGE_PATH}")
        return None
    
    # 读取图片文件
    image_data = PROBLEM_PIECE_IMAGE_PATH.read_bytes()
    file_size = len(image_data)
    
    headers = {
        "authToken": token_value,
        "Content-Type": "application/json;charset=utf-8",
        "lang": "zh_CN",
        "routeName": "batchProblem"
    }
    
    try:
        # 第一步：获取上传签名URL
        sign_url = "https://wdgw.jtexpress.com.cn/servicequality/file/getUploadSignedUrl"
        params = {
            "projectName": "jmswdweb",
            "moduleName": "batchProblem",
            "size": str(file_size),
            "fileNames": "wentijian.png"
        }
        
        response = await client.get(sign_url, params=params, headers=headers)
        result = response.json()
        
        if not (result.get("code") == 1 and result.get("succ") and result.get("data")):
            logger.warning(f"获取上传签名URL失败: {result.get('msg')}")
            return None
        
        upload_info = result["data"][0]
        upload_url = upload_info["url"]
        image_path = upload_info["path"]
        content_type = upload_info.get("contentType", "image/png")
        
        logger.info(f"获取上传签名URL成功: path={image_path}")
        
        # 第二步：上传图片到云存储
        upload_headers = {
            "Content-Type": content_type
        }
        
        upload_response = await client.put(upload_url, content=image_data, headers=upload_headers)
        
        if upload_response.status_code in [200, 201]:
            logger.info(f"图片上传成功: path={image_path}")
            return image_path
        else:
            logger.warning(f"图片上传失败: status={upload_response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"上传图片异常: {str(e)}")
        return None


@app.post("/api/problem-piece/{token_id}", tags=["ProblemPiece"])
async def register_problem_piece(
    token_id: int,
    data: ProblemPieceRequest,
    service: TokenService = Depends(get_service)
):
    """
    问题件登记
    
    使用指定Token的凭证进行问题件登记（仅网点账号可用）
    会自动上传预设的问题件图片
    
    Args:
        token_id: Token ID
        data: 请求数据，包含运单号
        
    Returns:
        登记结果
    """
    import httpx
    
    try:
        # 获取Token
        token = service.get_by_id(token_id)
        if token is None:
            raise HTTPException(status_code=404, detail=f"Token不存在: id={token_id}")
        
        if token.status.value != 'active':
            raise HTTPException(status_code=400, detail="Token已过期或无效")
        
        # 检查账号类型
        account_type = "agent"
        if token.account_type:
            account_type = token.account_type.value if hasattr(token.account_type, 'value') else str(token.account_type)
        
        if account_type != 'network':
            raise HTTPException(status_code=400, detail="问题件登记仅支持网点账号")
        
        # 解密Token
        decrypted_token = decrypt_token(token.token_value)
        
        # 获取网点ID
        network_id = token.network_id
        if not network_id:
            # 尝试从API获取网点ID
            network_id = await get_network_id_from_api(decrypted_token)
            if network_id:
                # 更新数据库中的网点ID
                service.update_network_info(token_id, network_id=network_id)
        
        if not network_id:
            raise HTTPException(status_code=400, detail="无法获取网点ID，请重新登录")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 上传图片
            image_path = await upload_problem_piece_image(decrypted_token, client)
            paths_value = image_path if image_path else ""
            
            # 构建请求数据（根据HAR文件分析）
            request_data = {
                "waybillNo": data.waybill_no,
                "replyContent": "",
                "problemPieceId": "",
                "probleTypeSubjectId": 118,
                "probleTypeSubjectId2": 100037,
                "receiveNetworkId": network_id,
                "replyContentImg": [],
                "replyStatus": 0,
                "probleTypeId": 4,
                "probleDescription": "此件到达我司运单信息缺失，我司已安排补打运单并安排最近班次转出。",
                "uploadDataProp": "success",
                "knowNetwork": "",
                "defaultKnow": None,
                "firstLevelTypeName": "运单信息不全",
                "changeDeliveryDate": "",
                "deliveryTime": "",
                "firstLevelTypeCode": "26",
                "isChangePackaging": "",
                "materialCode": "",
                "thirdExpressId": "",
                "thirdExpressCode": "",
                "thirdExpressName": "",
                "thirdWaybillNo": "",
                "provinceName": "",
                "cityName": "",
                "districtName": "",
                "provinceId": "",
                "cityId": "",
                "districtId": "",
                "address": "",
                "receiveName": "",
                "receivePhone": "",
                "problemTypeSubjectCode": "26",
                "secondLevelTypeId": 100037,
                "secondLevelTypeCode": "26a",
                "secondLevelTypeName": "运单信息不全a",
                "changeDeliveryTime": "",
                "paths": paths_value,
                "isCallConnectResult": False,
                "countryId": "1"
            }
            
            headers = {
                "authToken": decrypted_token,
                "Content-Type": "application/json;charset=UTF-8",
                "lang": "zh_CN",
                "routeName": "batchProblem"
            }
            
            response = await client.post(
                "https://wdgw.jtexpress.com.cn/servicequality/problemPiece/registration",
                json=request_data,
                headers=headers
            )
            result = response.json()
            
            if result.get("code") == 1 and result.get("succ"):
                logger.info(f"问题件登记成功: waybill_no={data.waybill_no}, network_id={network_id}, image={image_path}")
                return {
                    "success": True,
                    "message": "问题件登记成功",
                    "waybill_no": data.waybill_no,
                    "image_uploaded": bool(image_path)
                }
            else:
                error_msg = result.get("msg", "登记失败")
                logger.warning(f"问题件登记失败: waybill_no={data.waybill_no}, error={error_msg}")
                return {
                    "success": False,
                    "message": error_msg,
                    "waybill_no": data.waybill_no
                }
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"问题件登记异常: {str(e)}")
        raise HTTPException(status_code=500, detail=f"登记失败: {str(e)}")


@app.post("/api/problem-piece/{token_id}/list", tags=["ProblemPiece"])
async def get_problem_piece_list(
    token_id: int,
    data: ProblemPieceListRequest = None,
    service: TokenService = Depends(get_service)
):
    """
    获取问题件列表
    
    获取指定日期的问题件列表，返回未登记的运单号
    
    Args:
        token_id: Token ID
        data: 请求数据，包含可选的日期参数
        
    Returns:
        问题件列表
    """
    import httpx
    
    try:
        # 获取Token
        token = service.get_by_id(token_id)
        if token is None:
            raise HTTPException(status_code=404, detail=f"Token不存在: id={token_id}")
        
        if token.status.value != 'active':
            raise HTTPException(status_code=400, detail="Token已过期或无效")
        
        # 检查账号类型
        account_type = "agent"
        if token.account_type:
            account_type = token.account_type.value if hasattr(token.account_type, 'value') else str(token.account_type)
        
        if account_type != 'network':
            raise HTTPException(status_code=400, detail="问题件列表仅支持网点账号")
        
        # 解密Token
        decrypted_token = decrypt_token(token.token_value)
        
        # 获取网点信息
        network_id = token.network_id
        network_name = token.network_name
        network_code = token.network_code
        
        if not network_id or not network_code:
            raise HTTPException(status_code=400, detail="网点信息不完整，请重新登录")
        
        # 确定日期
        target_date = None
        if data and data.date:
            target_date = data.date
        else:
            target_date = datetime.now().strftime("%Y-%m-%d")
        
        headers = {
            "authToken": decrypted_token,
            "Content-Type": "application/json;charset=UTF-8",
            "lang": "zh_CN",
            "routeName": "OutofWarehouseParts"
        }
        
        # 分页获取所有数据
        all_records = []
        current_page = 1
        page_size = 100
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                request_data = {
                    "current": current_page,
                    "size": page_size,
                    "networkId": network_id,
                    "networkName": network_name or "",
                    "networkCode": network_code,
                    "inputDate": target_date,
                    "signType": 0,
                    "isCurrent": "1",
                    "deliverUser": None,
                    "countryId": "1"
                }
                
                response = await client.post(
                    "https://wdgw.jtexpress.com.cn/reportgateway/bigdataReport/detailDir/businessin/nms_deliver_area_monitor_detail_new",
                    json=request_data,
                    headers=headers
                )
                result = response.json()
                
                if result.get("code") != 1 or not result.get("data"):
                    break
                
                records = result.get("data", {}).get("records", [])
                if not records:
                    break
                
                all_records.extend(records)
                
                # 如果返回的记录数小于page_size，说明已经是最后一页
                if len(records) < page_size:
                    break
                
                current_page += 1
                
                # 安全限制，最多获取10页
                if current_page > 10:
                    break
        
        # 筛选未登记的运单（没有problemTime字段的）
        unregistered = []
        registered = []
        
        for record in all_records:
            waybill_info = {
                "billcode": record.get("billcode"),
                "deliveruser": record.get("deliveruser"),
                "deliverTime": record.get("deliverTime"),
                "problemTime": record.get("problemTime"),
                "problemTypeOne": record.get("problemTypeOne"),
                "thirdCode": record.get("thirdCode")
            }
            
            if record.get("problemTime"):
                registered.append(waybill_info)
            else:
                unregistered.append(waybill_info)
        
        logger.info(f"获取问题件列表: date={target_date}, total={len(all_records)}, unregistered={len(unregistered)}, registered={len(registered)}")
        
        return {
            "success": True,
            "date": target_date,
            "network_name": network_name,
            "total": len(all_records),
            "unregistered_count": len(unregistered),
            "registered_count": len(registered),
            "unregistered": unregistered,
            "registered": registered
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取问题件列表异常: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取列表失败: {str(e)}")


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
