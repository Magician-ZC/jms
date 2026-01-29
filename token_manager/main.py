"""
Token Manager Main Entry
Token管理系统服务启动入口

集成所有组件，提供统一的服务启动和优雅关闭功能。

Requirements: 8.2
"""

import asyncio
import signal
import sys
import logging
from pathlib import Path
from typing import Optional

import uvicorn

# 加载.env文件（必须在导入config之前）
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path)
except ImportError:
    pass  # dotenv未安装时忽略

from .config import SERVER_HOST, SERVER_PORT, LOG_LEVEL, KEEP_ALIVE_INTERVAL
from .models import init_database, close_database
from .token_keeper import get_token_keeper, reset_token_keeper
from .websocket_manager import get_websocket_manager

# 配置日志
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


class TokenManagerService:
    """
    Token管理服务
    
    统一管理所有组件的生命周期，包括：
    - FastAPI HTTP/WebSocket服务
    - Token保活服务
    - 数据库连接
    
    支持优雅关闭，确保所有资源正确释放。
    """
    
    def __init__(
        self,
        host: str = SERVER_HOST,
        port: int = SERVER_PORT,
        enable_keeper: bool = True,
        keeper_interval: int = KEEP_ALIVE_INTERVAL
    ):
        """
        初始化Token管理服务
        
        Args:
            host: 服务监听地址
            port: 服务监听端口
            enable_keeper: 是否启用Token保活服务
            keeper_interval: 保活间隔（秒）
        """
        self.host = host
        self.port = port
        self.enable_keeper = enable_keeper
        self.keeper_interval = keeper_interval
        
        self._server: Optional[uvicorn.Server] = None
        self._shutdown_event = asyncio.Event()
        self._is_running = False
        
        logger.info(f"TokenManagerService初始化: host={host}, port={port}, keeper={enable_keeper}")
    
    async def start(self) -> None:
        """
        启动服务
        
        启动所有组件：
        1. 初始化数据库
        2. 启动FastAPI服务
        3. 启动Token保活服务（如果启用）
        """
        if self._is_running:
            logger.warning("服务已在运行")
            return
        
        logger.info("=" * 50)
        logger.info("Token Manager 服务启动中...")
        logger.info("=" * 50)
        
        try:
            # 1. 初始化数据库
            logger.info("初始化数据库...")
            init_database()
            
            # 2. 启动Token保活服务
            if self.enable_keeper:
                logger.info(f"启动Token保活服务 (间隔: {self.keeper_interval}秒)...")
                keeper = get_token_keeper()
                keeper.set_interval(self.keeper_interval)
                await keeper.start()
            
            # 3. 启动FastAPI服务
            logger.info(f"启动HTTP/WebSocket服务: http://{self.host}:{self.port}")
            
            # 导入app（延迟导入避免循环依赖）
            from .server import app
            
            config = uvicorn.Config(
                app=app,
                host=self.host,
                port=self.port,
                log_level=LOG_LEVEL.lower(),
                access_log=True
            )
            self._server = uvicorn.Server(config)
            
            self._is_running = True
            
            logger.info("=" * 50)
            logger.info(f"Token Manager 服务已启动")
            logger.info(f"管理界面: http://{self.host}:{self.port}/management")
            logger.info(f"API文档: http://{self.host}:{self.port}/docs")
            logger.info("=" * 50)
            
            # 运行服务器
            await self._server.serve()
            
        except Exception as e:
            logger.error(f"服务启动失败: {str(e)}")
            await self.stop()
            raise
    
    async def stop(self) -> None:
        """
        停止服务
        
        优雅关闭所有组件：
        1. 停止FastAPI服务
        2. 停止Token保活服务
        3. 关闭WebSocket连接
        4. 关闭数据库连接
        """
        if not self._is_running:
            return
        
        logger.info("=" * 50)
        logger.info("Token Manager 服务关闭中...")
        logger.info("=" * 50)
        
        self._is_running = False
        
        try:
            # 1. 停止FastAPI服务
            if self._server:
                logger.info("停止HTTP/WebSocket服务...")
                self._server.should_exit = True
            
            # 2. 停止Token保活服务
            if self.enable_keeper:
                logger.info("停止Token保活服务...")
                keeper = get_token_keeper()
                await keeper.stop()
            
            # 3. 关闭所有WebSocket连接
            logger.info("关闭WebSocket连接...")
            ws_manager = get_websocket_manager()
            await ws_manager.close_all()
            
            # 4. 关闭数据库连接
            logger.info("关闭数据库连接...")
            close_database()
            
            logger.info("=" * 50)
            logger.info("Token Manager 服务已关闭")
            logger.info("=" * 50)
            
        except Exception as e:
            logger.error(f"服务关闭时出错: {str(e)}")
    
    def setup_signal_handlers(self) -> None:
        """
        设置信号处理器
        
        处理SIGINT和SIGTERM信号，实现优雅关闭
        """
        loop = asyncio.get_event_loop()
        
        def signal_handler(sig):
            logger.info(f"收到信号 {sig.name}，准备关闭服务...")
            self._shutdown_event.set()
            if self._server:
                self._server.should_exit = True
        
        # 在Unix系统上设置信号处理
        if sys.platform != "win32":
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))
        else:
            # Windows上使用不同的方式
            signal.signal(signal.SIGINT, lambda s, f: signal_handler(signal.SIGINT))
            signal.signal(signal.SIGTERM, lambda s, f: signal_handler(signal.SIGTERM))


