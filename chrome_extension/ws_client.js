/**
 * JMS Token Manager - WebSocket客户端模块
 * 
 * 功能：
 * - WebSocket连接管理
 * - 自动重连机制
 * - 心跳保活
 * - 消息处理
 * 
 * Requirements: 6.5, 7.1, 7.2, 7.6
 */

// ============== 配置 ==============
const WS_CONFIG = {
  // 服务器地址
  SERVER_URL: 'ws://10.133.178.56:8080/ws',
  // 心跳间隔（毫秒）
  HEARTBEAT_INTERVAL: 30000,
  // 重连间隔（毫秒）
  RECONNECT_INTERVAL: 5000,
  // 最大重连次数
  MAX_RECONNECT_ATTEMPTS: 3,
  // 连接超时（毫秒）
  CONNECTION_TIMEOUT: 10000,
  // 消息超时（毫秒）
  MESSAGE_TIMEOUT: 5000
};

// ============== 连接状态枚举 ==============
const ConnectionState = {
  DISCONNECTED: 'disconnected',
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  RECONNECTING: 'reconnecting',
  FAILED: 'failed'
};

// ============== 消息类型枚举 ==============
const MessageType = {
  // 客户端发送
  REGISTER: 'register',
  TOKEN_UPLOAD: 'token_upload',
  HEARTBEAT: 'heartbeat',
  
  // 服务器发送
  REGISTER_ACK: 'register_ack',
  TOKEN_ACK: 'token_ack',
  TOKEN_EXPIRED: 'token_expired',
  TOKEN_DELETED: 'token_deleted',  // Token删除通知
  PONG: 'pong'
};

/**
 * WebSocket客户端类
 * 管理与后端服务器的WebSocket连接
 */
class WebSocketClient {
  constructor(options = {}) {
    this.serverUrl = options.serverUrl || WS_CONFIG.SERVER_URL;
    this.heartbeatInterval = options.heartbeatInterval || WS_CONFIG.HEARTBEAT_INTERVAL;
    this.reconnectInterval = options.reconnectInterval || WS_CONFIG.RECONNECT_INTERVAL;
    this.maxReconnectAttempts = options.maxReconnectAttempts || WS_CONFIG.MAX_RECONNECT_ATTEMPTS;
    
    this.websocket = null;
    this.state = ConnectionState.DISCONNECTED;
    this.reconnectAttempts = 0;
    this.heartbeatTimer = null;
    this.connectionTimer = null;
    this.extensionId = null;
    this.extensionVersion = '1.0.0';
    
    // 事件回调
    this.eventHandlers = {
      onConnect: [],
      onDisconnect: [],
      onMessage: [],
      onError: [],
      onStateChange: [],
      onTokenExpired: [],
      onTokenDeleted: [],  // Token删除事件
      onTokenAck: []
    };
    
    // 待处理的消息队列
    this.pendingMessages = [];
  }

  /**
   * 设置插件标识
   * @param {string} extensionId 插件ID
   * @param {string} version 插件版本
   */
  setExtensionInfo(extensionId, version) {
    this.extensionId = extensionId;
    this.extensionVersion = version || '1.0.0';
  }

  /**
   * 连接到WebSocket服务器
   * Requirements: 7.1
   * @returns {Promise<boolean>} 连接是否成功
   */
  async connect() {
    if (this.state === ConnectionState.CONNECTED) {
      console.log('[WSClient] Already connected');
      return true;
    }
    
    if (this.state === ConnectionState.CONNECTING) {
      console.log('[WSClient] Connection in progress');
      return false;
    }
    
    return new Promise((resolve) => {
      this._setState(ConnectionState.CONNECTING);
      console.log('[WSClient] Connecting to:', this.serverUrl);
      
      try {
        this.websocket = new WebSocket(this.serverUrl);
        
        // 设置连接超时
        this.connectionTimer = setTimeout(() => {
          if (this.state === ConnectionState.CONNECTING) {
            console.log('[WSClient] Connection timeout');
            this._handleConnectionFailure();
            resolve(false);
          }
        }, WS_CONFIG.CONNECTION_TIMEOUT);
        
        this.websocket.onopen = () => {
          this._clearConnectionTimer();
          this._handleConnectionSuccess();
          resolve(true);
        };
        
        this.websocket.onmessage = (event) => {
          this._handleMessage(event.data);
        };
        
        this.websocket.onclose = (event) => {
          this._handleClose(event);
        };
        
        this.websocket.onerror = (error) => {
          this._handleError(error);
        };
        
      } catch (error) {
        console.error('[WSClient] Failed to create WebSocket:', error);
        this._handleConnectionFailure();
        resolve(false);
      }
    });
  }

  /**
   * 断开WebSocket连接
   * Requirements: 1.5
   */
  disconnect() {
    console.log('[WSClient] Disconnecting...');
    
    this._stopHeartbeat();
    this._clearConnectionTimer();
    this.reconnectAttempts = 0;
    
    if (this.websocket) {
      // 移除事件监听器以避免触发重连
      this.websocket.onclose = null;
      this.websocket.onerror = null;
      this.websocket.close();
      this.websocket = null;
    }
    
    this._setState(ConnectionState.DISCONNECTED);
    this._emit('onDisconnect', { reason: 'manual' });
  }

