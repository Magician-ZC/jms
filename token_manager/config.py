"""
Token Manager Configuration
Token管理系统配置文件
"""

import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# 中国时区 (UTC+8)
CHINA_TZ = timezone(timedelta(hours=8))


def get_china_now() -> datetime:
    """获取当前中国时间（东八区）"""
    return datetime.now(CHINA_TZ)


# 基础路径配置
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "token_data"

# 确保数据目录存在
DATA_DIR.mkdir(exist_ok=True)

# 数据库配置
DATABASE_URL = os.getenv("TOKEN_DB_URL", f"sqlite:///{DATA_DIR}/tokens.db")

# 服务器配置
SERVER_HOST = os.getenv("TOKEN_SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("TOKEN_SERVER_PORT", "8080"))

# WebSocket配置
WS_HEARTBEAT_INTERVAL = int(os.getenv("WS_HEARTBEAT_INTERVAL", "30"))  # 秒
WS_RECONNECT_ATTEMPTS = int(os.getenv("WS_RECONNECT_ATTEMPTS", "3"))
WS_RECONNECT_INTERVAL = int(os.getenv("WS_RECONNECT_INTERVAL", "5"))  # 秒

# Token保活配置
KEEP_ALIVE_INTERVAL = int(os.getenv("KEEP_ALIVE_INTERVAL", "300"))  # 秒，默认5分钟

# 加密配置
TOKEN_ENCRYPT_KEY = os.getenv("TOKEN_ENCRYPT_KEY", None)

# ============== 代理区平台配置 (idata.jtexpress.com.cn) ==============
JMS_LOGIN_URL = "https://jms.jtexpress.com.cn/login"
JMS_INDEX_URL = "https://jms.jtexpress.com.cn/index"
JMS_API_BASE_URL = "https://jmsgw.jtexpress.com.cn"

# ============== 网点平台配置 (wd.jtexpress.com.cn) ==============
WD_LOGIN_URL = "https://wd.jtexpress.com.cn/login"
WD_INDEX_URL = "https://wd.jtexpress.com.cn/indexSub"
WD_API_BASE_URL = "https://wdgw.jtexpress.com.cn"

# ============== 保活配置 ==============
# 代理区保活 - 使用数据平台页面
KEEP_ALIVE_URL = "https://idata.jtexpress.com.cn/indexSub"
AGENT_KEEP_ALIVE_URL = KEEP_ALIVE_URL

# 网点保活 - 使用轻量级API
NETWORK_KEEP_ALIVE_URL = "https://wdgw.jtexpress.com.cn/reportgateway/networkIndex/indicator/query"
NETWORK_KEEP_ALIVE_HEADERS = {
    "Content-Type": "application/json;charset=UTF-8",
    "Origin": "https://wd.jtexpress.com.cn",
    "Referer": "https://wd.jtexpress.com.cn/",
    "lang": "zh_CN",
    "routeName": "indexSub",
}
# 网点保活请求体（简化版，只需要验证Token有效性）
NETWORK_KEEP_ALIVE_BODY = {
    "dateDimension": "M",
    "dateType": 3,
    "organization": "network",
    "checkType": "head",
    "countryId": "1",
}

# 管理界面密码（生产环境应使用环境变量）
MANAGEMENT_PASSWORD = os.getenv("MANAGEMENT_PASSWORD", "admin123")

# 日志配置
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
