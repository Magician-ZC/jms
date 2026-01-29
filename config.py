"""
公共配置模块
"""

# 福建省主要城市
CITIES = ["福州", "厦门", "泉州", "漳州", "莆田", "龙岩", "三明", "南平", "宁德"]

# JMS API 基础URL
API_BASE_URL = "https://jmsgw.jtexpress.com.cn/businessplan/bigdataReport/detailDir"

# 数据驾舱 API 端点
API_ENDPOINTS = {
    "平台当前时间发单量": f"{API_BASE_URL}/datacabin/dws_order_source_ratio",
    "当前发单总量": f"{API_BASE_URL}/datacabin/dws_order_totalandper_bydate",
    "预测当日总量": f"{API_BASE_URL}/datacabin/dws_order_totalandper_predict",
    "当前加盟商排名": f"{API_BASE_URL}/datacabin/dws_order_top_agentarea",
}

# 虚假签收报表 API
FALSE_SIGN_REPORT_API = f"{API_BASE_URL}/businessin/sqs_false_sign_rate_detail"
FALSE_SIGN_REPORT_PAGE_URL = "https://idata.jtexpress.com.cn/app/serviceQualityIndex/FalseSignReportPC?title=%E8%99%9A%E5%81%87%E7%AD%BE%E6%94%B6%E6%8A%A5%E8%A1%A8&moduleCode=serviceQualityIndex&resourceId=32180"

# 虚假签收报表Excel字段映射 (API字段 -> Excel列名)
FALSE_SIGN_EXCEL_COLUMNS = {
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

# CRM 推送配置
CRM_PUSH_URL = "http://localhost:8000/crm/api/realtime/push/simple"
CRM_PUSH_TIMEOUT = 10

# 登录页面
LOGIN_PAGE_URL = "https://jms.jtexpress.com.cn/"
