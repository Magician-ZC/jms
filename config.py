"""
公共配置模块
支持代理区(agent)和网点(network)两种账号类型
"""
from enum import Enum


class AccountType(Enum):
    """账号类型枚举"""
    AGENT = "agent"      # 代理区账号
    NETWORK = "network"  # 网点账号


# 福建省主要城市
CITIES = ["福州", "厦门", "泉州", "漳州", "莆田", "龙岩", "三明", "南平", "宁德"]

# ============== 代理区配置 (idata.jtexpress.com.cn) ==============
AGENT_CONFIG = {
    "name": "代理区",
    "login_url": "https://jms.jtexpress.com.cn/",
    "index_url": "https://jms.jtexpress.com.cn/index",
    "api_gateway": "https://jmsgw.jtexpress.com.cn",
    "api_base_url": "https://jmsgw.jtexpress.com.cn/businessplan/bigdataReport/detailDir",
    "origin": "https://idata.jtexpress.com.cn",
    "referer": "https://idata.jtexpress.com.cn/",
    "token_header": "authtoken",  # 小写
    "domains": ["jms.jtexpress.com.cn", "idata.jtexpress.com.cn"],
}

# ============== 网点配置 (wd.jtexpress.com.cn) ==============
NETWORK_CONFIG = {
    "name": "网点",
    "login_url": "https://wd.jtexpress.com.cn/login",
    "index_url": "https://wd.jtexpress.com.cn/indexSub",
    "api_gateway": "https://wdgw.jtexpress.com.cn",
    "api_base_url": "https://wdgw.jtexpress.com.cn/reportgateway/bigdataReport/detailDir",
    "origin": "https://wd.jtexpress.com.cn",
    "referer": "https://wd.jtexpress.com.cn/",
    "token_header": "authToken",  # 驼峰
    "domains": ["wd.jtexpress.com.cn"],
}

# JMS API 基础URL (代理区)
API_BASE_URL = AGENT_CONFIG["api_base_url"]

# 数据驾舱 API 端点 (代理区)
API_ENDPOINTS = {
    "平台当前时间发单量": f"{API_BASE_URL}/datacabin/dws_order_source_ratio",
    "当前发单总量": f"{API_BASE_URL}/datacabin/dws_order_totalandper_bydate",
    "预测当日总量": f"{API_BASE_URL}/datacabin/dws_order_totalandper_predict",
    "当前加盟商排名": f"{API_BASE_URL}/datacabin/dws_order_top_agentarea",
}

# ============== 虚假签收报表配置 ==============
# 代理区虚假签收API
FALSE_SIGN_AGENT_API = f"{AGENT_CONFIG['api_base_url']}/businessin/sqs_false_sign_rate_detail"
FALSE_SIGN_AGENT_PAGE_URL = "https://idata.jtexpress.com.cn/app/serviceQualityIndex/FalseSignReportPC"

# 网点虚假签收API
FALSE_SIGN_NETWORK_API = f"{NETWORK_CONFIG['api_base_url']}/businessin/nms_false_sign_rate_detail"
FALSE_SIGN_NETWORK_PAGE_URL = "https://wd.jtexpress.com.cn/servicequalityIndex/falseSignReportPC"

# 兼容旧代码
FALSE_SIGN_REPORT_API = FALSE_SIGN_AGENT_API
FALSE_SIGN_REPORT_PAGE_URL = FALSE_SIGN_AGENT_PAGE_URL

# 代理区虚假签收报表Excel字段映射 (API字段 -> Excel列名)
FALSE_SIGN_AGENT_COLUMNS = {
    "workOrderNo": "工单号",
    "waybillNo": "运单号",
    "pddCreateTime": "工单创建时间",
    "workOrderType": "工单类型",
    "complaintTarget": "投诉对象",
    "problemTypeName": "问题类型",
    "problemDescription": "问题描述",
    "falseType": "虚假类型",
    "signType": "签收类型",
    "agentName": "代理区",
    "virtName": "虚拟网点",
    "areaInfoDesc": "片区",
    "networkName": "网点名称",
    "networkCode": "网点编码",
    "deliveryName": "派件员",
    "deliveryCode": "派件员编码",
    "orderSourceName": "订单来源",
    "isCainiaoEnter": "是否菜鸟入仓",
    "isDispatcherOrder": "是否派件员下单",
    "isPhoneContact": "是否电话联系",
    "isPromise": "是否承诺",
    "isReback": "是否退回",
    "isTalk": "是否沟通",
}

# 网点虚假签收报表Excel字段映射 (API字段 -> Excel列名)
FALSE_SIGN_NETWORK_COLUMNS = {
    "workOrderNo": "工单号",
    "waybillNo": "运单号",
    "pddCreateTime": "工单创建时间",
    "workOrderType": "工单类型",
    "complaintTarget": "投诉对象",
    "problemTypeName": "问题类型",
    "problemDescription": "问题描述",
    "falseType": "虚假类型",
    "signType": "签收类型",
    "networkName": "网点名称",
    "networkCode": "网点编码",
    "deliveryName": "派件员",
    "deliveryCode": "派件员编码",
    "orderSourceName": "订单来源",
    "isCainiaoEnter": "是否菜鸟入仓",
    "isDispatcherOrder": "是否派件员下单",
    "isPhoneContact": "是否电话联系",
    "isPromise": "是否承诺",
    "isReback": "是否退回",
    "isTalk": "是否沟通",
}

# 兼容旧代码
FALSE_SIGN_EXCEL_COLUMNS = FALSE_SIGN_AGENT_COLUMNS

# CRM 推送配置
CRM_PUSH_URL = "http://localhost:8000/crm/api/realtime/push/simple"
CRM_PUSH_TIMEOUT = 10

# 登录页面 (代理区)
LOGIN_PAGE_URL = AGENT_CONFIG["login_url"]


def get_config_by_type(account_type: AccountType) -> dict:
    """根据账号类型获取配置"""
    if account_type == AccountType.AGENT:
        return AGENT_CONFIG
    elif account_type == AccountType.NETWORK:
        return NETWORK_CONFIG
    else:
        raise ValueError(f"未知的账号类型: {account_type}")
