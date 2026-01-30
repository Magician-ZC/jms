/**
 * JMS Token Manager - Content Script
 * 支持代理区(jms.jtexpress.com.cn)和网点(wd.jtexpress.com.cn)
 */

// ============== 配置 ==============
const CONFIG = {
  // 代理区配置
  AGENT: {
    type: 'agent',
    name: '代理区',
    LOGIN_PAGE: 'https://jms.jtexpress.com.cn/login',
    INDEX_PAGE: 'https://jms.jtexpress.com.cn/index',
    DOMAIN: 'jms.jtexpress.com.cn',
    API_DOMAIN: 'jmsgw.jtexpress.com.cn',
    TOKEN_COOKIE_NAME: 'authtoken',
  },
  // 网点配置
  NETWORK: {
    type: 'network',
    name: '网点',
    LOGIN_PAGE: 'https://wd.jtexpress.com.cn/login',
    INDEX_PAGE: 'https://wd.jtexpress.com.cn/indexSub',
    DOMAIN: 'wd.jtexpress.com.cn',
    API_DOMAIN: 'wdgw.jtexpress.com.cn',
    TOKEN_COOKIE_NAME: 'authtoken',
  }
};

// ============== 状态 ==============
let isMonitoring = false;
let currentConfig = null;
let tokenExtractor = null;

// ============== 工具函数 ==============

/**
 * 安全发送消息到background，处理扩展上下文失效的情况
 */
function safeSendMessage(message, callback) {
  try {
    // 先检查扩展上下文是否有效
    if (!chrome.runtime.id) {
      console.log('[Content] Extension context invalidated, cannot send message');
      return;
    }
    
    chrome.runtime.sendMessage(message, (response) => {
      if (chrome.runtime.lastError) {
        console.log('[Content] Message send failed:', chrome.runtime.lastError.message);
        return;
      }
      if (callback) callback(response);
    });
  } catch (error) {
    console.log('[Content] Failed to send message:', error.message);
  }
}

// ============== 初始化 ==============

/**
 * 检测当前页面类型并获取对应配置
 */
function detectPlatform() {
  const hostname = window.location.hostname;
  
  if (hostname.includes('jms.jtexpress.com.cn')) {
    return CONFIG.AGENT;
  } else if (hostname.includes('wd.jtexpress.com.cn')) {
    return CONFIG.NETWORK;
  }
  return null;
}

/**
 * 获取当前页面类型
 */
function getCurrentPageType() {
  const url = window.location.href;
  
  if (url.includes('/login')) {
    return 'login';
  } else if (url.includes('/index') || url.includes('/indexSub')) {
    return 'index';
  }
  return 'other';
}

function isLoginPage() {
  return getCurrentPageType() === 'login';
}

function isIndexPage() {
  return getCurrentPageType() === 'index';
}

// ============== Token提取 ==============

function initTokenExtractor() {
  if (typeof TokenExtractor !== 'undefined') {
    tokenExtractor = new TokenExtractor();
    tokenExtractor.onTokenExtracted((tokenInfo) => {
      if (isMonitoring) {
        handleTokenFromExtractor(tokenInfo);
      }
    });
    console.log('[Content] TokenExtractor initialized');
  }
}

function handleTokenFromExtractor(tokenInfo) {
  console.log('[Content] Token from extractor:', tokenInfo.source);
  
  const fullTokenInfo = {
    token: tokenInfo.token,
    userId: extractUserId(),
    account: extractAccount(),
    accountType: currentConfig ? currentConfig.type : 'agent',
    source: tokenInfo.source,
    captureTime: Date.now()
  };
  
  chrome.runtime.sendMessage({
    action: 'tokenCaptured',
    tokenInfo: fullTokenInfo
  });
}

function extractTokenFromCookie() {
  if (tokenExtractor) {
    return tokenExtractor.extractFromCookie();
  }
  
  const cookies = document.cookie.split(';');
  for (const cookie of cookies) {
    const [name, value] = cookie.trim().split('=');
    if (name === 'authtoken' && value) {
      console.log('[Content] Token found in cookie');
      return decodeURIComponent(value);
    }
  }
  return null;
}

function extractTokenFromStorage() {
  if (tokenExtractor) {
    return tokenExtractor.extractFromLocalStorage();
  }
  
  try {
    const possibleKeys = ['YL_TOKEN', 'token', 'authtoken', 'auth_token'];
    for (const key of possibleKeys) {
      const value = localStorage.getItem(key);
      if (value) {
        console.log('[Content] Token found in localStorage:', key);
        return value;
      }
    }
  } catch (error) {
    console.error('[Content] Failed to read localStorage:', error);
  }
  return null;
}

function extractToken() {
  if (tokenExtractor) {
    return tokenExtractor.extractFromAllSources();
  }
  
  let token = extractTokenFromCookie();
  if (token) return { token, source: 'cookie' };
  
  token = extractTokenFromStorage();
  if (token) return { token, source: 'localStorage' };
  
  return null;
}

