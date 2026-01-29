/**
 * JMS Token Manager - Service Worker (Background Script)
 * 
 * 功能：
 * - WebSocket连接管理
 * - 与Content Script的消息通信
 * - 状态管理
 * - Token失效处理
 * 
 * Requirements: 1.2, 1.5, 6.3, 6.4, 6.5, 7.1, 7.2, 7.6
 */

// ============== 配置 ==============
const CONFIG = {
  WS_SERVER_URL: 'ws://localhost:8080/ws',
  HEARTBEAT_INTERVAL: 30000,  // 30秒心跳
  RECONNECT_INTERVAL: 5000,   // 5秒重连间隔
  MAX_RECONNECT_ATTEMPTS: 3,  // 最大重连次数
  LOGIN_PAGE: 'https://jms.jtexpress.com.cn/login',
  INDEX_PAGE: 'https://jms.jtexpress.com.cn/index',
  // 失效处理配置
  TOKEN_EXPIRED_REDIRECT_DELAY: 1500,  // Token失效后跳转延迟（毫秒）
  AUTO_ENABLE_MONITORING_ON_EXPIRED: true  // Token失效后自动开启监听
};

// ============== 状态管理 ==============
let state = {
  isEnabled: false,           // 开关状态
  hasToken: false,            // 是否有Token
  wsConnected: false,         // WebSocket连接状态
  lastTokenTime: null,        // 最后Token获取时间
  extensionId: null,          // 插件唯一标识
  tokenExpiredReason: null,   // Token失效原因
  isAutoMonitoring: false     // 是否处于自动监听状态（Token失效后）
};

let websocket = null;
let heartbeatTimer = null;
let reconnectAttempts = 0;

// 生成或获取插件唯一标识
async function getExtensionId() {
  const result = await chrome.storage.local.get('extensionId');
  if (result.extensionId) {
    return result.extensionId;
  }
  const newId = 'ext_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
  await chrome.storage.local.set({ extensionId: newId });
  return newId;
}

// 初始化状态
async function initState() {
  state.extensionId = await getExtensionId();
  const stored = await chrome.storage.local.get(['isEnabled', 'hasToken', 'lastTokenTime']);
  state.isEnabled = stored.isEnabled || false;
  state.hasToken = stored.hasToken || false;
  state.lastTokenTime = stored.lastTokenTime || null;
  console.log('[Background] State initialized:', state);
}

// 保存状态到storage
async function saveState() {
  await chrome.storage.local.set({
    isEnabled: state.isEnabled,
    hasToken: state.hasToken,
    lastTokenTime: state.lastTokenTime,
    tokenExpiredReason: state.tokenExpiredReason,
    isAutoMonitoring: state.isAutoMonitoring
  });
}

// 获取当前状态
function getState() {
  return { ...state };
}

// 更新状态
async function setState(newState) {
  state = { ...state, ...newState };
  await saveState();
  // 通知Popup更新
  broadcastStateUpdate();
}


// ============== WebSocket连接管理 ==============

/**
 * 连接WebSocket服务器
 * Requirements: 7.1
 */
async function connectWebSocket() {
  if (websocket && websocket.readyState === WebSocket.OPEN) {
    console.log('[Background] WebSocket already connected');
    return;
  }

  try {
    console.log('[Background] Connecting to WebSocket:', CONFIG.WS_SERVER_URL);
    websocket = new WebSocket(CONFIG.WS_SERVER_URL);

    websocket.onopen = async () => {
      console.log('[Background] WebSocket connected');
      await setState({ wsConnected: true });
      reconnectAttempts = 0;
      
      // 发送注册消息 (Requirements: 7.2)
      await sendRegisterMessage();
      
      // 启动心跳 (Requirements: 7.6)
      startHeartbeat();
    };

    websocket.onmessage = (event) => {
      handleServerMessage(event.data);
    };

    websocket.onclose = async (event) => {
      console.log('[Background] WebSocket closed:', event.code, event.reason);
      await setState({ wsConnected: false });
      stopHeartbeat();
      
      // 自动重连 (Requirements: 6.5)
      if (state.isEnabled && reconnectAttempts < CONFIG.MAX_RECONNECT_ATTEMPTS) {
        reconnectAttempts++;
        console.log(`[Background] Reconnecting... attempt ${reconnectAttempts}/${CONFIG.MAX_RECONNECT_ATTEMPTS}`);
        setTimeout(connectWebSocket, CONFIG.RECONNECT_INTERVAL);
      }
    };

    websocket.onerror = (error) => {
      console.error('[Background] WebSocket error:', error);
    };

  } catch (error) {
    console.error('[Background] Failed to connect WebSocket:', error);
    await setState({ wsConnected: false });
  }
}

