# JMS爬虫系统

极兔JMS系统登录爬虫，支持滑动验证码。

## 安装

```bash
cd jms_crawler
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

## 使用

### 1. 登录获取Token

```bash
python auth.py
```

浏览器会自动打开登录页面，账号密码已自动填充：
1. 点击登录按钮
2. 完成滑动验证
3. 系统自动捕获验证结果并登录

### 2. 使用爬虫

```python
from crawler import JMSCrawler

crawler = JMSCrawler()
user_info = crawler.get_user_info()
```

## 文件说明

- `auth.py` - 登录认证模块
- `crawler.py` - 爬虫主模块
- `config.py` - 配置文件
- `session.json` - 登录会话（自动生成）
- `cookies.json` - Cookies（自动生成）