async def run_server(
    host: str = SERVER_HOST,
    port: int = SERVER_PORT,
    enable_keeper: bool = True,
    keeper_interval: int = KEEP_ALIVE_INTERVAL
) -> None:
    """
    运行Token管理服务
    
    便捷函数，用于启动完整的Token管理服务。
    
    Args:
        host: 服务监听地址
        port: 服务监听端口
        enable_keeper: 是否启用Token保活服务
        keeper_interval: 保活间隔（秒）
    """
    service = TokenManagerService(
        host=host,
        port=port,
        enable_keeper=enable_keeper,
        keeper_interval=keeper_interval
    )
    
    service.setup_signal_handlers()
    
    try:
        await service.start()
    except KeyboardInterrupt:
        logger.info("收到键盘中断信号")
    finally:
        await service.stop()


def main():
    """
    主入口函数
    
    解析命令行参数并启动服务
    """
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Token Manager - JMS平台Token管理服务",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m token_manager.main                    # 使用默认配置启动
  python -m token_manager.main --port 8888        # 指定端口
  python -m token_manager.main --no-keeper        # 禁用保活服务
  python -m token_manager.main --interval 600     # 设置保活间隔为10分钟
        """
    )
    
    parser.add_argument(
        "--host",
        type=str,
        default=SERVER_HOST,
        help=f"服务监听地址 (默认: {SERVER_HOST})"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=SERVER_PORT,
        help=f"服务监听端口 (默认: {SERVER_PORT})"
    )
    
    parser.add_argument(
        "--no-keeper",
        action="store_true",
        help="禁用Token保活服务"
    )
    
    parser.add_argument(
        "--interval",
        type=int,
        default=KEEP_ALIVE_INTERVAL,
        help=f"Token保活间隔（秒）(默认: {KEEP_ALIVE_INTERVAL})"
    )
    
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=LOG_LEVEL,
        help=f"日志级别 (默认: {LOG_LEVEL})"
    )
    
    args = parser.parse_args()
    
    # 更新日志级别
    if args.log_level:
        logging.getLogger().setLevel(getattr(logging, args.log_level.upper()))
    
    # 运行服务
    try:
        asyncio.run(run_server(
            host=args.host,
            port=args.port,
            enable_keeper=not args.no_keeper,
            keeper_interval=args.interval
        ))
    except KeyboardInterrupt:
        print("\n[退出] 用户中断")
    except Exception as e:
        logger.error(f"服务异常退出: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
