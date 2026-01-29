# Requirements Document

## Introduction

Token管理系统是一个完整的解决方案，用于管理JMS平台的用户认证Token。系统由Chrome浏览器插件和Python后端服务两部分组成，实现Token的自动获取、集中管理、状态监控和失效处理。

## Glossary

- **Token_Manager**: 后端Token管理服务，负责存储、验证和管理所有Token
- **Chrome_Extension**: Chrome浏览器插件，负责监听登录、获取Token并与后端通信
- **Token**: JMS平台的用户认证凭证，用于API请求授权
- **WebSocket_Server**: 后端WebSocket服务，用于与插件进行双向实时通信
- **Management_UI**: Token管理Web界面，展示所有Token状态和操作入口
- **Token_Keeper**: Token保活服务，定时模拟操作防止Token过期
- **Login_Page**: JMS登录页面 (https://jms.jtexpress.com.cn/login)
- **Index_Page**: JMS首页 (https://jms.jtexpress.com.cn/index)

## Requirements

### Requirement 1: Chrome插件开关控制

**User Story:** As a 用户, I want 通过插件开关按钮控制Token获取流程, so that 我可以方便地启动或停止Token监听功能。

#### Acceptance Criteria

1. WHEN 用户点击插件图标, THE Chrome_Extension SHALL 显示一个包含开关按钮的弹出界面
2. WHEN 开关处于关闭状态且用户点击开关, THE Chrome_Extension SHALL 检查当前是否已有有效Token
3. WHEN 开关开启且没有有效Token且当前页面不是Login_Page, THE Chrome_Extension SHALL 自动跳转到Login_Page
4. WHEN 开关开启且当前页面是Login_Page, THE Chrome_Extension SHALL 开始监听登录成功事件
5. WHEN 用户点击开关关闭, THE Chrome_Extension SHALL 停止所有监听并断开与后端的连接

### Requirement 2: 登录监听与Token获取

**User Story:** As a 用户, I want 插件自动监听登录成功并获取Token, so that 我不需要手动复制Token。

#### Acceptance Criteria

1. WHEN 用户在Login_Page完成扫码登录, THE Chrome_Extension SHALL 监听页面跳转事件
2. WHEN 页面从Login_Page跳转到Index_Page, THE Chrome_Extension SHALL 从响应或Cookie中提取Token值
3. WHEN Token成功获取, THE Chrome_Extension SHALL 将Token发送到Token_Manager后端服务
4. WHEN Token发送成功, THE Chrome_Extension SHALL 在界面显示"Token已同步"状态
5. IF Token获取失败, THEN THE Chrome_Extension SHALL 显示错误提示并允许用户重试

### Requirement 3: 后端Token存储与管理

**User Story:** As a 管理员, I want 后端服务接收并存储所有Token, so that 我可以集中管理多个用户的Token。

#### Acceptance Criteria

1. WHEN Token_Manager接收到插件发送的Token, THE Token_Manager SHALL 验证Token格式有效性
2. WHEN Token格式有效, THE Token_Manager SHALL 将Token与用户标识、时间戳一起存储到数据库
3. WHEN 存储相同用户的新Token, THE Token_Manager SHALL 更新该用户的Token记录而非创建新记录
4. THE Token_Manager SHALL 为每个Token记录维护状态字段（active/expired/invalid）
5. WHEN Token存储成功, THE Token_Manager SHALL 返回成功响应给Chrome_Extension

### Requirement 4: Token管理Web界面

**User Story:** As a 管理员, I want 通过Web界面查看和管理所有Token, so that 我可以监控Token状态并进行必要操作。

#### Acceptance Criteria

1. THE Management_UI SHALL 展示所有已存储Token的列表，包含用户标识、Token状态、更新时间
2. WHEN 管理员访问Management_UI, THE Management_UI SHALL 实时显示每个Token的当前状态
3. THE Management_UI SHALL 提供手动刷新Token状态的功能
4. THE Management_UI SHALL 提供删除指定Token的功能
5. WHEN Token状态发生变化, THE Management_UI SHALL 自动更新显示而无需手动刷新

### Requirement 5: Token保活机制

**User Story:** As a 系统, I want 定时模拟操作保持Token激活状态, so that Token不会因长时间未使用而过期。

#### Acceptance Criteria

1. THE Token_Keeper SHALL 每隔固定时间间隔（可配置，默认5分钟）对所有active状态的Token执行保活操作
2. WHEN 执行保活操作, THE Token_Keeper SHALL 使用Token调用JMS平台的轻量级API接口
3. WHEN 保活请求返回成功, THE Token_Keeper SHALL 更新Token的最后活跃时间
4. IF 保活请求返回认证失败, THEN THE Token_Keeper SHALL 将Token状态标记为expired
5. THE Token_Keeper SHALL 记录每次保活操作的结果日志

### Requirement 6: Token失效检测与通知

**User Story:** As a 用户, I want 在Token失效时收到通知并自动跳转到登录页, so that 我可以及时重新登录获取新Token。

#### Acceptance Criteria

1. WHEN Token_Keeper检测到Token失效, THE Token_Manager SHALL 通过WebSocket向对应的Chrome_Extension发送失效通知
2. WHEN Chrome_Extension收到Token失效通知, THE Chrome_Extension SHALL 在插件界面显示"Token已失效"提示
3. WHEN Chrome_Extension收到Token失效通知, THE Chrome_Extension SHALL 自动将当前标签页跳转到Login_Page
4. WHEN 跳转到Login_Page后, THE Chrome_Extension SHALL 自动开启登录监听等待用户重新扫码
5. IF WebSocket连接断开, THEN THE Chrome_Extension SHALL 自动尝试重连（最多3次，间隔5秒）

### Requirement 7: 插件与后端双向通信

**User Story:** As a 系统, I want 插件与后端建立稳定的双向通信通道, so that 后端可以主动向插件推送消息。

#### Acceptance Criteria

1. WHEN Chrome_Extension启动, THE Chrome_Extension SHALL 尝试与WebSocket_Server建立连接
2. WHEN WebSocket连接建立成功, THE Chrome_Extension SHALL 发送注册消息包含插件唯一标识
3. THE WebSocket_Server SHALL 维护所有已连接插件的会话列表
4. WHEN 需要向特定插件发送消息, THE WebSocket_Server SHALL 根据插件标识找到对应连接并发送
5. WHEN WebSocket连接异常断开, THE Chrome_Extension SHALL 在界面显示"连接断开"状态
6. THE Chrome_Extension SHALL 支持心跳机制，每30秒发送一次心跳包保持连接

### Requirement 8: Token数据持久化

**User Story:** As a 系统, I want Token数据持久化存储, so that 服务重启后数据不会丢失。

#### Acceptance Criteria

1. THE Token_Manager SHALL 使用SQLite数据库存储Token数据
2. WHEN 服务启动, THE Token_Manager SHALL 从数据库加载所有Token记录到内存
3. WHEN Token数据发生变更, THE Token_Manager SHALL 同步更新数据库记录
4. THE Token_Manager SHALL 存储以下字段：id、user_id、token_value、status、created_at、updated_at、last_active_at
5. IF 数据库操作失败, THEN THE Token_Manager SHALL 记录错误日志并返回适当的错误响应

### Requirement 9: 安全性要求

**User Story:** As a 管理员, I want 系统具备基本的安全防护, so that Token数据不会被未授权访问。

#### Acceptance Criteria

1. THE Token_Manager SHALL 仅接受来自localhost的API请求（本地部署场景）
2. THE Management_UI SHALL 要求输入访问密码才能查看Token列表
3. THE Token_Manager SHALL 对存储的Token值进行加密存储
4. WHEN 在日志中记录Token相关信息, THE Token_Manager SHALL 对Token值进行脱敏处理（仅显示前后各8位）
5. THE WebSocket_Server SHALL 验证连接请求的来源是否为已授权的Chrome_Extension
