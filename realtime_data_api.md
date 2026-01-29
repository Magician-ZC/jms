# 实时发单数据推送 API 文档

## 概述

本文档描述了爬虫服务如何向 CRM 工作台 3D 地图推送实时发单数据。

## 接口信息

### 推送接口

**URL**: `POST /crm/api/realtime/push/simple`

**Content-Type**: `application/json`

**认证**: 无需认证（已加入白名单）

### 请求频率

建议每 **30秒** 推送一次数据。

---

## 数据格式

### 请求体 (JSON)

```json
{
  "platform_volume": {
    "桃花岛": 553038,
    "紫金山": 384246,
    "七星潭": 244650,
    "桃花岛逆向上门取件-lip": 71138,
    "逍遥峰": 28805,
    "其他": 70299
  },
  "total_volume": 1352176,
  "volume_change_rate": -0.78,
  "predicted_volume": 1710507,
  "top_franchisees": [
    {"name": "泉州加盟商一百零一(项目)", "volume": 197492},
    {"name": "泉州加盟商四十九(林清强)", "volume": 79616},
    {"name": "泉州加盟商四十八(刘毓鹏)", "volume": 79452},
    {"name": "漳州加盟商三十一(游志容)", "volume": 78933},
    {"name": "泉州加盟商一百一十九(刘志盛)", "volume": 55464},
    {"name": "泉州加盟商七十一(李艺蓉)", "volume": 54322},
    {"name": "泉州加盟商四十四(魏明聪)", "volume": 53675},
    {"name": "福州加盟商四十三(叶志艺)", "volume": 50601},
    {"name": "泉州加盟商一百零三(卢志奇)", "volume": 48282},
    {"name": "泉州加盟商四十五(魏春建)", "volume": 46007}
  ],
  "city_stats": {
    "泉州": {"volume": 753649, "count": 82},
    "漳州": {"volume": 167477, "count": 29},
    "福州": {"volume": 130370, "count": 59},
    "宁德": {"volume": 93305, "count": 15},
    "莆田": {"volume": 81306, "count": 9},
    "龙岩": {"volume": 33697, "count": 13},
    "厦门": {"volume": 33649, "count": 81},
    "南平": {"volume": 33477, "count": 16},
    "三明": {"volume": 24388, "count": 21}
  }
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `platform_volume` | object | ✅ | 平台发单量，key为平台名称，value为单量 |
| `total_volume` | int | ✅ | 当前发单总量 |
| `volume_change_rate` | float | ✅ | 环比变化率（百分比，如 -0.78 表示 -0.78%） |
| `predicted_volume` | int | ✅ | 预测当日总量 |
| `top_franchisees` | array | ✅ | TOP10加盟商排名列表 |
| `top_franchisees[].name` | string | ✅ | 加盟商名称 |
| `top_franchisees[].volume` | int | ✅ | 发单量 |
| `city_stats` | object | ✅ | 城市统计，key为城市名（不带"市"后缀） |
| `city_stats[].volume` | int | ✅ | 该城市发单量 |
| `city_stats[].count` | int | ✅ | 该城市加盟商数量 |

### 响应

**成功响应** (HTTP 200):

```json
{
  "success": true,
  "message": "数据已接收",
  "timestamp": "2025-12-17 15:37:28",
  "subscribers": 2
}
```

**错误响应** (HTTP 500):

```json
{
  "detail": "数据推送失败: 错误信息"
}
```

---

## Python 示例代码

```python
import requests
import json

# 服务器地址
BASE_URL = "http://your-server:8000"

def push_realtime_data(data: dict) -> bool:
    """
    推送实时数据到CRM工作台
    
    Args:
        data: 实时数据字典
        
    Returns:
        bool: 是否推送成功
    """
    url = f"{BASE_URL}/crm/api/realtime/push/simple"
    
    try:
        response = requests.post(
            url,
            json=data,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"[成功] 数据已推送，订阅者: {result.get('subscribers', 0)}")
            return True
        else:
            print(f"[失败] HTTP {response.status_code}: {response.text}")
            return False
            
    except Exception as e:
        print(f"[错误] 推送失败: {e}")
        return False


# 使用示例
if __name__ == "__main__":
    # 构造数据
    data = {
        "platform_volume": {
            "桃花岛": 553038,
            "紫金山": 384246,
            "七星潭": 244650,
        },
        "total_volume": 1352176,
        "volume_change_rate": -0.78,
        "predicted_volume": 1710507,
        "top_franchisees": [
            {"name": "泉州加盟商一百零一(项目)", "volume": 197492},
            {"name": "泉州加盟商四十九(林清强)", "volume": 79616},
            # ... 更多加盟商
        ],
        "city_stats": {
            "泉州": {"volume": 753649, "count": 82},
            "漳州": {"volume": 167477, "count": 29},
            "福州": {"volume": 130370, "count": 59},
            # ... 更多城市
        }
    }
    
    # 推送数据
    push_realtime_data(data)
```

---

## 其他接口

### 获取当前数据

**URL**: `GET /crm/api/realtime/current`

返回最新一次推送的数据。

### 获取城市地图数据

**URL**: `GET /crm/api/realtime/city-map-data`

返回用于3D地图展示的城市数据格式。

### SSE 实时数据流

**URL**: `GET /crm/api/realtime/stream`

前端通过 EventSource 连接此接口，实时接收数据更新。

---

## 注意事项

1. **城市名称**: `city_stats` 中的城市名不需要带"市"后缀，系统会自动处理
2. **数据频率**: 建议每30秒推送一次，过于频繁可能影响性能
3. **网络超时**: 建议设置10秒超时
4. **错误重试**: 推送失败时建议等待5秒后重试，最多重试3次
5. **数据完整性**: 每次推送需要包含完整数据，不支持增量更新

---

## 测试

可以使用项目自带的测试脚本：

```bash
# 单次测试
python tools/test_realtime_push.py

# 持续推送（模拟爬虫，每30秒）
python tools/test_realtime_push.py --continuous 30
```
