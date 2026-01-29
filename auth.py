"""
JMS登录认证模块
使用Playwright全程模拟浏览器操作，获取authtoken后启动数据采集
"""
import os
import json
import asyncio
import sys
from datetime import datetime
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from slider_captcha import SliderCaptcha
from config import LOGIN_PAGE_URL, FALSE_SIGN_REPORT_PAGE_URL

# 加载环境变量
load_dotenv()

# 从 .env 读取配置
JMS_ACCOUNT = os.getenv("JMS_ACCOUNT", "")
JMS_PASSWORD = os.getenv("JMS_PASSWORD", "")


class JMSAuth:
    """JMS登录认证器"""
    
    def __init__(self):
        self.is_logged_in = False
        self.authtoken = None
    
    def _save_authtoken(self, token: str):
        """保存authtoken到文件"""
        self.authtoken = token
        token_data = {
            "authtoken": token,
            "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        with open("authtoken.json", "w", encoding="utf-8") as f:
            json.dump(token_data, f, ensure_ascii=False, indent=2)
        print(f"[保存] authtoken已保存到 authtoken.json")
    
    async def run(self):
        """主运行入口"""
        async with async_playwright() as p:
            # 使用持久化上下文，保存登录状态
            user_data_dir = "./browser_data"
            
            # 启动浏览器，添加反检测参数
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
            
            # 使用 stealth 插件隐藏自动化特征
            stealth = Stealth()
            await stealth.apply_stealth_async(page)
            
            # 注册响应监听器捕获登录token
            page.on("response", lambda resp: asyncio.create_task(self._handle_response(resp)))
            
            # 执行登录
            login_success = await self._login(page)
            
            if not login_success:
                print("\n[错误] 登录失败，程序退出")
                print("[提示] 请检查账号密码或手动完成验证码")
                await context.close()
                return
            
            # 登录成功，关闭浏览器
            print("\n[完成] 登录成功，authtoken 已保存到 authtoken.json")
            await context.close()
            print("[浏览器] 已关闭")
            
            # 启动数据采集循环
            await self._start_data_crawler()
    
    async def _handle_response(self, response):
        """处理响应，捕获登录token"""
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
        print("请完成滑动验证后等待自动跳转")
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
            checkbox_clicked = False
            try:
                checkbox_elem = page.locator("span.ap-a-check:not(.ap-a-check-bg)").last
                if await checkbox_elem.is_visible(timeout=1000):
                    await checkbox_elem.click()
                    print("[自动] 已勾选协议复选框")
                    checkbox_clicked = True
                    await page.wait_for_timeout(500)
                else:
                    checked_elem = page.locator("span.ap-a-check.ap-a-check-bg").last
                    if await checked_elem.is_visible(timeout=500):
                        print("[自动] 协议复选框已是勾选状态")
                        checkbox_clicked = True
            except:
                pass
            
            if not checkbox_clicked:
                print("[警告] 未能找到或勾选协议复选框")
            
            # 5. 点击登录
            login_btn = page.locator("button:has-text('登')").first
            if await login_btn.is_visible():
                await login_btn.click()
                print("[自动] 已点击登录按钮")
            
            # 5.1 处理"请先同意协议"弹窗
            await page.wait_for_timeout(1000)
            agree_btn_selectors = [
                "button:has-text('同 意')",
                "button:has-text('同意')",
                "div.el-dialog button:has-text('同')",
                ".el-message-box__btns button:nth-child(2)",
            ]
            for selector in agree_btn_selectors:
                try:
                    agree_btn = page.locator(selector).first
                    if await agree_btn.is_visible(timeout=2000):
                        await agree_btn.click()
                        print("[自动] 已点击'同意'按钮")
                        await page.wait_for_timeout(1000)
                        break
                except:
                    continue
            
            # 6. 尝试自动处理滑动验证码
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
        """点击刷新按钮获取新验证码"""
        try:
            iframe = page.frame_locator("#tcaptcha_iframe")
            refresh_selectors = [
                "img.tc-action-icon[alt*='刷新']",
                "img.tc-action-icon",
                "[aria-label*='刷新']",
                "#reload",
                "[class*='refresh']",
            ]
            
            for selector in refresh_selectors:
                try:
                    btn = iframe.locator(selector).first
                    if await btn.is_visible(timeout=1000):
                        await btn.click()
                        print("[验证码] 已点击刷新按钮")
                        return True
                except:
                    continue
            
            for selector in refresh_selectors:
                try:
                    btn = page.locator(selector).first
                    if await btn.is_visible(timeout=500):
                        await btn.click()
                        print("[验证码] 已点击刷新按钮(主页面)")
                        return True
                except:
                    continue
                    
            print("[验证码] 未找到刷新按钮")
            return False
        except Exception as e:
            print(f"[验证码] 刷新失败: {e}")
            return False
    
    async def _start_data_crawler(self):
        """启动数据采集循环"""
        from crawler import JMSDataCrawler
        
        print("\n[数据采集] 开始后台循环采集，间隔 30 秒")
        print("[数据采集] 按 Ctrl+C 退出")
        print("=" * 50)
        
        crawler = JMSDataCrawler(self.authtoken)
        query_count = 0
        
        while True:
            try:
                query_count += 1
                print(f"\n[第 {query_count} 次采集]")
                
                success = crawler.fetch_and_push()
                if not success:
                    print("[服务停止] 推送失败")
                    break
                
                print(f"等待 30 秒...")
                await asyncio.sleep(30)
            except KeyboardInterrupt:
                print("\n\n[退出] 程序已停止")
                break
            except asyncio.CancelledError:
                print("\n\n[退出] 程序已停止")
                break


async def main():
    """主函数"""
    auth = JMSAuth()
    await auth.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
