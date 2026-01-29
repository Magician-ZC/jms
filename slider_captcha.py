"""
滑动验证码自动识别模块
支持两种识别方式：
1. 超级鹰打码平台（优先，识别率高）
2. OpenCV 模板匹配（备用，免费）
"""
import os
import random
import asyncio
import cv2
import numpy as np
from pathlib import Path
from typing import Optional

# 尝试导入超级鹰客户端
try:
    from chaojiying import ChaojiyingClient
    HAS_CHAOJIYING = True
except ImportError:
    HAS_CHAOJIYING = False


class SliderCaptcha:
    """滑动验证码处理器"""

    def __init__(self, debug: bool = False, use_chaojiying: bool = True):
        """
        :param debug: 是否保存调试图片
        :param use_chaojiying: 是否使用超级鹰（需配置环境变量）
        """
        self.debug = debug
        self.screenshot_dir = Path("captcha_screenshots")
        if debug:
            self.screenshot_dir.mkdir(exist_ok=True)

        # 初始化超级鹰客户端
        self.cjy_client = None
        if use_chaojiying and HAS_CHAOJIYING:
            cjy_user = os.getenv("CJY_USERNAME")
            cjy_pass = os.getenv("CJY_PASSWORD")
            cjy_soft_id = os.getenv("CJY_SOFT_ID")
            if cjy_user and cjy_pass and cjy_soft_id:
                self.cjy_client = ChaojiyingClient(cjy_user, cjy_pass, cjy_soft_id)
                print("[验证码] 超级鹰客户端已初始化")

    async def solve(self, page) -> bool:
        """自动解决滑动验证码"""
        try:
            # 1. 查找验证码 frame
            captcha_frame = await self._find_captcha_frame(page)
            if not captcha_frame:
                print("[验证码] 未检测到验证码弹窗")
                return False

            print("[验证码] 检测到验证码，开始处理...")

            # 2. 截取背景图（和滑块图）
            bg_img, slider_img, bg_bytes = await self._capture_images_with_bytes(captcha_frame)
            if bg_img is None:
                print("[验证码] 截图失败")
                return False

            # 3. 获取滑动轨道实际宽度，计算缩放比例
            track_width = await self._get_track_width(captcha_frame)
            bg_width = bg_img.shape[1]
            scale = track_width / bg_width if track_width > 0 else 1.0
            print(f"[验证码] 图片宽度: {bg_width}px, 轨道宽度: {track_width}px, 缩放比例: {scale:.3f}")

            # 4. 识别缺口位置（优先超级鹰，失败回退 OpenCV）
            gap_x = await self._recognize_gap(bg_img, slider_img, bg_bytes)
            if gap_x <= 0:
                print("[验证码] 无法识别缺口位置")
                return False

            # 5. 计算滑动距离（应用缩放比例）
            # 超级鹰返回的是图片上的像素坐标，需要转换为实际滑动距离
            actual_gap_x = int(gap_x * scale)
            slider_offset = int(50 * scale)  # 滑块初始位置也要缩放
            distance = actual_gap_x - slider_offset
            print(f"[验证码] 原始缺口: {gap_x}px, 缩放后: {actual_gap_x}px, 滑动距离: {distance}px")

            if distance <= 0:
                print("[验证码] 滑动距离无效")
                return False

            # 6. 找到滑块并拖动
            slider = await self._find_slider(captcha_frame)
            if not slider:
                print("[验证码] 未找到滑块")
                return False

            success = await self._drag_slider(page, slider, distance)
            if success:
                print("[验证码] 滑动完成，等待验证结果...")
                await page.wait_for_timeout(2000)

            return success

        except Exception as e:
            print(f"[验证码] 处理异常: {e}")
            return False

    async def _get_track_width(self, frame) -> int:
        """获取滑动轨道的实际宽度"""
        track_selectors = [
            "#tcOperation",  # 腾讯防水墙滑动区域
            ".tc-slider-normal",
            ".tc-operation",
            "#slideBlock",
        ]
        for selector in track_selectors:
            try:
                elem = frame.locator(selector).first
                if await elem.is_visible(timeout=500):
                    box = await elem.bounding_box()
                    if box and box["width"] > 100:
                        return int(box["width"])
            except:
                continue
        return 0

    async def _recognize_gap(self, bg_img, slider_img, bg_bytes: bytes) -> int:
        """
        识别缺口位置
        优先使用超级鹰，失败时回退到 OpenCV
        """
        gap_x = 0

        # 方式1: 超级鹰打码
        if self.cjy_client and bg_bytes:
            print("[验证码] 使用超级鹰识别...")
            gap_x = self.cjy_client.recognize_slider(bg_bytes, None) or 0
            if gap_x > 0:
                print(f"[验证码] 超级鹰识别成功: {gap_x}px")
                return gap_x
            print("[验证码] 超级鹰识别失败，回退到 OpenCV")

        # 方式2: OpenCV 模板匹配
        if slider_img is not None:
            print("[验证码] 使用 OpenCV 识别...")
            gap_x = self._template_match(bg_img, slider_img)

        return gap_x

    async def _find_captcha_frame(self, page):
        """查找验证码框架"""
        try:
            tcaptcha_iframe = page.frame_locator("#tcaptcha_iframe")
            slider = tcaptcha_iframe.locator(".tc-slider-normal").first
            if await slider.is_visible(timeout=2000):
                print("[验证码] 检测到腾讯防水墙 iframe")
                return tcaptcha_iframe
        except:
            pass

        for frame in page.frames:
            try:
                slider = frame.locator(".tc-slider-normal").first
                if await slider.is_visible(timeout=500):
                    return frame
            except:
                continue
        return page

    async def _capture_images_with_bytes(self, frame):
        """
        截取背景图和滑块图
        返回: (bg_img, slider_img, bg_bytes)
        """
        bg_img = None
        slider_img = None
        bg_bytes = None

        try:
            # 背景图 - 整个验证码图片区域
            bg_selectors = ["#slideBg", ".tc-bg-img", "#tcImgArea img"]
            for selector in bg_selectors:
                try:
                    elem = frame.locator(selector).first
                    if await elem.is_visible(timeout=1000):
                        screenshot = await elem.screenshot()
                        bg_bytes = screenshot  # 保存原始字节
                        bg_img = cv2.imdecode(
                            np.frombuffer(screenshot, np.uint8), cv2.IMREAD_COLOR
                        )
                        print(f"[验证码] 背景图截取成功: {selector}")
                        break
                except:
                    continue

            # 如果没找到单独的背景图，截取整个图片区域
            if bg_img is None:
                for selector in ["#tcImgArea", ".tc-imgarea"]:
                    try:
                        elem = frame.locator(selector).first
                        if await elem.is_visible(timeout=1000):
                            screenshot = await elem.screenshot()
                            bg_bytes = screenshot
                            bg_img = cv2.imdecode(
                                np.frombuffer(screenshot, np.uint8), cv2.IMREAD_COLOR
                            )
                            print(f"[验证码] 背景图截取成功: {selector}")
                            break
                    except:
                        continue

            # 滑块图 - 截取拼图块本身（OpenCV 备用方案需要）
            slider_selectors = [
                "#slideBlock",
                ".tc-fg-item",
                "img.tc-fg-item",
            ]
            for selector in slider_selectors:
                try:
                    elem = frame.locator(selector).first
                    if await elem.is_visible(timeout=1000):
                        box = await elem.bounding_box()
                        if box and box["width"] > 30 and box["height"] > 30:
                            screenshot = await elem.screenshot()
                            slider_img = cv2.imdecode(
                                np.frombuffer(screenshot, np.uint8), cv2.IMREAD_COLOR
                            )
                            print(
                                f"[验证码] 滑块图截取成功: {selector} ({int(box['width'])}x{int(box['height'])})"
                            )
                            break
                except:
                    continue

            # 保存调试图片
            if self.debug and bg_img is not None:
                import time
                ts = int(time.time() * 1000)
                cv2.imwrite(str(self.screenshot_dir / f"bg_{ts}.png"), bg_img)
                if slider_img is not None:
                    cv2.imwrite(str(self.screenshot_dir / f"slider_{ts}.png"), slider_img)

        except Exception as e:
            print(f"[验证码] 截图异常: {e}")

        return bg_img, slider_img, bg_bytes

    def _template_match(self, bg_img, slider_img) -> int:
        """
        用滑块图作为模板，在背景图右侧区域搜索缺口位置
        关键：只在右半部分搜索，排除左边滑块本身的干扰
        """
        if bg_img is None or slider_img is None:
            print("[验证码] 图片为空")
            return 0

        bg_height, bg_width = bg_img.shape[:2]
        slider_height, slider_width = slider_img.shape[:2]
        print(f"[验证码] 背景图: {bg_width}x{bg_height}, 滑块: {slider_width}x{slider_height}")

        # 关键：只在背景图右半部分搜索缺口，排除左边滑块区域
        # 左边滑块大约在 x=0~100 的位置，从 x=100 开始搜索
        search_start_x = max(80, slider_width + 20)  # 至少跳过滑块宽度+20px
        bg_right = bg_img[:, search_start_x:]
        
        print(f"[验证码] 搜索区域: x >= {search_start_x}px")

        # 转灰度
        bg_gray = cv2.cvtColor(bg_right, cv2.COLOR_BGR2GRAY)
        slider_gray = cv2.cvtColor(slider_img, cv2.COLOR_BGR2GRAY)

        # Canny 边缘检测
        bg_edge = cv2.Canny(bg_gray, 50, 150)
        slider_edge = cv2.Canny(slider_gray, 50, 150)

        # 模板匹配
        result = cv2.matchTemplate(bg_edge, slider_edge, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        # 缺口位置 = 搜索起点 + 匹配位置 + 滑块宽度/2
        gap_x = search_start_x + max_loc[0] + slider_width // 2

        print(f"[验证码] 模板匹配度: {max_val:.2%}")
        print(f"[验证码] 匹配位置(相对): x={max_loc[0]}, y={max_loc[1]}")
        print(f"[验证码] 缺口中心位置(绝对): {gap_x}px")

        # 保存调试图
        if self.debug:
            import time
            ts = int(time.time() * 1000)
            debug_img = bg_img.copy()
            abs_x = search_start_x + max_loc[0]
            cv2.rectangle(
                debug_img,
                (abs_x, max_loc[1]),
                (abs_x + slider_width, max_loc[1] + slider_height),
                (0, 255, 0),
                2
            )
            # 画一条线标记搜索起点
            cv2.line(debug_img, (search_start_x, 0), (search_start_x, bg_height), (0, 0, 255), 1)
            cv2.imwrite(str(self.screenshot_dir / f"match_{ts}.png"), debug_img)
            cv2.imwrite(str(self.screenshot_dir / f"bg_edge_{ts}.png"), bg_edge)
            cv2.imwrite(str(self.screenshot_dir / f"slider_edge_{ts}.png"), slider_edge)

        return gap_x

    def _column_scan(self, edge_img, width) -> int:
        """列扫描法：在边缘图右半部分找边缘密集区域"""
        search_start = int(width * 0.35)
        search_end = int(width * 0.85)

        # 按列统计边缘像素
        col_sums = []
        for x in range(search_start, search_end):
            col_sums.append((x, np.sum(edge_img[:, x] > 0)))

        # 滑动窗口找边缘密度最高的区域
        window = 50
        max_sum = 0
        gap_x = 0

        for i in range(len(col_sums) - window):
            s = sum(c[1] for c in col_sums[i : i + window])
            if s > max_sum:
                max_sum = s
                gap_x = col_sums[i + window // 2][0]

        print(f"[验证码] 列扫描缺口位置: {gap_x}px")
        return gap_x

    def _edge_detect(self, bg_img) -> int:
        """边缘检测找缺口（备用方法）"""
        gray = cv2.cvtColor(bg_img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 100, 200)
        return self._column_scan(edges, bg_img.shape[1])

        print(f"[验证码] 边缘检测缺口位置: {gap_x}px")
        return gap_x

    async def _find_slider(self, frame):
        """查找滑块元素"""
        for selector in [".tc-slider-normal", "#tcOperation .tc-slider-normal"]:
            try:
                elem = frame.locator(selector).first
                if await elem.is_visible(timeout=1000):
                    return elem
            except:
                continue
        return None

    async def _drag_slider(self, page, slider, distance: int) -> bool:
        """
        模拟人类拖动滑块
        参考 test.py 中的 simulateSlideBar 实现：
        - 分步移动，每步约 20px
        - 每步间隔约 80ms
        - 最后松开前有短暂延迟
        """
        try:
            box = await slider.bounding_box()
            if not box:
                return False

            start_x = box["x"] + box["width"] / 2
            start_y = box["y"] + box["height"] / 2

            # 使用 test.py 风格的分步滑动
            track = self._generate_track_v2(distance)

            await page.mouse.move(start_x, start_y)
            await page.mouse.down()

            current_x = start_x
            for move_x, move_y, delay in track:
                current_x += move_x
                await page.mouse.move(current_x, start_y + move_y)
                await asyncio.sleep(delay / 1000)

            # 松开前短暂延迟（参考 test.py 的 80ms）
            await asyncio.sleep(0.08)
            await page.mouse.up()
            return True

        except Exception as e:
            print(f"[验证码] 拖动失败: {e}")
            return False

    def _generate_track(self, distance: int) -> list:
        """生成人类化拖动轨迹（原版）"""
        track = []
        current = 0
        mid = distance * 0.7

        while current < distance:
            if current < mid:
                move = random.randint(8, 18)
            else:
                move = random.randint(2, 6)

            if current + move > distance:
                move = distance - current

            y_offset = random.randint(-2, 2)
            delay = random.randint(10, 25)
            track.append((move, y_offset, delay))
            current += move

        # 微调回弹
        if random.random() > 0.5:
            track.append((-2, 0, 50))
            track.append((2, 0, 30))

        return track

    def _generate_track_v2(self, distance: int) -> list:
        """
        生成滑动轨迹（参考 test.py 的 simulateSlideBar）
        - 每步移动约 20px
        - 每步间隔约 80ms
        - 添加轻微的 y 轴抖动模拟人类行为
        """
        track = []
        current = 0
        step_size = 20  # 参考 test.py 的步长

        while current < distance:
            # 计算本次移动距离
            if current + step_size < distance:
                move = step_size + random.randint(-3, 3)  # 添加随机性
            else:
                move = distance - current  # 最后一步精确到位

            # 轻微 y 轴抖动
            y_offset = random.randint(-1, 1)
            # 间隔约 80ms，添加随机性
            delay = 80 + random.randint(-10, 10)

            track.append((move, y_offset, delay))
            current += move

        return track
