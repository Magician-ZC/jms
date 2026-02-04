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
const settingsBtn = document.getElementById('settingsBtn');
const settingsPanel = document.getElementById('settingsPanel');
const serverAddress = document.getElementById('serverAddress');
const cancelSettings = document.getElementById('cancelSettings');
const saveSettings = document.getElementById('saveSettings');
const typeAgent = document.getElementById('typeAgent');
const typeNetwork = document.getElementById('typeNetwork');
const checkUpdateBtn = document.getElementById('checkUpdateBtn');
const doUpdateBtn = document.getElementById('doUpdateBtn');
const currentVersionEl = document.getElementById('currentVersion');
const latestVersionEl = document.getElementById('latestVersion');
const latestVersionRow = document.getElementById('latestVersionRow');
const updateStatus = document.getElementById('updateStatus');

// ============== 常量 ==============
const CURRENT_VERSION = chrome.runtime.getManifest().version;

// ============== 状态管理 ==============
let currentState = {
  isEnabled: false,
  hasToken: false,
  wsConnected: false,
  lastTokenTime: null,
  tokenExpiredReason: null,
  isAutoMonitoring: false,
  accountType: 'agent'
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
  
  // 设置按钮
  settingsBtn.addEventListener('click', showSettings);
  cancelSettings.addEventListener('click', hideSettings);
  saveSettings.addEventListener('click', handleSaveSettings);
  
  // 账号类型选择
  typeAgent.addEventListener('click', () => handleTypeChange('agent'));
  typeNetwork.addEventListener('click', () => handleTypeChange('network'));
  
  // 更新按钮
  checkUpdateBtn.addEventListener('click', handleCheckUpdate);
  doUpdateBtn.addEventListener('click', handleDoUpdate);
  
  // 显示当前版本
  currentVersionEl.textContent = 'v' + CURRENT_VERSION;
}

/**
 * 处理账号类型切换
 */
async function handleTypeChange(type) {
  if (currentState.accountType === type) return;
  
  // 更新UI
  typeAgent.classList.toggle('active', type === 'agent');
  typeNetwork.classList.toggle('active', type === 'network');
  
  // 保存到storage
  await chrome.storage.local.set({ accountType: type });
  currentState.accountType = type;
  
  // 通知background更新
  try {
    const response = await chrome.runtime.sendMessage({ action: 'updateAccountType', accountType: type });
    const typeName = type === 'agent' ? '代理区' : '网点';
    showMessage(`已切换到${typeName}模式`, 'success');
    
    // 刷新状态显示（会获取新类型的Token状态）
    await fetchState();
  } catch (error) {
    console.error('[Popup] Failed to update account type:', error);
  }
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
  
  // 更新账号类型选择
  updateAccountTypeUI(state.accountType || 'agent');
  
  // 如果Token失效，显示提示
  if (state.tokenExpiredReason && !state.hasToken) {
    showMessage('Token已失效: ' + state.tokenExpiredReason, 'warning');
  }
}

/**
 * 更新账号类型UI
 */