  /**
   * 发送消息
   * @param {object} message 消息对象
   * @returns {boolean} 是否发送成功
   */
  send(message) {
    if (!this.isConnected()) {
      console.warn('[WSClient] Cannot send, not connected');
      // 将消息加入待发送队列
      this.pendingMessages.push(message);
      return false;
    }
    
    try {
      const messageStr = JSON.stringify(message);
      this.websocket.send(messageStr);
      console.log('[WSClient] Message sent:', message.type);
      return true;
    } catch (error) {
      console.error('[WSClient] Failed to send message:', error);
      return false;
    }
  }

  /**
   * 发送注册消息
   * Requirements: 7.2
   */
  sendRegister() {
    const message = {
      type: MessageType.REGISTER,
      payload: {
        extensionId: this.extensionId,
        version: this.extensionVersion
      },
      timestamp: Date.now()
    };
    return this.send(message);
  }

  /**
   * 发送Token上报消息
   * @param {object} tokenInfo Token信息
   */
  sendTokenUpload(tokenInfo) {
    const message = {
      type: MessageType.TOKEN_UPLOAD,
      payload: {
        token: tokenInfo.token,
        userId: tokenInfo.userId,
        account: tokenInfo.account,  // 添加账号信息
        source: tokenInfo.source,
        extensionId: this.extensionId
      },
      timestamp: Date.now()
    };
    return this.send(message);
  }

  /**
   * 发送心跳消息
   * Requirements: 7.6
   */
  sendHeartbeat() {
    const message = {
      type: MessageType.HEARTBEAT,
      payload: {
        extensionId: this.extensionId
      },
      timestamp: Date.now()
    };
    return this.send(message);
  }

  /**
   * 检查是否已连接
   * @returns {boolean}
   */
  isConnected() {
    return this.websocket && 
           this.websocket.readyState === WebSocket.OPEN && 
           this.state === ConnectionState.CONNECTED;
  }

  /**
   * 获取当前连接状态
   * @returns {string}
   */
  getState() {
    return this.state;
  }

  /**
   * 获取重连次数
   * @returns {number}
   */
  getReconnectAttempts() {
    return this.reconnectAttempts;
  }

  /**
   * 注册事件处理器
   * @param {string} event 事件名称
   * @param {Function} handler 处理函数
   */
  on(event, handler) {
    if (this.eventHandlers[event] && typeof handler === 'function') {
      this.eventHandlers[event].push(handler);
    }
  }

  /**
   * 移除事件处理器
   * @param {string} event 事件名称
   * @param {Function} handler 处理函数
   */
  off(event, handler) {
    if (this.eventHandlers[event]) {
      const index = this.eventHandlers[event].indexOf(handler);
      if (index > -1) {
        this.eventHandlers[event].splice(index, 1);
      }
    }
  }

  // ============== 私有方法 ==============

  /**
   * 处理连接成功
   */
  _handleConnectionSuccess() {
    console.log('[WSClient] Connected successfully');
    this._setState(ConnectionState.CONNECTED);
    this.reconnectAttempts = 0;
    
    // 发送注册消息
    this.sendRegister();
    
    // 启动心跳
    this._startHeartbeat();
    
    // 发送待处理的消息
    this._flushPendingMessages();
    
    this._emit('onConnect', { url: this.serverUrl });
  }

  /**
   * 处理连接失败
   */
  _handleConnectionFailure() {
    this._clearConnectionTimer();
    this._setState(ConnectionState.FAILED);
    
    // 尝试重连
    this._scheduleReconnect();
  }

  /**
   * 处理消息
   * @param {string} data 消息数据
   */
  _handleMessage(data) {
    try {
      const message = JSON.parse(data);
      console.log('[WSClient] Received message:', message.type);
      
      // 触发通用消息事件
      this._emit('onMessage', message);
      
      // 根据消息类型触发特定事件
      switch (message.type) {
        case MessageType.REGISTER_ACK:
          this._handleRegisterAck(message.payload);
          break;
          
        case MessageType.TOKEN_ACK:
          this._handleTokenAck(message.payload);
          break;
          
        case MessageType.TOKEN_EXPIRED:
          this._handleTokenExpired(message.payload);
          break;
          
        case MessageType.TOKEN_DELETED:
          this._handleTokenDeleted(message.payload);
          break;
          
        case MessageType.PONG:
          // 心跳响应，无需特殊处理
          break;
          
        default:
          console.log('[WSClient] Unknown message type:', message.type);
      }
    } catch (error) {
      console.error('[WSClient] Failed to parse message:', error);
    }
  }

  /**
   * 处理注册确认
   * @param {object} payload 消息载荷
   */
  _handleRegisterAck(payload) {
    if (payload.success) {
      console.log('[WSClient] Registration successful');
    } else {
      console.error('[WSClient] Registration failed:', payload.message);
    }
  }