/**
 * 断开WebSocket连接
 * Requirements: 1.5
 */
function disconnectWebSocket() {
  stopHeartbeat();
  if (websocket) {
    websocket.close();
    websocket = null;
  }
  setState({ wsConnected: false });
  console.log('[Background] WebSocket disconnected');
}

/**
 * 发送消息到服务器
 */
function sendMessage(message) {
  if (websocket && websocket.readyState === WebSocket.OPEN) {
    websocket.send(JSON.stringify(message));
    console.log('[Background] Message sent:', message.type);
  } else {
    console.warn('[Background] Cannot send message, WebSocket not connected');
  }
}

/**
 * 发送注册消息
 * Requirements: 7.2
 */
async function sendRegisterMessage() {
  // 确保extensionId已经初始化
  if (!state.extensionId) {
    state.extensionId = await getExtensionId();
  }
  
  const message = {
    type: 'register',
    payload: {
      extensionId: state.extensionId,
      version: chrome.runtime.getManifest().version
    },
    timestamp: Date.now()
  };
  sendMessage(message);
}

/**
 * 发送Token上报消息
 */
async function sendTokenUpload(tokenInfo) {
  // 确保extensionId已经初始化
  if (!state.extensionId) {
    state.extensionId = await getExtensionId();
  }
  
  const message = {
    type: 'token_upload',
    payload: {
      token: tokenInfo.token,
      userId: tokenInfo.userId,
      account: tokenInfo.account,  // 添加账号信息
      source: tokenInfo.source,
      extensionId: state.extensionId
    },
    timestamp: Date.now()
  };
  sendMessage(message);
}

/**
 * 发送心跳消息
 * Requirements: 7.6
 */
async function sendHeartbeat() {
  // 确保extensionId已经初始化
  if (!state.extensionId) {
    state.extensionId = await getExtensionId();
  }
  
  const message = {
    type: 'heartbeat',
    payload: {
      extensionId: state.extensionId
    },
    timestamp: Date.now()
  };
  sendMessage(message);
}

// 启动心跳定时器
function startHeartbeat() {
  stopHeartbeat();
  heartbeatTimer = setInterval(sendHeartbeat, CONFIG.HEARTBEAT_INTERVAL);
  console.log('[Background] Heartbeat started');
}

// 停止心跳定时器
function stopHeartbeat() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
    console.log('[Background] Heartbeat stopped');
  }
}


// ============== 消息处理 ==============

/**
 * 处理来自服务器的消息
 */
function handleServerMessage(data) {
  try {
    const message = JSON.parse(data);
    console.log('[Background] Received server message:', message.type);

    switch (message.type) {
      case 'register_ack':
        handleRegisterAck(message.payload);
        break;
      case 'token_ack':
        handleTokenAck(message.payload);
        break;
      case 'token_expired':
        handleTokenExpired(message.payload);
        break;
      case 'token_deleted':
        handleTokenDeleted(message.payload);
        break;
      default:
        console.log('[Background] Unknown message type:', message.type);
    }
  } catch (error) {
    console.error('[Background] Failed to parse server message:', error);
  }
}