function extractUserId() {
  try {
    const userElements = document.querySelectorAll('[class*="user"], [class*="account"]');
    for (const el of userElements) {
      const text = el.textContent.trim();
      if (text && text.length < 50) {
        return text;
      }
    }
  } catch (error) {}
  return 'user_' + Date.now();
}

function extractAccount() {
  try {
    const brUser = localStorage.getItem('br-user');
    if (brUser && brUser.trim()) {
      return brUser.trim();
    }
    
    const userDataStr = localStorage.getItem('userData');
    if (userDataStr) {
      try {
        const userData = JSON.parse(userDataStr);
        const account = userData.account || userData.username || userData.loginName;
        if (account) return account;
      } catch (e) {}
    }
  } catch (error) {}
  return null;
}

// ============== 登录监听 ==============

/**
 * 检查扩展上下文是否有效
 */
function isExtensionContextValid() {
  try {
    // 尝试访问chrome.runtime.id，如果上下文失效会抛出异常
    return !!chrome.runtime.id;
  } catch (e) {
    return false;
  }
}

function observeNavigation() {
  let currentUrl = window.location.href;
  
  const observer = new MutationObserver(() => {
    // 检查扩展上下文是否有效
    if (!isExtensionContextValid()) {
      observer.disconnect();
      console.log('[Content] Extension context invalidated, observer disconnected');
      return;
    }
    
    if (window.location.href !== currentUrl) {
      const oldUrl = currentUrl;
      currentUrl = window.location.href;
      handleUrlChange(oldUrl, currentUrl);
    }
  });
  
  observer.observe(document.body, { childList: true, subtree: true });
  
  window.addEventListener('popstate', () => {
    if (!isExtensionContextValid()) return;
    
    if (window.location.href !== currentUrl) {
      const oldUrl = currentUrl;
      currentUrl = window.location.href;
      handleUrlChange(oldUrl, currentUrl);
    }
  });
}

function handleUrlChange(oldUrl, newUrl) {
  console.log('[Content] URL changed:', oldUrl, '->', newUrl);
  
  const oldPageType = getPageTypeFromUrl(oldUrl);
  const newPageType = getPageTypeFromUrl(newUrl);
  
  safeSendMessage({
    action: 'pageChanged',
    pageType: newPageType,
    oldPageType: oldPageType,
    accountType: currentConfig ? currentConfig.type : 'agent'
  });
  
  if (oldPageType === 'login' && newPageType === 'index') {
    console.log('[Content] Login success detected!');
    handleLoginSuccess();
  }
}

function getPageTypeFromUrl(url) {
  if (url.includes('/login')) return 'login';
  if (url.includes('/index') || url.includes('/indexSub')) return 'index';
  return 'other';
}

function handleLoginSuccess() {
  if (!isMonitoring) return;
  setTimeout(() => captureAndSendToken(), 500);
}

function captureAndSendToken() {
  console.log('[Content] Attempting to capture token...');
  
  const tokenResult = extractToken();
  
  if (tokenResult) {
    const tokenInfo = {
      token: tokenResult.token,
      userId: extractUserId(),
      account: extractAccount(),
      accountType: currentConfig ? currentConfig.type : 'agent',
      source: tokenResult.source,
      captureTime: Date.now()
    };
    
    console.log('[Content] Token captured, type:', tokenInfo.accountType);
    
    safeSendMessage({
      action: 'tokenCaptured',
      tokenInfo: tokenInfo
    }, (response) => {
      if (response && response.success) {
        showNotification('Token已同步', 'success');
      } else if (response && response.error) {
        showNotification('Token同步失败: ' + response.error, 'error');
      }
    });
  } else {
    showNotification('未找到Token', 'warning');
  }
}

// ============== 网络请求拦截 ==============

function interceptLoginApi() {
  console.log('[Content] Setting up login API interceptor for', currentConfig?.name);
  
  const originalXHROpen = XMLHttpRequest.prototype.open;
  const originalXHRSend = XMLHttpRequest.prototype.send;
  
  XMLHttpRequest.prototype.open = function(method, url) {
    this._url = url;
    return originalXHROpen.apply(this, arguments);
  };
  
  XMLHttpRequest.prototype.send = function(body) {
    const xhr = this;
    const url = this._url || '';
    
    // 监听代理区登录API
    if (url.includes('jmsgw.jtexpress.com.cn') && url.includes('webOauth/login')) {
      xhr.addEventListener('load', function() {
        if (xhr.status === 200) {
          try {
            const data = JSON.parse(xhr.responseText);
            if (data.succ && data.data && data.data.token) {
              handleTokenFromLoginApi(data.data.token, 'agent');
            }
          } catch (e) {}
        }
      });
    }
    
    // 监听网点登录API
    if (url.includes('wdgw.jtexpress.com.cn') && url.includes('login')) {
      xhr.addEventListener('load', function() {
        if (xhr.status === 200) {
          try {
            const data = JSON.parse(xhr.responseText);
            if (data.succ && data.data && data.data.token) {
              handleTokenFromLoginApi(data.data.token, 'network');
            }
          } catch (e) {}
        }
      });
    }
    
    return originalXHRSend.apply(this, arguments);
  };
  
  // Fetch拦截
  const originalFetch = window.fetch;
  window.fetch = function(input, init) {
    const url = typeof input === 'string' ? input : input.url;
    const fetchPromise = originalFetch.apply(this, arguments);
    
    if ((url.includes('jmsgw.jtexpress.com.cn') && url.includes('webOauth/login')) ||
        (url.includes('wdgw.jtexpress.com.cn') && url.includes('login'))) {
      
      const accountType = url.includes('jmsgw') ? 'agent' : 'network';
      
      return fetchPromise.then(response => {
        const clonedResponse = response.clone();
        clonedResponse.text().then(text => {
          try {
            const data = JSON.parse(text);
            if (data.succ && data.data && data.data.token) {
              handleTokenFromLoginApi(data.data.token, accountType);
            }
          } catch (e) {}
        }).catch(() => {});
        return response;
      });
    }
    
    return fetchPromise;
  };
}

