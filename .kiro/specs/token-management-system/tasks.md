# Implementation Plan: Token Management System

## Overview

本实现计划将Token管理系统分为三个主要部分：Python后端服务、Chrome浏览器插件、管理界面。采用增量开发方式，每个阶段都能独立验证功能。

## Tasks

- [-] 1. 搭建后端项目结构和核心模块
  - [x] 1.1 创建token_manager目录结构和配置文件
    - 创建 `token_manager/` 目录
    - 创建 `token_manager/__init__.py`
    - 创建 `token_manager/config.py` 配置文件
    - 添加依赖到 `requirements.txt`: fastapi, uvicorn, sqlalchemy, cryptography, websockets
    - _Requirements: 8.1_

  - [x] 1.2 实现数据库模型和初始化
    - 创建 `token_manager/models.py`
    - 实现 Token 和 ExtensionConnection 模型
    - 实现数据库初始化函数
    - _Requirements: 8.1, 8.4_

  - [ ]* 1.3 编写数据模型属性测试
    - **Property 6: Token数据持久化Round-Trip**
    - **Validates: Requirements 3.2, 8.3**

  - [x] 1.4 实现Token加密工具
    - 创建 `token_manager/crypto_utils.py`
    - 实现 encrypt/decrypt 方法
    - 实现 mask_token 脱敏方法
    - _Requirements: 9.3, 9.4_

  - [ ]* 1.5 编写加密工具属性测试
    - **Property 14: Token加密Round-Trip**
    - **Property 15: Token脱敏格式**
    - **Validates: Requirements 9.3, 9.4**

- [x] 2. 实现Token服务核心逻辑
  - [x] 2.1 实现TokenService类
    - 创建 `token_manager/token_service.py`
    - 实现 create_or_update 方法（幂等存储）
    - 实现 get_all, get_by_user, delete 方法
    - 实现 update_status, update_last_active 方法
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.4_

  - [ ]* 2.2 编写TokenService属性测试
    - **Property 4: Token格式验证**
    - **Property 5: Token存储幂等性**
    - **Property 7: Token删除有效性**
    - **Validates: Requirements 3.1, 3.3, 4.4**

  - [x] 2.3 实现Token格式验证函数
    - 创建 `token_manager/validators.py`
    - 实现 validate_token 函数
    - _Requirements: 3.1_

- [x] 3. Checkpoint - 确保核心服务测试通过
  - 运行所有属性测试和单元测试
  - 确保数据库操作正常
  - 如有问题请询问用户

- [x] 4. 实现WebSocket通信模块
  - [x] 4.1 实现WebSocket连接管理器
    - 创建 `token_manager/websocket_manager.py`
    - 实现 connect/disconnect 方法
    - 实现 send_to_extension 定向发送
    - 实现 broadcast 广播方法
    - 实现心跳检测逻辑
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.6_

  - [ ]* 4.2 编写WebSocket管理器属性测试
    - **Property 13: WebSocket连接管理**
    - **Validates: Requirements 7.3, 7.4**

  - [x] 4.3 实现消息协议处理
    - 创建 `token_manager/message_protocol.py`
    - 实现消息序列化/反序列化
    - 实现各类消息的创建函数
    - _Requirements: 7.2_

- [x] 5. 实现Token保活服务
  - [x] 5.1 实现TokenKeeper类
    - 创建 `token_manager/token_keeper.py`
    - 实现定时保活循环
    - 实现 keep_alive 单Token保活
    - 实现 check_token_validity 验证
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ]* 5.2 编写TokenKeeper属性测试
    - **Property 8: 保活成功更新活跃时间**
    - **Property 9: 认证失败标记Token过期**
    - **Validates: Requirements 5.3, 5.4**

  - [x] 5.3 实现失效通知推送
    - 在TokenKeeper中集成WebSocket通知
    - 实现 notify_token_expired 方法
    - _Requirements: 6.1_

  - [ ]* 5.4 编写失效通知属性测试
    - **Property 10: Token失效通知推送**
    - **Validates: Requirements 6.1**