/**
 * 处理注册确认
 */
function handleRegisterAck(payload) {
  if (payload.success) {
    console.log('[Background] Registration successful');
  } else {
    console.error('[Background] Registration failed:', payload.message);
  }
}

/**
 * 处理Token上报确认
 */
async function handleTokenAck(payload) {
  if (payload.success) {
    console.log('[Background] Token uploaded successfully, id:', payload.tokenId);
    
    // 检查是否是从失效状态恢复
    const wasExpired = state.tokenExpiredReason !== null;
    
    await setState({ 
      hasToken: true, 
      lastTokenTime: Date.now(),
      tokenExpiredReason: null,
      isAutoMonitoring: false
    });
    
    // 如果是从失效状态恢复，执行恢复流程
    if (wasExpired) {
      await handleTokenRecovered();
    }
    
    // 通知Content Script Token已同步
    notifyContentScript({ 
      action: 'tokenSynced',
      tokenId: payload.tokenId
    });
  } else {
    console.error('[Background] Token upload failed:', payload.message);
    
    // 通知Content Script上传失败
    notifyContentScript({ 
      action: 'tokenSyncFailed',
      error: payload.message
    });
  }
}

/**
 * 处理Token失效通知
 * Requirements: 6.3, 6.4
 * 
 * 当收到Token失效通知时：
 * 1. 更新本地状态，标记Token已失效
 * 2. 通知Content Script显示失效提示
 * 3. 自动跳转到登录页
 * 4. 自动开启登录监听等待用户重新扫码
 */
async function handleTokenExpired(payload) {
  console.log('[Background] Token expired for user:', payload.userId, 'reason:', payload.reason);
  
  // 更新状态
  await setState({ 
    hasToken: false,
    tokenExpiredReason: payload.reason || '认证已过期',
    isAutoMonitoring: CONFIG.AUTO_ENABLE_MONITORING_ON_EXPIRED
  });
  
  // 通知所有JMS页面的Content Script
  await notifyContentScript({ 
    action: 'tokenExpired', 
    reason: payload.reason,
    userId: payload.userId
  });
  
  // 查找JMS相关的标签页
  const tabs = await chrome.tabs.query({ url: 'https://jms.jtexpress.com.cn/*' });
  
  if (tabs.length > 0) {
    // 延迟跳转，让用户看到失效提示
    setTimeout(async () => {
      try {
        // 跳转到登录页 (Requirements: 6.3)
        await chrome.tabs.update(tabs[0].id, { url: CONFIG.LOGIN_PAGE });
        console.log('[Background] Redirected to login page after token expired');
        
        // 自动开启监听 (Requirements: 6.4)
        if (CONFIG.AUTO_ENABLE_MONITORING_ON_EXPIRED) {
          await setState({ isEnabled: true });
          // 等待页面加载后通知开始监听
          setTimeout(() => {
            notifyContentScript({ action: 'startMonitoring' });
            console.log('[Background] Auto-enabled monitoring after token expired');
          }, 2000);
        }
      } catch (error) {
        console.error('[Background] Failed to redirect after token expired:', error);
      }
    }, CONFIG.TOKEN_EXPIRED_REDIRECT_DELAY);
  } else {
    // 没有打开JMS页面，创建新标签页
    try {
      await chrome.tabs.create({ url: CONFIG.LOGIN_PAGE });
      console.log('[Background] Created new tab for login after token expired');
      
      if (CONFIG.AUTO_ENABLE_MONITORING_ON_EXPIRED) {
        await setState({ isEnabled: true });
      }
    } catch (error) {
      console.error('[Background] Failed to create login tab:', error);
    }
  }
  
  // 广播状态更新给Popup
  broadcastStateUpdate();
}

/**
 * 处理Token删除通知
 * 
 * 当服务端删除Token时：
 * 1. 清除本地Token状态
 * 2. 通知Content Script
 * 3. 广播状态更新给Popup
 */
