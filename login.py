"""
JMS统一登录模块
负责浏览器登录、获取authtoken
"""
import os
import json
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page, BrowserContext
from slider_captcha import SliderCaptcha
from config import LOGIN_PAGE_URL

load_dotenv()

JMS_ACCOUNT = os.getenv("JMS_ACCOUNT", "")
JMS_PASSWORD = os.getenv("JMS_PASSWORD", "")


class JMSLogin:
    """JMS登录器"""

    def __init__(self):
        self.is_logged_in = False
        self.authtoken = None
        self.context: BrowserContext = None
        self.page: Page = None

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

    @staticmethod
    def load_authtoken() -> str:
        """从文件加载authtoken"""
        try:
            with open("authtoken.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("authtoken", "")
        except:
            return ""

    async def _handle_response(self, response):
        """捕获登录响应中的token"""
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

    async def login(self) -> bool:
        """
        执行登录流程，获取有效的authtoken
        Returns:
            是否成功获取token
        """
        # 先尝试使用已保存的token
        saved_token = self.load_authtoken()
        if saved_token:
            print(f"[Token] 尝试使用已保存的token: {saved_token[:30]}...")
            # 验证token是否有效
            if await self._verify_token_via_browser(saved_token):
                self.authtoken = saved_token
                print("[Token] token有效，无需重新登录")
                return True
            else:
                print("[Token] token已失效，需要重新登录...")
        
        # token无效或不存在，执行浏览器登录
        return await self._browser_login()

    async def _verify_token_via_browser(self, token: str) -> bool:
        """通过浏览器验证token是否有效"""
        async with async_playwright() as p:
            user_data_dir = "./browser_data"
            
            context = await p.chromium.launch_persistent_context(
                user_data_dir,
                headless=True,  # 验证时使用无头模式
                args=["--disable-blink-features=AutomationControlled"],
            )
            
            try:
                page = await context.new_page()
                await page.goto(LOGIN_PAGE_URL, timeout=30000, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)
                
                # 检查是否在登录页还是已登录
                current_url = page.url
                is_valid = "/index" in current_url
                
                await context.close()
                return is_valid
            except Exception as e:
                print(f"[验证] 验证失败: {e}")
                await context.close()
                return False

    async def _browser_login(self) -> bool:
        """通过浏览器执行登录"""
        async with async_playwright() as p:
            user_data_dir = "./browser_data"

            self.context = await p.chromium.launch_persistent_context(
                user_data_dir,
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--no-sandbox",
                ],
                ignore_default_args=["--enable-automation"],
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            )

            # 关闭旧页面
            for old_page in self.context.pages:
                await old_page.close()

            self.page = await self.context.new_page()

            # 反检测脚本
            await self.page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            """)

            # 监听登录响应
            self.page.on("response", lambda resp: asyncio.create_task(self._handle_response(resp)))

            # 访问首页
            print("\n[检查] 访问首页...")
            await self.page.goto(LOGIN_PAGE_URL, timeout=60000, wait_until="domcontentloaded")
            await self.page.wait_for_timeout(2000)

            # 检查页面是否正常加载
            content = await self.page.content()
            if len(content) < 1000 or "科 技 信 息 平 台" not in content:
                print("[警告] 页面可能未正常加载，尝试刷新...")
                await self.page.reload(wait_until="networkidle")
                await self.page.wait_for_timeout(3000)

            # 检查是否已登录
            current_url = self.page.url
            if "/index" in current_url:
                print("[已登录] 检测到已登录状态")
                # 已登录但token失效，需要重新登录获取新token
                # 先退出登录
                await self._logout()
            
            # 执行登录
            print("[登录] 开始登录流程...")
            success = await self._do_login()
            
            await self.context.close()
            print("[浏览器] 已关闭")
            
            return success and self.authtoken is not None

    async def _logout(self):
        """退出登录"""
        try:
            # 尝试点击退出按钮
            logout_btn = self.page.locator("text=退出").first
            if await logout_btn.is_visible(timeout=2000):
                await logout_btn.click()
                await self.page.wait_for_timeout(2000)
                print("[退出] 已退出登录")
        except:
            pass

    async def _do_login(self) -> bool:
        """执行登录操作"""
        print(f"\n{'='*50}")
        print("开始登录流程...")
        print(f"{'='*50}\n")

        # 确保在登录页
        if "/index" in self.page.url:
            await self.page.goto(LOGIN_PAGE_URL, timeout=60000, wait_until="domcontentloaded")
        await self.page.wait_for_timeout(2000)

        try:
            # 1. 勾选"已阅读"
            checkbox = self.page.locator("input[type='checkbox']").first
            if await checkbox.is_visible(timeout=2000):
                await checkbox.click()
                print("[自动] 已勾选'已阅读'")
                await self.page.wait_for_timeout(500)

            # 2. 点击"切换账号登录"
            switch_btn = self.page.locator("text=切换账号登录").first
            if await switch_btn.is_visible(timeout=2000):
                await switch_btn.click()
                print("[自动] 已点击'切换账号登录'")
                await self.page.wait_for_timeout(1000)

            # 3. 填充账号密码
            account_input = self.page.locator("input[type='text']").first
            if await account_input.is_visible(timeout=2000):
                await account_input.fill(JMS_ACCOUNT)
                print(f"[自动] 账号: {JMS_ACCOUNT}")

            await self.page.wait_for_timeout(300)

            pwd_input = self.page.locator("input[type='password']").first
            if await pwd_input.is_visible(timeout=2000):
                await pwd_input.fill(JMS_PASSWORD)
                print("[自动] 密码已填充")

            await self.page.wait_for_timeout(500)

            # 4. 勾选协议复选框
            try:
                checkbox_elem = self.page.locator("span.ap-a-check:not(.ap-a-check-bg)").last
                if await checkbox_elem.is_visible(timeout=1000):
                    await checkbox_elem.click()
                    print("[自动] 已勾选协议复选框")
                    await self.page.wait_for_timeout(500)
            except:
                pass

            # 5. 点击登录
            login_btn = self.page.locator("button:has-text('登')").first
            if await login_btn.is_visible(timeout=2000):
                await login_btn.click()
                print("[自动] 已点击登录按钮")

            # 6. 处理"同意"弹窗
            await self.page.wait_for_timeout(1000)
            for selector in ["button:has-text('同 意')", "button:has-text('同意')"]:
                try:
                    agree_btn = self.page.locator(selector).first
                    if await agree_btn.is_visible(timeout=2000):
                        await agree_btn.click()
                        print("[自动] 已点击'同意'按钮")
                        await self.page.wait_for_timeout(1000)
                        break
                except:
                    continue

            # 7. 处理滑动验证码
            await self.page.wait_for_timeout(2000)
            await self._solve_captcha()

        except Exception as e:
            print(f"[警告] 自动操作异常: {e}")

        # 等待登录成功
        for _ in range(120):  # 最多等待2分钟
            if self.is_logged_in:
                print("\n[成功] 登录完成!")
                await self.page.wait_for_timeout(2000)
                return True
            await self.page.wait_for_timeout(1000)

        print("[超时] 登录等待超时")
        return False

    async def _solve_captcha(self, max_retries: int = 3):
        """尝试自动解决滑动验证码"""
        captcha_solver = SliderCaptcha(debug=True)

        for attempt in range(max_retries):
            print(f"[验证码] 第 {attempt + 1} 次尝试...")

            if attempt > 0:
                await self._refresh_captcha()
                await self.page.wait_for_timeout(2000)

            success = await captcha_solver.solve(self.page)

            if success:
                await self.page.wait_for_timeout(2000)
                if self.is_logged_in:
                    print("[验证码] 验证成功!")
                    return True
                print("[验证码] 验证可能失败，等待重试...")
                await self.page.wait_for_timeout(1000)
            else:
                print("[验证码] 自动识别失败，请手动完成...")
                break

        print("[验证码] 自动处理未成功，请手动完成滑动验证")
        return False

    async def _refresh_captcha(self):
        """刷新验证码"""
        try:
            iframe = self.page.frame_locator("#tcaptcha_iframe")
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