- [x] 6. 实现FastAPI服务端点
  - [x] 6.1 创建FastAPI应用主文件
    - 创建 `token_manager/server.py`
    - 配置CORS和中间件
    - 实现localhost访问控制中间件
    - _Requirements: 9.1_

  - [ ]* 6.2 编写访问控制属性测试
    - **Property 16: Localhost访问控制**
    - **Validates: Requirements 9.1**

  - [x] 6.3 实现REST API端点
    - GET /api/tokens - 获取所有Token
    - POST /api/tokens - 创建/更新Token
    - DELETE /api/tokens/{id} - 删除Token
    - GET /api/tokens/{user_id} - 获取指定用户Token
    - _Requirements: 3.5, 4.1, 4.3, 4.4_

  - [x] 6.4 实现WebSocket端点
    - WS /ws - WebSocket连接端点
    - 集成WebSocketManager
    - _Requirements: 7.1_

- [x] 7. Checkpoint - 确保后端服务完整可用
  - 启动服务验证所有端点
  - 运行所有测试
  - 如有问题请询问用户

- [x] 8. 创建Chrome Extension基础结构
  - [x] 8.1 创建插件目录和manifest.json
    - 创建 `chrome_extension/` 目录
    - 创建 `chrome_extension/manifest.json` (Manifest V3)
    - 创建图标文件占位
    - _Requirements: 1.1_

  - [x] 8.2 实现Service Worker (background.js)
    - 创建 `chrome_extension/background.js`
    - 实现WebSocket连接管理
    - 实现与Content Script的消息通信
    - 实现状态管理
    - _Requirements: 1.2, 1.5, 6.5, 7.1, 7.2, 7.6_

  - [x] 8.3 实现Content Script (content.js)
    - 创建 `chrome_extension/content.js`
    - 实现页面类型检测
    - 实现登录成功监听
    - 实现Token提取逻辑
    - 实现页面跳转功能
    - _Requirements: 1.3, 1.4, 2.1, 2.2, 2.3_

  - [x] 8.4 实现Popup界面
    - 创建 `chrome_extension/popup.html`
    - 创建 `chrome_extension/popup.css`
    - 创建 `chrome_extension/popup.js`
    - 实现开关按钮和状态显示
    - _Requirements: 1.1, 2.4, 2.5, 6.2, 7.5_

- [x] 9. 实现插件核心功能
  - [x] 9.1 实现Token提取模块
    - 创建 `chrome_extension/token_extractor.js`
    - 实现从响应中提取Token
    - 实现从Cookie中提取Token
    - 实现从localStorage中提取Token
    - _Requirements: 2.2_

  - [x] 9.2 实现WebSocket客户端模块
    - 创建 `chrome_extension/ws_client.js`
    - 实现连接、断开、重连逻辑
    - 实现心跳发送
    - 实现消息处理
    - _Requirements: 6.5, 7.1, 7.2, 7.6_

  - [x] 9.3 实现失效处理逻辑
    - 在background.js中处理token_expired消息
    - 实现自动跳转到登录页
    - 实现自动开启监听
    - _Requirements: 6.3, 6.4_

- [x] 10. 创建管理界面
  - [x] 10.1 创建管理界面HTML/CSS
    - 创建 `token_manager/static/management.html`
    - 创建 `token_manager/static/management.css`
    - 实现Token列表展示布局
    - _Requirements: 4.1_

  - [x] 10.2 实现管理界面JavaScript
    - 创建 `token_manager/static/management.js`
    - 实现Token列表加载和渲染
    - 实现删除功能
    - 实现刷新功能
    - 实现WebSocket实时更新
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 10.3 实现简单密码认证
    - 实现访问密码输入界面
    - 实现密码验证逻辑
    - _Requirements: 9.2_

- [x] 11. 集成和启动脚本
  - [x] 11.1 创建服务启动入口
    - 创建 `token_manager/main.py`
    - 集成所有组件
    - 实现优雅关闭
    - _Requirements: 8.2_

  - [x] 11.2 更新项目主入口
    - 在 `main.py` 中添加Token管理服务启动选项
    - 集成到现有菜单系统
    - _Requirements: 8.2_

- [x] 12. Final Checkpoint - 完整功能验证
  - 运行所有测试确保通过
  - 验证插件安装和基本功能
  - 验证后端服务所有端点
  - 如有问题请询问用户

## Notes

- 任务标记 `*` 的为可选测试任务，可跳过以加快MVP开发
- 每个任务都引用了具体的需求条款以确保可追溯性
- Checkpoint任务用于阶段性验证，确保增量开发的正确性
- 属性测试验证通用正确性属性，单元测试验证具体示例和边界情况
- Chrome Extension需要在Chrome浏览器中手动加载测试