async function handleTokenDeleted(payload) {
  console.log('[Background] Token deleted for user:', payload.userId, 'reason:', payload.reason);
  
  // 更新状态，清除Token
  await setState({ 
    hasToken: false,
    lastTokenTime: null,
    tokenExpiredReason: null,
    isAutoMonitoring: false
  });
  
  // 通知所有JMS页面的Content Script
  await notifyContentScript({ 
    action: 'tokenDeleted', 
    reason: payload.reason,
    userId: payload.userId
  });
  
  // 广播状态更新给Popup
  broadcastStateUpdate();
  
  console.log('[Background] Local token state cleared after server deletion');
}

/**
 * 处理来自Content Script的消息
 * Requirements: 1.2
 */
function handleContentMessage(message, sender, sendResponse) {
  console.log('[Background] Received content message:', message.action);

  switch (message.action) {
    case 'getState':
      sendResponse(getState());
      break;
      
    case 'tokenCaptured':
      // Token捕获成功 - 异步处理，需要等待完成后再响应
      handleTokenCaptured(message.tokenInfo).then((result) => {
        sendResponse(result || { success: true });
      }).catch((error) => {
        console.error('[Background] Token capture handling failed:', error);
        sendResponse({ success: false, error: error.message });
      });
      return true; // 保持消息通道开放，等待异步响应
      
    case 'pageChanged':
      // 页面变化通知
      handlePageChanged(message.pageType, sender.tab);
      sendResponse({ success: true });
      break;
      
    case 'checkShouldMonitor':
      // 检查是否应该监听
      sendResponse({ shouldMonitor: state.isEnabled && !state.hasToken });
      break;
      
    default:
      sendResponse({ error: 'Unknown action' });
  }
  
  return true; // 保持消息通道开放
}

/**
 * 处理Token捕获
 */
async function handleTokenCaptured(tokenInfo) {
  console.log('[Background] Token captured from:', tokenInfo.source);
  
  // 发送到服务器
  sendTokenUpload(tokenInfo);
  
  // 更新本地状态，清除失效原因
  await setState({ 
    hasToken: true, 
    lastTokenTime: Date.now(),
    tokenExpiredReason: null,
    isAutoMonitoring: false
  });
  
  // 广播状态更新
  broadcastStateUpdate();
  
  // 返回成功标志
  return { success: true };
}

/**
 * 处理Token失效后的恢复
 * 当用户重新登录成功后调用
 */
async function handleTokenRecovered() {
  console.log('[Background] Token recovered after expiration');
  
  await setState({
    hasToken: true,
    tokenExpiredReason: null,
    isAutoMonitoring: false
  });
  
  // 通知Content Script
  notifyContentScript({ action: 'tokenRecovered' });
  
  // 广播状态更新
  broadcastStateUpdate();
}

/**
 * 处理页面变化
 */
function handlePageChanged(pageType, tab) {
  console.log('[Background] Page changed to:', pageType);
  // 可以在这里添加额外的页面变化处理逻辑
}

/**
 * 通知Content Script
 */
async function notifyContentScript(message) {
  const tabs = await chrome.tabs.query({ url: 'https://jms.jtexpress.com.cn/*' });
  for (const tab of tabs) {
    try {
      await chrome.tabs.sendMessage(tab.id, message);
    } catch (error) {
      console.log('[Background] Failed to send message to tab:', tab.id);
    }
  }
}

/**
 * 广播状态更新给所有监听者
 */
function broadcastStateUpdate() {
  chrome.runtime.sendMessage({ action: 'stateUpdated', state: getState() }).catch(() => {
    // Popup可能未打开，忽略错误
  });
}


// ============== Popup通信处理 ==============