  /**
   * 处理Token确认
   * @param {object} payload 消息载荷
   */
  _handleTokenAck(payload) {
    this._emit('onTokenAck', payload);
  }

  /**
   * 处理Token失效通知
   * Requirements: 6.3, 6.4
   * @param {object} payload 消息载荷
   */
  _handleTokenExpired(payload) {
    console.log('[WSClient] Token expired:', payload);
    this._emit('onTokenExpired', payload);
  }

  /**
   * 处理Token删除通知
   * @param {object} payload 消息载荷
   */
  _handleTokenDeleted(payload) {
    console.log('[WSClient] Token deleted:', payload);
    this._emit('onTokenDeleted', payload);
  }

  /**
   * 处理连接关闭
   * @param {CloseEvent} event 关闭事件
   */
  _handleClose(event) {
    console.log('[WSClient] Connection closed:', event.code, event.reason);
    
    this._stopHeartbeat();
    this._setState(ConnectionState.DISCONNECTED);
    
    this._emit('onDisconnect', {
      code: event.code,
      reason: event.reason,
      wasClean: event.wasClean
    });
    
    // 如果不是正常关闭，尝试重连
    // Requirements: 6.5
    if (!event.wasClean) {
      this._scheduleReconnect();
    }
  }

  /**
   * 处理错误
   * @param {Event} error 错误事件
   */
  _handleError(error) {
    console.error('[WSClient] WebSocket error:', error);
    this._emit('onError', { error });
  }

  /**
   * 安排重连
   * Requirements: 6.5 - 最多重试3次，间隔5秒
   */
  _scheduleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.log('[WSClient] Max reconnect attempts reached');
      this._setState(ConnectionState.FAILED);
      return;
    }
    
    this.reconnectAttempts++;
    this._setState(ConnectionState.RECONNECTING);
    
    console.log(`[WSClient] Scheduling reconnect ${this.reconnectAttempts}/${this.maxReconnectAttempts} in ${this.reconnectInterval}ms`);
    
    setTimeout(() => {
      if (this.state === ConnectionState.RECONNECTING) {
        this.connect();
      }
    }, this.reconnectInterval);
  }

  /**
   * 启动心跳
   * Requirements: 7.6 - 每30秒发送一次心跳包
   */
  _startHeartbeat() {
    this._stopHeartbeat();
    
    this.heartbeatTimer = setInterval(() => {
      if (this.isConnected()) {
        this.sendHeartbeat();
      }
    }, this.heartbeatInterval);
    
    console.log('[WSClient] Heartbeat started, interval:', this.heartbeatInterval);
  }

  /**
   * 停止心跳
   */
  _stopHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
      console.log('[WSClient] Heartbeat stopped');
    }
  }

  /**
   * 清除连接超时定时器
   */
  _clearConnectionTimer() {
    if (this.connectionTimer) {
      clearTimeout(this.connectionTimer);
      this.connectionTimer = null;
    }
  }

  /**
   * 发送待处理的消息
   */
  _flushPendingMessages() {
    while (this.pendingMessages.length > 0) {
      const message = this.pendingMessages.shift();
      this.send(message);
    }
  }

  /**
   * 设置状态
   * @param {string} newState 新状态
   */
  _setState(newState) {
    if (this.state !== newState) {
      const oldState = this.state;
      this.state = newState;
      console.log('[WSClient] State changed:', oldState, '->', newState);
      this._emit('onStateChange', { oldState, newState });
    }
  }

  /**
   * 触发事件
   * @param {string} event 事件名称
   * @param {any} data 事件数据
   */
  _emit(event, data) {
    if (this.eventHandlers[event]) {
      for (const handler of this.eventHandlers[event]) {
        try {
          handler(data);
        } catch (error) {
          console.error('[WSClient] Event handler error:', error);
        }
      }
    }
  }
}

/**
 * 创建消息工厂函数
 */
const MessageFactory = {
  /**
   * 创建注册消息
   */
  createRegister(extensionId, version) {
    return {
      type: MessageType.REGISTER,
      payload: { extensionId, version },
      timestamp: Date.now()
    };
  },
  
  /**
   * 创建Token上报消息
   */
  createTokenUpload(token, userId, source, extensionId, account) {
    return {
      type: MessageType.TOKEN_UPLOAD,
      payload: { token, userId, source, extensionId, account },
      timestamp: Date.now()
    };
  },
  
  /**
   * 创建心跳消息
   */
  createHeartbeat(extensionId) {
    return {
      type: MessageType.HEARTBEAT,
      payload: { extensionId },
      timestamp: Date.now()
    };
  }
};

// 导出模块（用于ES模块环境）
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { 
    WebSocketClient, 
    ConnectionState, 
    MessageType, 
    MessageFactory,
    WS_CONFIG 
  };
}

// 全局导出（用于浏览器环境）
if (typeof window !== 'undefined') {
  window.WebSocketClient = WebSocketClient;
  window.ConnectionState = ConnectionState;
  window.MessageType = MessageType;
  window.MessageFactory = MessageFactory;
  window.WS_CONFIG = WS_CONFIG;
}
