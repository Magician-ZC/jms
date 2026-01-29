"""
公共工具函数模块
"""
from config import CITIES


def extract_city(agent_name: str) -> str:
    """从加盟商名称提取城市"""
    for city in CITIES:
        if agent_name.startswith(city):
            return city
    return agent_name[:2] if len(agent_name) >= 2 else "未知"


def aggregate_by_city(agents: list) -> dict:
    """
    按城市统计加盟商订单总量
    
    Args:
        agents: 加盟商数据列表，每项包含 dimension(名称) 和 orderCount(订单数)
    
    Returns:
        dict: {城市名: {"volume": 总订单量, "count": 加盟商数量}}
    """
    city_stats = {}
    
    for agent in agents:
        agent_name = agent.get("dimension", "")
        order_count = agent.get("orderCount", 0) or 0
        city = extract_city(agent_name)
        
        if city not in city_stats:
            city_stats[city] = {"volume": 0, "count": 0}
        
        city_stats[city]["volume"] += order_count
        city_stats[city]["count"] += 1
    
    # 按订单量降序排序，排除"未知"和"其他"
    sorted_stats = dict(
        sorted(
            [(k, v) for k, v in city_stats.items() if k not in ("未知", "其他")],
            key=lambda x: x[1]["volume"],
            reverse=True,
        )
    )
    
    return sorted_stats


def print_city_stats(city_stats: dict):
    """打印城市统计信息"""
    print("\n[城市统计] 各市加盟商订单总量:")
    print("-" * 50)
    total = 0
    for city, stats in city_stats.items():
        vol = stats.get("volume", 0)
        cnt = stats.get("count", 0)
        total += vol
        print(f"  {city}: {vol:,} 单 ({cnt}个加盟商)")
    print(f"  合计: {total:,} 单")
    print("-" * 50)