function handleTokenFromLoginApi(token, accountType) {
  if (!isMonitoring) return;
  
  const tokenInfo = {
    token: token,
    userId: extractUserId(),
    account: extractAccount(),
    accountType: accountType,
    source: 'login_response',
    captureTime: Date.now()
  };
  
  console.log('[Content] Token from login API, type:', accountType);
  
  safeSendMessage({
    action: 'tokenCaptured',
    tokenInfo: tokenInfo
  }, (response) => {
    if (response && response.success) {
      showNotification('Token已同步', 'success');
    }
  });
}

// ============== UI通知 ==============

function showNotification(message, type = 'info') {
  const notification = document.createElement('div');
  notification.textContent = message;
  
  const colors = {
    success: '#4CAF50',
    error: '#f44336',
    warning: '#ff9800',
    info: '#2196F3'
  };
  
  notification.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    padding: 12px 24px;
    background-color: ${colors[type] || colors.info};
    color: white;
    border-radius: 4px;
    font-size: 14px;
    z-index: 999999;
    box-shadow: 0 2px 8px rgba(0,0,0,0.2);
  `;
  
  document.body.appendChild(notification);
  setTimeout(() => notification.remove(), 3000);
}

// ============== 消息处理 ==============

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.action) {
    case 'startMonitoring':
      startMonitoring();
      sendResponse({ success: true });
      break;
      
    case 'stopMonitoring':
      stopMonitoring();
      sendResponse({ success: true });
      break;
      
    case 'tokenExpired':
      handleTokenExpiredNotification(message.reason);
      sendResponse({ success: true });
      break;
    
    case 'tokenDeleted':
      handleTokenDeletedNotification(message.reason);
      sendResponse({ success: true });
      break;
      
    case 'tokenSynced':
      showNotification('Token已同步', 'success');
      sendResponse({ success: true });
      break;
      
    case 'captureToken':
      captureAndSendToken();
      sendResponse({ success: true });
      break;
      
    case 'pageLoaded':
      // 页面加载完成时，如果开关开启则开始监听
      if (message.isEnabled) {
        startMonitoring();
        // 在首页时总是尝试捕获Token（无论是否已有Token）
        if (isIndexPage()) {
          setTimeout(captureAndSendToken, 500);
        }
      }
      sendResponse({ success: true });
      break;
      
    default:
      sendResponse({ error: 'Unknown action' });
  }
  return true;
});

function startMonitoring() {
  if (isMonitoring) return;
  isMonitoring = true;
  console.log('[Content] Monitoring started for', currentConfig?.name);
  
  // 在首页时总是尝试捕获Token（用于更新已有Token）
  if (isIndexPage()) {
    setTimeout(captureAndSendToken, 500);
  }
}

function stopMonitoring() {
  isMonitoring = false;
  console.log('[Content] Monitoring stopped');
}

function handleTokenExpiredNotification(reason) {
  showNotification('Token已失效: ' + (reason || '请重新登录'), 'warning');
  isMonitoring = true;
}

function handleTokenDeletedNotification(reason) {
  showNotification('Token已被删除: ' + (reason || '请重新登录'), 'warning');
  isMonitoring = true;
  
  // 如果在首页，立即尝试重新捕获Token
  if (isIndexPage()) {
    setTimeout(captureAndSendToken, 500);
  }
}

// ============== 初始化 ==============

function init() {
  currentConfig = detectPlatform();
  
  if (!currentConfig) {
    console.log('[Content] Unknown platform, skipping initialization');
    return;
  }
  
  console.log('[Content] Initializing for', currentConfig.name, 'on:', window.location.href);
  
  initTokenExtractor();
  interceptLoginApi();
  observeNavigation();
  
  safeSendMessage({ action: 'checkShouldMonitor' }, (response) => {
    if (response && response.shouldMonitor) {
      startMonitoring();
    }
  });
  
  safeSendMessage({
    action: 'pageChanged',
    pageType: getCurrentPageType(),
    accountType: currentConfig.type
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
