"""
虚假签收报表下载器
先登录获取token，再下载报表导出Excel
"""
import os
import json
import asyncio
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from slider_captcha import SliderCaptcha
from config import LOGIN_PAGE_URL, FALSE_SIGN_REPORT_PAGE_URL
from false_sign_report import FalseSignReport

load_dotenv()

JMS_ACCOUNT = os.getenv("JMS_ACCOUNT", "")
JMS_PASSWORD = os.getenv("JMS_PASSWORD", "")


class FalseSignDownloader:
    """虚假签收报表下载器 - 登录+下载"""

    def __init__(self):
        self.is_logged_in = False
        self.authtoken = None
        self.captured_headers = {}  # 保存完整请求头

    def _save_authtoken(self, token: str):
        """保存authtoken到文件"""
        self.authtoken = token
        token_data = {
            "authtoken": token,
            "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        with open("authtoken.json", "w", encoding="utf-8") as f:
            json.dump(token_data, f, ensure_ascii=False, indent=2)
        print(f"[保存] authtoken已保存")

    async def run(self, date: str = None):
        """
        主运行入口
        Args:
            date: 报表日期，格式 YYYY-MM-DD，默认昨天
        """
        async with async_playwright() as p:
            user_data_dir = "./browser_data"

            context = await p.chromium.launch_persistent_context(
                user_data_dir,
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--no-sandbox",
                ],
                ignore_default_args=["--enable-automation"],
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )

            page = context.pages[0] if context.pages else await context.new_page()

            stealth = Stealth()
            await stealth.apply_stealth_async(page)

            # 监听所有请求，捕获authtoken
            page.on("request", lambda req: asyncio.create_task(self._capture_token_from_request(req)))
            page.on("response", lambda resp: asyncio.create_task(self._handle_response(resp)))

            # 1. 先访问首页
            print("\n[检查] 访问首页...")
            await page.goto(LOGIN_PAGE_URL, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            # 检查是否已经在首页（已登录状态）
            current_url = page.url
            if "/index" in current_url:
                print("[已登录] 检测到已登录状态")
            else:
                # 需要登录
                print("[未登录] 需要执行登录流程...")
                login_success = await self._login(page)
                if not login_success:
                    print("\n[错误] 登录失败")
                    await context.close()
                    return

            # 2. 通过模拟点击导航到虚假签收报表页面
            print("\n[导航] 通过菜单进入虚假签收报表...")
            page = await self._navigate_to_false_sign_report(page)
            
            # 等待页面加载并捕获token
            await page.wait_for_timeout(3000)
            
            # 检查是否捕获到token
            if not self.authtoken:
                print("[警告] 未从请求中捕获到token，尝试从localStorage获取...")
                token = await page.evaluate("() => localStorage.getItem('authtoken')")
                if token:
                    self.authtoken = token
                    self._save_authtoken(token)
            
            if not self.authtoken:
                print("[错误] 无法获取有效token")
                await context.close()
                return
                
            print(f"[成功] 获取到token: {self.authtoken[:30]}...")

            # 3. 关闭浏览器
            await context.close()
            print("[浏览器] 已关闭")
            
            # 4. 使用API下载数据并导出Excel
            print("\n[下载] 开始下载虚假签收报表...")
            report = FalseSignReport(authtoken=self.authtoken)
            target_date = date or (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            output_path = report.export_excel(date=target_date)

            if output_path:
                print(f"\n[完成] 报表已导出: {output_path}")
            else:
                print("\n[失败] 报表导出失败")
    
    async def _navigate_to_false_sign_report(self, page):
        """通过菜单导航到虚假签收报表页面"""
        try:
            # 获取context用于监听新页面
            context = page.context
            
            # 1. 点击"数据平台" - 会打开新标签页
            print("[点击] 数据平台...")
            data_platform = page.locator("text=数据平台").first
            if await data_platform.is_visible(timeout=5000):
                # 监听新页面打开
                async with context.expect_page() as new_page_info:
                    await data_platform.click()
                
                new_page = await new_page_info.value
                await new_page.wait_for_load_state("domcontentloaded")
                print(f"[新页面] URL: {new_page.url}")
                
                # 在新页面上也注册token捕获
                new_page.on("request", lambda req: asyncio.create_task(self._capture_token_from_request(req)))
                
                # 切换到新页面继续操作
                page = new_page
                await page.wait_for_timeout(2000)
            
            # 2. 在数据平台页面，点击左侧菜单"服务质量"
            print("[点击] 服务质量...")
            service_quality_selectors = [
                "span:has-text('服务质量')",
                "div.menu-item:has-text('服务质量')",
                "text=服务质量",
            ]
            for selector in service_quality_selectors:
                try:
                    elem = page.locator(selector).first
                    if await elem.is_visible(timeout=2000):
                        await elem.click()
                        await page.wait_for_timeout(1500)
                        print(f"[成功] 点击服务质量")
                        break
                except:
                    continue
            
            # 3. 点击"体验监控"展开子菜单
            print("[点击] 体验监控...")
            experience_selectors = [
                "span:has-text('体验监控')",
                "div:has-text('体验监控')",
                "text=体验监控",
            ]
            for selector in experience_selectors:
                try:
                    elem = page.locator(selector).first
                    if await elem.is_visible(timeout=2000):
                        await elem.click()
                        await page.wait_for_timeout(1500)
                        print(f"[成功] 点击体验监控")
                        break
                except:
                    continue
            
            # 4. 点击"虚假签收报表"
            print("[点击] 虚假签收报表...")
            false_sign_selectors = [
                "span:has-text('虚假签收报表')",
                "div:has-text('虚假签收报表')",
                "text=虚假签收报表",
                "a:has-text('虚假签收报表')",
            ]
            for selector in false_sign_selectors:
                try:
                    elem = page.locator(selector).first
                    if await elem.is_visible(timeout=2000):
                        await elem.click()
                        await page.wait_for_timeout(3000)
                        print(f"[成功] 点击虚假签收报表")
                        print(f"[页面] 当前URL: {page.url}")
                        break
                except:
                    continue
            
            # 5. 点击"明细"标签触发API请求
            print("[点击] 明细标签...")
            await page.wait_for_timeout(2000)
            detail_selectors = [
                "div[id='tab-detail']",
                "div:has-text('明细'):not(:has-text('汇总'))",
                "#tab-detail",
                "[role='tab']:has-text('明细')",
                "text=明细",
            ]
            for selector in detail_selectors:
                try:
                    elem = page.locator(selector).first
                    if await elem.is_visible(timeout=2000):
                        await elem.click()
                        await page.wait_for_timeout(5000)  # 等待API请求完成
                        print(f"[成功] 点击明细标签")
                        break
                except:
                    continue
            
            # 等待报表页面加载完成，API请求会自动触发
            await page.wait_for_timeout(3000)
            print("[成功] 已进入虚假签收报表页面")
            
            return page  # 返回当前操作的页面
            
        except Exception as e:
            print(f"[错误] 导航失败: {e}")
            return page

            # 4. 使用API下载数据并导出Excel
            print("\n[下载] 开始下载虚假签收报表...")
            report = FalseSignReport(authtoken=self.authtoken)
            target_date = date or (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            output_path = report.export_excel(date=target_date)

            if output_path:
                print(f"\n[完成] 报表已导出: {output_path}")
            else:
                print("\n[失败] 报表导出失败")

    async def _capture_token_from_request(self, request):
        """从请求头中捕获authtoken和完整headers"""
        url = request.url
        # 关注jmsgw的API请求，特别是虚假签收相关的
        if "jmsgw.jtexpress.com.cn" not in url:
            return
        
        try:
            headers = request.headers
            token = headers.get("authtoken")
            
            # 如果是虚假签收API，打印完整请求头用于调试
            if "sqs_false_sign" in url or "businessin" in url:
                print(f"\n[调试] 虚假签收API请求头:")
                for key, value in headers.items():
                    print(f"  {key}: {value[:50] if len(str(value)) > 50 else value}")
                
                if token:
                    self.authtoken = token
                    self._save_authtoken(token)
                    # 保存完整headers供后续使用
                    self.captured_headers = dict(headers)
                    print(f"[捕获] 从虚假签收API获取到token: {token[:30]}...")
            elif token and not self.authtoken:
                self.authtoken = token
                self._save_authtoken(token)
                print(f"[捕获] 从API请求中获取到token: {token[:30]}...")
        except Exception as e:
            print(f"[错误] 捕获请求头失败: {e}")

    async def _handle_response(self, response):
        """捕获登录token"""
        url = response.url
        if "jmsgw.jtexpress.com.cn" not in url:
            return

        try:
            if "webOauth/login" in url:
                data = await response.json()
                if data.get("succ") and data.get("data", {}).get("token"):
                    self.is_logged_in = True
                    token = data['data']['token']
                    print(f"[登录成功] Token: {token[:30]}...")
                    self._save_authtoken(token)
        except:
            pass

    async def _login(self, page):
        """执行登录流程"""
        print(f"\n{'='*50}")
        print("开始登录流程...")
        print(f"{'='*50}\n")

        await page.goto(LOGIN_PAGE_URL, timeout=60000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        try:
            # 1. 勾选"已阅读"
            checkbox = page.locator("input[type='checkbox']").first
            if await checkbox.is_visible():
                await checkbox.click()
                print("[自动] 已勾选'已阅读'")
                await page.wait_for_timeout(500)

            # 2. 点击"切换账号登录"
            switch_btn = page.locator("text=切换账号登录").first
            if await switch_btn.is_visible():
                await switch_btn.click()
                print("[自动] 已点击'切换账号登录'")
                await page.wait_for_timeout(1000)

            # 3. 填充账号密码
            account_input = page.locator("input[type='text']").first
            if await account_input.is_visible():
                await account_input.fill(JMS_ACCOUNT)
                print(f"[自动] 账号: {JMS_ACCOUNT}")

            await page.wait_for_timeout(300)

            pwd_input = page.locator("input[type='password']").first
            if await pwd_input.is_visible():
                await pwd_input.fill(JMS_PASSWORD)
                print("[自动] 密码已填充")

            await page.wait_for_timeout(500)

            # 4. 勾选协议复选框
            try:
                checkbox_elem = page.locator("span.ap-a-check:not(.ap-a-check-bg)").last
                if await checkbox_elem.is_visible(timeout=1000):
                    await checkbox_elem.click()
                    print("[自动] 已勾选协议复选框")
                    await page.wait_for_timeout(500)
            except:
                pass

            # 5. 点击登录
            login_btn = page.locator("button:has-text('登')").first
            if await login_btn.is_visible():
                await login_btn.click()
                print("[自动] 已点击登录按钮")

            # 5.1 处理"同意"弹窗
            await page.wait_for_timeout(1000)
            for selector in ["button:has-text('同 意')", "button:has-text('同意')"]:
                try:
                    agree_btn = page.locator(selector).first
                    if await agree_btn.is_visible(timeout=2000):
                        await agree_btn.click()
                        print("[自动] 已点击'同意'按钮")
                        await page.wait_for_timeout(1000)
                        break
                except:
                    continue

            # 6. 处理滑动验证码
            await page.wait_for_timeout(2000)
            await self._solve_captcha(page)

        except Exception as e:
            print(f"[警告] 自动操作失败，请手动操作: {e}")

        # 等待登录成功
        for _ in range(300):
            if self.is_logged_in:
                print("\n[成功] 登录完成!")
                await page.wait_for_timeout(3000)
                return True
            await page.wait_for_timeout(1000)

        print("[超时] 登录等待超时")
        return False

    async def _solve_captcha(self, page, max_retries: int = 3):
        """尝试自动解决滑动验证码"""
        captcha_solver = SliderCaptcha(debug=True)

        for attempt in range(max_retries):
            print(f"[验证码] 第 {attempt + 1} 次尝试...")

            if attempt > 0:
                await self._refresh_captcha(page)
                await page.wait_for_timeout(2000)

            success = await captcha_solver.solve(page)

            if success:
                await page.wait_for_timeout(2000)
                if self.is_logged_in:
                    print("[验证码] 验证成功!")
                    return True
                print("[验证码] 验证可能失败，等待重试...")
                await page.wait_for_timeout(1000)
            else:
                print("[验证码] 自动识别失败，请手动完成...")
                break

        print("[验证码] 自动处理未成功，请手动完成滑动验证")
        return False

    async def _refresh_captcha(self, page):
        """刷新验证码"""
        try:
            iframe = page.frame_locator("#tcaptcha_iframe")
            for selector in ["img.tc-action-icon", "[class*='refresh']"]:
                try:
                    btn = iframe.locator(selector).first
                    if await btn.is_visible(timeout=1000):
                        await btn.click()
                        print("[验证码] 已刷新")
                        return True
                except:
                    continue
        except:
            pass
        return False


async def main():
    """主函数"""
    # 支持命令行传入日期参数
    date = None
    if len(sys.argv) > 1:
        date = sys.argv[1]
        print(f"[参数] 指定日期: {date}")

    downloader = FalseSignDownloader()
    await downloader.run(date=date)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[退出] 用户中断")
