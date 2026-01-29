/**
 * JMS Token Manager - Popup Script
 * 
 * 功能：
 * - 开关按钮控制
 * - 状态显示
 * - 与Background通信
 * 
 * Requirements: 1.1, 2.4, 2.5, 6.2, 7.5
 */

// ============== DOM元素 ==============
const mainSwitch = document.getElementById('mainSwitch');
const switchHint = document.getElementById('switchHint');
const connectionStatus = document.getElementById('connectionStatus');
const tokenStatus = document.getElementById('tokenStatus');
const lastUpdate = document.getElementById('lastUpdate');
const refreshBtn = document.getElementById('refreshBtn');

// ============== 状态管理 ==============
let currentState = {
  isEnabled: false,
  hasToken: false,
  wsConnected: false,
  lastTokenTime: null,
  tokenExpiredReason: null,
  isAutoMonitoring: false
};

// ============== 初始化 ==============

/**
 * 初始化Popup
 */
async function init() {
  console.log('[Popup] Initializing...');
  
  // 绑定事件
  bindEvents();
  
  // 获取当前状态
  await fetchState();
  
  // 监听状态更新
  listenForStateUpdates();
  
  console.log('[Popup] Initialized');
}

/**
 * 绑定事件处理
 */
function bindEvents() {
  // 主开关
  mainSwitch.addEventListener('change', handleSwitchToggle);
  
  // 刷新按钮
  refreshBtn.addEventListener('click', handleRefresh);
}

/**
 * 监听来自Background的状态更新
 */
function listenForStateUpdates() {
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === 'stateUpdated') {
      updateUI(message.state);
    }
    sendResponse({ received: true });
    return true;
  });
}

// ============== 状态获取与更新 ==============

/**
 * 从Background获取状态
 */
async function fetchState() {
  try {
    const response = await chrome.runtime.sendMessage({ action: 'getState' });
    if (response) {
      currentState = response;
      updateUI(currentState);
    }
  } catch (error) {
    console.error('[Popup] Failed to fetch state:', error);
    showMessage('获取状态失败', 'error');
  }
}

/**
 * 更新UI显示
 */
function updateUI(state) {
  currentState = state;
  
  // 更新开关状态
  mainSwitch.checked = state.isEnabled;
  updateSwitchHint(state);
  
  // 更新连接状态
  updateConnectionStatus(state.wsConnected, state.isEnabled);
  
  // 更新Token状态（包含失效信息）
  updateTokenStatus(state.hasToken, state.tokenExpiredReason, state.isAutoMonitoring);
  
  // 更新最后更新时间
  updateLastUpdate(state.lastTokenTime);
  
  // 如果Token失效，显示提示
  if (state.tokenExpiredReason && !state.hasToken) {
    showMessage('Token已失效: ' + state.tokenExpiredReason, 'warning');
  }
}

/**
 * 更新开关提示文字
 */
function updateSwitchHint(state) {
  if (!state.isEnabled) {
    switchHint.textContent = '点击开关启动Token获取';
  } else if (!state.wsConnected) {
    switchHint.textContent = '正在连接服务器...';
  } else if (state.tokenExpiredReason && state.isAutoMonitoring) {
    switchHint.textContent = 'Token已失效，等待重新登录';
  } else if (!state.hasToken) {
    switchHint.textContent = '等待登录获取Token';
  } else {
    switchHint.textContent = 'Token监听已启动';
  }
}

/**
 * 更新连接状态显示
 * Requirements: 7.5
 */
function updateConnectionStatus(connected, enabled) {
  const dot = connectionStatus.querySelector('.status-dot');
  const text = connectionStatus.querySelector('.status-text');
  
  if (!enabled) {
    dot.className = 'status-dot disconnected';
    text.textContent = '未启动';
  } else if (connected) {
    dot.className = 'status-dot connected';
    text.textContent = '已连接';
  } else {
    dot.className = 'status-dot connecting';
    text.textContent = '连接中...';
  }
}

