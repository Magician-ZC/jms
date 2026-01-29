"""
超级鹰打码平台 API 封装
官网: https://www.chaojiying.com/
"""
import requests
import hashlib
import base64
from typing import Optional


class ChaojiyingClient:
    """超级鹰打码客户端"""

    API_URL = "http://upload.chaojiying.net/Upload/Processing.php"

    def __init__(self, username: str, password: str, soft_id: str):
        """
        初始化客户端
        :param username: 超级鹰账号
        :param password: 超级鹰密码
        :param soft_id: 软件ID（在用户中心生成）
        """
        self.username = username
        self.password_md5 = hashlib.md5(password.encode("utf-8")).hexdigest()
        self.soft_id = soft_id

    def recognize(self, img_bytes: bytes, code_type: int = 9101) -> dict:
        """
        识别验证码
        :param img_bytes: 图片二进制数据
        :param code_type: 验证码类型
            - 9101: 滑动验证码（返回坐标）
            - 9102: 点选验证码
            - 9004: 1-4位数字+字母
        :return: {"err_no": 0, "err_str": "OK", "pic_id": "xxx", "pic_str": "x,y"}
        """
        data = {
            "user": self.username,
            "pass2": self.password_md5,
            "softid": self.soft_id,
            "codetype": code_type,
        }
        files = {"userfile": ("captcha.png", img_bytes)}

        try:
            response = requests.post(self.API_URL, data=data, files=files, timeout=30)
            result = response.json()
            return result
        except Exception as e:
            return {"err_no": -1, "err_str": str(e), "pic_id": "", "pic_str": ""}

    def recognize_slider(self, bg_bytes: bytes, slider_bytes: bytes = None, code_type: int = 9101) -> Optional[int]:
        """
        识别滑动验证码缺口位置
        :param bg_bytes: 背景图二进制
        :param slider_bytes: 滑块图二进制（可选）
        :param code_type: 验证码类型
            - 9101: 坐标型滑动验证码，返回 "x,y"
            - 9201: 滑块拼图，返回滑动距离
        :return: 缺口 x 坐标或滑动距离，失败返回 None
        """
        result = self.recognize(bg_bytes, code_type=code_type)
        
        print(f"[超级鹰] 原始返回: {result}")

        if result.get("err_no") == 0:
            pic_str = result.get("pic_str", "")
            print(f"[超级鹰] 识别结果: {pic_str}")
            try:
                # 返回格式可能是: "x,y" 或 "x" 或纯数字
                x = int(pic_str.split(",")[0])
                return x
            except:
                print(f"[超级鹰] 解析坐标失败: {pic_str}")
                return None
        else:
            print(f"[超级鹰] 识别失败: err_no={result.get('err_no')}, err_str={result.get('err_str')}")
            return None

    def report_error(self, pic_id: str) -> dict:
        """
        报告识别错误（可退还题分）
        :param pic_id: 图片ID
        """
        data = {
            "user": self.username,
            "pass2": self.password_md5,
            "softid": self.soft_id,
            "id": pic_id,
        }
        try:
            response = requests.post(
                "http://upload.chaojiying.net/Upload/ReportError.php",
                data=data,
                timeout=10,
            )
            return response.json()
        except:
            return {"err_no": -1}

    def get_score(self) -> int:
        """查询剩余题分"""
        data = {
            "user": self.username,
            "pass2": self.password_md5,
        }
        try:
            response = requests.post(
                "http://upload.chaojiying.net/Upload/GetScore.php",
                data=data,
                timeout=10,
            )
            result = response.json()
            if result.get("err_no") == 0:
                return int(result.get("tifen", 0))
        except:
            pass
        return 0