/**
 * 处理来自Popup的消息
 */
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // 来自Content Script的消息
  if (sender.tab) {
    return handleContentMessage(message, sender, sendResponse);
  }
  
  // 来自Popup的消息
  console.log('[Background] Received popup message:', message.action);
  
  switch (message.action) {
    case 'getState':
      sendResponse(getState());
      break;
      
    case 'toggleSwitch':
      handleToggleSwitch().then(sendResponse);
      return true; // 异步响应
      
    case 'forceRefresh':
      handleForceRefresh().then(sendResponse);
      return true;
      
    default:
      sendResponse({ error: 'Unknown action' });
  }
  
  return true;
});

/**
 * 处理开关切换
 * Requirements: 1.2, 1.5
 */
async function handleToggleSwitch() {
  const newEnabled = !state.isEnabled;
  console.log('[Background] Toggle switch to:', newEnabled);
  
  if (newEnabled) {
    // 开启
    await setState({ isEnabled: true });
    
    // 连接WebSocket
    await connectWebSocket();
    
    // 检查是否需要跳转到登录页
    if (!state.hasToken) {
      const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tabs.length > 0) {
        const currentUrl = tabs[0].url || '';
        if (!currentUrl.includes('jms.jtexpress.com.cn/login')) {
          // 跳转到登录页 (Requirements: 1.3)
          await chrome.tabs.update(tabs[0].id, { url: CONFIG.LOGIN_PAGE });
        }
      }
    }
    
    // 通知Content Script开始监听
    notifyContentScript({ action: 'startMonitoring' });
    
  } else {
    // 关闭
    await setState({ isEnabled: false });
    
    // 断开WebSocket连接
    disconnectWebSocket();
    
    // 通知Content Script停止监听
    notifyContentScript({ action: 'stopMonitoring' });
  }
  
  return getState();
}

/**
 * 强制刷新状态
 * 从服务器获取真实的Token状态
 */
async function handleForceRefresh() {
  console.log('[Background] Force refreshing state from server...');
  
  try {
    // 从服务器获取Token列表
    const response = await fetch('http://localhost:8080/api/tokens?include_expired=true');
    if (response.ok) {
      const data = await response.json();
      const tokens = data.tokens || [];
      
      // 检查是否有活跃的Token
      const hasActiveToken = tokens.some(t => t.status === 'active');
      
      if (!hasActiveToken && state.hasToken) {
        // 服务器没有Token但本地显示有，需要同步
        console.log('[Background] Server has no token, clearing local state');
        await setState({
          hasToken: false,
          lastTokenTime: null,
          tokenExpiredReason: null
        });
      } else if (hasActiveToken && !state.hasToken) {
        // 服务器有Token但本地显示没有，需要同步
        console.log('[Background] Server has token, updating local state');
        await setState({
          hasToken: true,
          lastTokenTime: Date.now()
        });
      }
      
      console.log('[Background] State refreshed, hasToken:', state.hasToken);
    }
  } catch (error) {
    console.error('[Background] Failed to refresh state from server:', error);
  }
  
  return getState();
}

// ============== 初始化 ==============

// Service Worker启动时初始化
initState().then(() => {
  console.log('[Background] Service Worker initialized');
  
  // 如果之前是开启状态，自动重连
  if (state.isEnabled) {
    connectWebSocket();
  }
});

// 监听插件安装/更新事件
chrome.runtime.onInstalled.addListener((details) => {
  console.log('[Background] Extension installed/updated:', details.reason);
  if (details.reason === 'install') {
    // 首次安装，初始化状态
    setState({
      isEnabled: false,
      hasToken: false,
      lastTokenTime: null
    });
  }
});

// 监听标签页更新，用于检测页面跳转
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url) {
    if (tab.url.includes('jms.jtexpress.com.cn')) {
      // JMS页面加载完成，通知Content Script
      chrome.tabs.sendMessage(tabId, { 
        action: 'pageLoaded',
        isEnabled: state.isEnabled,
        hasToken: state.hasToken
      }).catch(() => {
        // Content Script可能还未加载
      });
    }
  }
});

console.log('[Background] Service Worker script loaded');