/**
 * 更新Token状态显示
 * Requirements: 2.4, 6.2
 */
function updateTokenStatus(hasToken, tokenExpiredReason, isAutoMonitoring) {
  const dot = tokenStatus.querySelector('.status-dot');
  const text = tokenStatus.querySelector('.status-text');
  
  if (hasToken) {
    dot.className = 'status-dot active';
    text.textContent = 'Token已同步';
  } else if (tokenExpiredReason) {
    // Token已失效
    dot.className = 'status-dot expired';
    text.textContent = 'Token已失效';
    
    // 如果正在自动监听，显示等待重新登录
    if (isAutoMonitoring) {
      text.textContent = '等待重新登录';
    }
  } else {
    dot.className = 'status-dot none';
    text.textContent = '无Token';
  }
}

/**
 * 更新最后更新时间
 */
function updateLastUpdate(timestamp) {
  if (timestamp) {
    const date = new Date(timestamp);
    lastUpdate.textContent = formatTime(date);
  } else {
    lastUpdate.textContent = '-';
  }
}

/**
 * 格式化时间
 */
function formatTime(date) {
  const now = new Date();
  const diff = now - date;
  
  if (diff < 60000) {
    return '刚刚';
  } else if (diff < 3600000) {
    return Math.floor(diff / 60000) + '分钟前';
  } else if (diff < 86400000) {
    return Math.floor(diff / 3600000) + '小时前';
  } else {
    return date.toLocaleDateString('zh-CN', {
      month: 'numeric',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  }
}


// ============== 事件处理 ==============

/**
 * 处理开关切换
 * Requirements: 1.1, 2.5
 */
async function handleSwitchToggle() {
  const newState = mainSwitch.checked;
  console.log('[Popup] Switch toggled to:', newState);
  
  // 禁用开关防止重复点击
  mainSwitch.disabled = true;
  
  try {
    const response = await chrome.runtime.sendMessage({ action: 'toggleSwitch' });
    if (response) {
      updateUI(response);
      
      if (response.isEnabled) {
        showMessage('Token监听已启动', 'success');
      } else {
        showMessage('Token监听已停止', 'info');
      }
    }
  } catch (error) {
    console.error('[Popup] Failed to toggle switch:', error);
    showMessage('操作失败，请重试', 'error');
    // 恢复开关状态
    mainSwitch.checked = !newState;
  } finally {
    mainSwitch.disabled = false;
  }
}

/**
 * 处理刷新按钮点击
 */
async function handleRefresh() {
  console.log('[Popup] Refresh clicked');
  
  refreshBtn.disabled = true;
  refreshBtn.querySelector('.btn-icon').style.animation = 'spin 1s linear infinite';
  
  try {
    await fetchState();
    showMessage('状态已刷新', 'success');
  } catch (error) {
    console.error('[Popup] Failed to refresh:', error);
    showMessage('刷新失败', 'error');
  } finally {
    refreshBtn.disabled = false;
    refreshBtn.querySelector('.btn-icon').style.animation = '';
  }
}

// ============== 消息提示 ==============

/**
 * 显示消息提示
 */
function showMessage(text, type = 'info') {
  // 检查是否已有消息元素
  let messageEl = document.querySelector('.message');
  
  if (!messageEl) {
    // 创建消息元素
    messageEl = document.createElement('div');
    messageEl.className = 'message';
    
    // 插入到开关区域之前
    const switchSection = document.querySelector('.switch-section');
    switchSection.parentNode.insertBefore(messageEl, switchSection);
  }
  
  // 设置消息内容和类型
  messageEl.textContent = text;
  messageEl.className = `message ${type} show`;
  
  // 3秒后自动隐藏
  setTimeout(() => {
    messageEl.classList.remove('show');
  }, 3000);
}

// ============== 添加旋转动画样式 ==============

const style = document.createElement('style');
style.textContent = `
  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
`;
document.head.appendChild(style);

// ============== 启动 ==============

// DOM加载完成后初始化
document.addEventListener('DOMContentLoaded', init);
