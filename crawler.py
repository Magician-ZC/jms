"""
JMS数据爬取模块
使用多线程并行查询接口，每30秒推送数据到CRM
"""
import requests
import json
from datetime import datetime
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import API_ENDPOINTS, CITIES, CRM_PUSH_URL, CRM_PUSH_TIMEOUT
from utils import aggregate_by_city, print_city_stats


class JMSDataCrawler:
    """JMS数据爬取器 - 支持并行查询和数据推送"""

    def __init__(self, authtoken: Optional[str] = None, crm_url: Optional[str] = None):
        self.authtoken = authtoken or self._load_authtoken()
        self.headers = self._build_headers()
        self.crm_url = crm_url or CRM_PUSH_URL
        self.results = {}

    def _load_authtoken(self) -> str:
        """从文件加载authtoken"""
        try:
            with open("authtoken.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("authtoken", "")
        except:
            return ""

    def _build_headers(self) -> dict:
        """构建请求头"""
        return {
            "accept": "application/json, text/plain, */*",
            "authtoken": self.authtoken,
            "content-type": "application/json;charset=UTF-8",
            "lang": "zh_CN",
            "origin": "https://jms.jtexpress.com.cn",
            "referer": "https://jms.jtexpress.com.cn/",
            "routename": "orderReport",
        }

    def _build_request_body(self, page: int = 1, size: int = 10, is_ranking: bool = False) -> dict:
        """构建请求体"""
        today = datetime.now().strftime("%Y-%m-%d")
        body = {
            "startTime": f"{today} 00:00:00",
            "endTime": f"{today} 23:59:59",
            "timeType": "day",
            "regionCode": None,
            "agentName": "福建代理区",
            "agentCode": "350000",
            "agentCodes": "350000",
            "menuDesensitizationStatus": 1,
            "current": page,
            "size": size,
            "countryId": "1",
            "isvirtualAgent": 0,
        }
        if is_ranking:
            body["isAsc"] = ""
        return body

    def _fetch_api(self, name: str, url: str, body: dict) -> dict:
        """请求单个API"""
        try:
            response = requests.post(
                url,
                headers=self.headers,
                data=json.dumps(body, separators=(",", ":")),
                timeout=10,
            )
            data = response.json()
            if data.get("code") == 1 and data.get("succ"):
                return {"success": True, "name": name, "data": data}
            return {"success": False, "name": name, "error": data.get("msg")}
        except Exception as e:
            return {"success": False, "name": name, "error": str(e)}

    def _fetch_agent_page(self, page: int, size: int = 50) -> list:
        """获取加盟商排名的单页数据"""
        url = API_ENDPOINTS["当前加盟商排名"]
        body = self._build_request_body(page=page, size=size, is_ranking=True)
        try:
            response = requests.post(
                url,
                headers=self.headers,
                data=json.dumps(body, separators=(",", ":")),
                timeout=10,
            )
            data = response.json()
            if data.get("code") == 1 and data.get("succ"):
                return data.get("data", {}).get("records", [])
        except:
            pass
        return []

    def fetch_all_parallel(self) -> dict:
        """并行获取所有数据"""
        if not self.authtoken:
            print("[错误] 无有效authtoken")
            return {}

        print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始并行获取数据...")

        results = {}

        # 1. 并行获取基础数据
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {}
            for name, url in API_ENDPOINTS.items():
                is_ranking = "top_agentarea" in url
                body = self._build_request_body(is_ranking=is_ranking)
                futures[executor.submit(self._fetch_api, name, url, body)] = name

            for future in as_completed(futures):
                result = future.result()
                if result["success"]:
                    results[result["name"]] = result["data"]

        # 2. 先获取第一页确定总页数
        url = API_ENDPOINTS["当前加盟商排名"]
        body = self._build_request_body(page=1, size=50, is_ranking=True)
        first_page = self._fetch_api("加盟商排名", url, body)

        all_agents = []
        total_pages = 1

        if first_page["success"]:
            page_data = first_page["data"].get("data", {})
            all_agents.extend(page_data.get("records", []))
            total_pages = page_data.get("pages", 1)

        # 3. 并行获取剩余页
        if total_pages > 1:
            with ThreadPoolExecutor(max_workers=6) as executor:
                futures = [
                    executor.submit(self._fetch_agent_page, page)
                    for page in range(2, total_pages + 1)
                ]
                for future in as_completed(futures):
                    records = future.result()
                    all_agents.extend(records)

        print(f"[数据] 共获取 {len(all_agents)} 条加盟商数据")

        # 4. 构建推送数据
        push_data = self._build_push_data(results, all_agents)
        self.results = push_data

        return push_data

    def _build_push_data(self, api_results: dict, all_agents: list) -> dict:
        """构建推送到CRM的数据格式"""
        push_data = {
            "platform_volume": {},
            "total_volume": 0,
            "volume_change_rate": 0,
            "predicted_volume": 0,
            "top_franchisees": [],
            "city_stats": {},
        }

        # 平台发单量
        if "平台当前时间发单量" in api_results:
            records = api_results["平台当前时间发单量"].get("data", {}).get("records", [])
            for r in records:
                push_data["platform_volume"][r.get("dimension", "")] = r.get("orderCount", 0)

        # 当前发单总量
        if "当前发单总量" in api_results:
            records = api_results["当前发单总量"].get("data", {}).get("records", [])
            if records:
                push_data["total_volume"] = records[0].get("orderCount", 0)
                push_data["volume_change_rate"] = records[0].get("ringRatio", 0)

        # 预测当日总量
        if "预测当日总量" in api_results:
            records = api_results["预测当日总量"].get("data", {}).get("records", [])
            if records:
                push_data["predicted_volume"] = records[0].get("predictCount", 0)

        # TOP10加盟商
        if "当前加盟商排名" in api_results:
            records = api_results["当前加盟商排名"].get("data", {}).get("records", [])
            for r in records[:10]:
                push_data["top_franchisees"].append({
                    "name": r.get("dimension", ""),
                    "volume": r.get("orderCount", 0),
                })

        # 城市统计 - 使用公共函数
        push_data["city_stats"] = aggregate_by_city(all_agents)

        return push_data

    def push_to_crm(self, data: dict) -> bool:
        """推送数据到CRM"""
        try:
            response = requests.post(
                self.crm_url,
                json=data,
                headers={"Content-Type": "application/json"},
                timeout=CRM_PUSH_TIMEOUT,
            )
            if response.status_code == 200:
                result = response.json()
                print(f"[推送成功] 订阅者: {result.get('subscribers', 0)}")
                return True
            else:
                print(f"[推送失败] HTTP {response.status_code}")
                return False
        except Exception as e:
            print(f"[推送错误] {e}")
            return False

    def fetch_and_push(self) -> bool:
        """获取数据并推送，返回是否成功"""
        data = self.fetch_all_parallel()
        if not data:
            print("[错误] 数据获取失败")
            return False
        
        # 先保存和打印
        self._save_results(data)
        self._print_summary(data)
        
        # 最后推送
        success = self.push_to_crm(data)
        if not success:
            print("[错误] 推送失败，服务停止")
            return False
        
        return True

    def _save_results(self, data: dict):
        """保存结果到文件"""
        save_data = {
            "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": data,
        }
        with open("data_result.json", "w", encoding="utf-8") as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)

    def _print_summary(self, data: dict):
        """打印摘要"""
        print(f"\n{'='*50}")
        print(f"【发单总量】: {data.get('total_volume', 0):,} 单 (环比: {data.get('volume_change_rate', 0)}%)")
        print(f"【预测总量】: {data.get('predicted_volume', 0):,} 单")
        # 使用公共函数打印城市统计
        print_city_stats(data.get("city_stats", {}))
        print(f"{'='*50}\n")


def main():
    """主函数"""
    crawler = JMSDataCrawler()
    crawler.fetch_and_push()


if __name__ == "__main__":
    main()