function updateAccountTypeUI(type) {
  typeAgent.classList.toggle('active', type === 'agent');
  typeNetwork.classList.toggle('active', type === 'network');
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
    // 先让background从服务器同步状态
    await chrome.runtime.sendMessage({ action: 'forceRefresh' });
    // 然后获取最新状态
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

// ============== 设置功能 ==============

/**
 * 显示设置面板
 */
async function showSettings() {
  // 加载当前服务器地址
  const result = await chrome.storage.local.get('serverAddress');
  serverAddress.value = result.serverAddress || '';
  settingsPanel.style.display = 'block';
}

/**
 * 隐藏设置面板
 */
function hideSettings() {
  settingsPanel.style.display = 'none';
}

/**
 * 保存设置
 */
async function handleSaveSettings() {
  const address = serverAddress.value.trim();
  
  if (!address) {
    showMessage('请输入服务器地址', 'error');
    return;
  }
  
  // 验证格式
  if (!/^[\w.-]+:\d+$/.test(address)) {
    showMessage('地址格式错误，应为 IP:端口', 'error');
    return;
  }
  
  // 保存到storage
  await chrome.storage.local.set({ serverAddress: address });
  
  // 通知background更新
  try {
    await chrome.runtime.sendMessage({ action: 'updateServerAddress', address });
    showMessage('设置已保存，重新连接中...', 'success');
    hideSettings();
    
    // 刷新状态
    setTimeout(fetchState, 1000);
  } catch (error) {
    showMessage('保存失败: ' + error.message, 'error');
  }
}

// ============== 在线更新功能 ==============

let latestVersionInfo = null;

/**
 * 检查更新
 */
async function handleCheckUpdate() {
  checkUpdateBtn.disabled = true;
  updateStatus.textContent = '正在检查更新...';
  updateStatus.className = 'update-status checking';
  doUpdateBtn.style.display = 'none';
  latestVersionRow.style.display = 'none';
  
  try {
    // 获取服务器地址
    const result = await chrome.storage.local.get('serverAddress');
    const serverAddr = result.serverAddress || 'localhost:8080';
    
    // 请求版本信息
    const response = await fetch(`http://${serverAddr}/api/extension/version`);
    if (!response.ok) {
      throw new Error('服务器响应错误: ' + response.status);
    }
    
    const data = await response.json();
    latestVersionInfo = data;
    
    // 显示最新版本
    latestVersionRow.style.display = 'flex';
    latestVersionEl.textContent = 'v' + data.version;
    
    // 比较版本
    if (compareVersions(data.version, CURRENT_VERSION) > 0) {
      latestVersionEl.classList.add('new-version');
      updateStatus.textContent = `发现新版本！更新内容: ${data.changelog || '功能优化'}`;
      updateStatus.className = 'update-status has-update';
      doUpdateBtn.style.display = 'flex';
    } else {
      latestVersionEl.classList.remove('new-version');
      updateStatus.textContent = '当前已是最新版本';
      updateStatus.className = 'update-status no-update';
    }
  } catch (error) {
    console.error('[Popup] Check update failed:', error);
    updateStatus.textContent = '检查更新失败: ' + error.message;
    updateStatus.className = 'update-status error';
  } finally {
    checkUpdateBtn.disabled = false;
  }
}

/**
 * 执行更新
 */
async function handleDoUpdate() {
  if (!latestVersionInfo) {
    showMessage('请先检查更新', 'error');
    return;
  }
  
  doUpdateBtn.disabled = true;
  updateStatus.textContent = '正在下载更新包...';
  updateStatus.className = 'update-status updating';
  
  try {
    // 获取服务器地址
    const result = await chrome.storage.local.get('serverAddress');
    const serverAddr = result.serverAddress || 'localhost:8080';
    
    // 下载更新包
    const downloadUrl = `http://${serverAddr}/api/extension/download`;
    
    // 创建下载链接
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.download = `jms-token-manager-v${latestVersionInfo.version}.zip`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    updateStatus.textContent = '更新包已下载，请手动安装：\n1. 解压下载的zip文件\n2. 打开 chrome://extensions\n3. 删除旧版本插件\n4. 加载已解压的扩展程序';
    updateStatus.className = 'update-status has-update';
    updateStatus.style.whiteSpace = 'pre-line';
    
    showMessage('更新包已下载', 'success');
  } catch (error) {
    console.error('[Popup] Update failed:', error);
    updateStatus.textContent = '下载失败: ' + error.message;
    updateStatus.className = 'update-status error';
    showMessage('下载更新失败', 'error');
  } finally {
    doUpdateBtn.disabled = false;
  }
}

/**
 * 比较版本号
 * @returns 1 if v1 > v2, -1 if v1 < v2, 0 if equal
 */
function compareVersions(v1, v2) {
  const parts1 = v1.split('.').map(Number);
  const parts2 = v2.split('.').map(Number);
  
  for (let i = 0; i < Math.max(parts1.length, parts2.length); i++) {
    const p1 = parts1[i] || 0;
    const p2 = parts2[i] || 0;
    if (p1 > p2) return 1;
    if (p1 < p2) return -1;
  }
  return 0;
}

// ============== 启动 ==============

// DOM加载完成后初始化
document.addEventListener('DOMContentLoaded', init);
