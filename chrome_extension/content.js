/**
 * JMS Token Manager - Content Script
 * 
 * 功能：
 * - 页面类型检测
 * - 登录成功监听
 * - Token提取逻辑（使用TokenExtractor模块）
 * - 页面跳转功能
 * - Token失效处理
 * 
 * Requirements: 1.3, 1.4, 2.1, 2.2, 2.3, 6.3, 6.4
 */

// ============== 配置 ==============
const CONFIG = {
  LOGIN_PAGE: 'https://jms.jtexpress.com.cn/login',
  INDEX_PAGE: 'https://jms.jtexpress.com.cn/index',
  TOKEN_COOKIE_NAME: 'authtoken',
  TOKEN_STORAGE_KEY: 'token',
  TOKEN_HEADER_NAME: 'authorization'
};

// ============== 状态 ==============
let isMonitoring = false;
let lastUrl = window.location.href;
let tokenExtractor = null;
let requestInterceptor = null;

// ============== 页面类型检测 ==============

/**
 * 获取当前页面类型
 * Requirements: 1.3, 1.4
 */
function getCurrentPageType() {
  const url = window.location.href;
  
  if (url.includes('/login')) {
    return 'login';
  } else if (url.includes('/index') || url === 'https://jms.jtexpress.com.cn/') {
    return 'index';
  }
  return 'other';
}

/**
 * 检查是否在登录页
 */
function isLoginPage() {
  return getCurrentPageType() === 'login';
}

/**
 * 检查是否在首页
 */
function isIndexPage() {
  return getCurrentPageType() === 'index';
}

// ============== Token提取 ==============

/**
 * 初始化Token提取器
 */
function initTokenExtractor() {
  // 使用TokenExtractor模块（如果可用）
  if (typeof TokenExtractor !== 'undefined') {
    tokenExtractor = new TokenExtractor();
    
    // 注册Token提取回调
    tokenExtractor.onTokenExtracted((tokenInfo) => {
      if (isMonitoring) {
        handleTokenFromExtractor(tokenInfo);
      }
    });
    
    // 初始化请求拦截器
    if (typeof RequestInterceptor !== 'undefined') {
      requestInterceptor = new RequestInterceptor(tokenExtractor);
    }
    
    console.log('[Content] TokenExtractor initialized');
  } else {
    console.log('[Content] TokenExtractor not available, using fallback');
  }
}

/**
 * 处理从TokenExtractor获取的Token
 */
function handleTokenFromExtractor(tokenInfo) {
  console.log('[Content] Token from extractor:', tokenInfo.source);
  
  const fullTokenInfo = {
    token: tokenInfo.token,
    userId: extractUserId(),
    source: tokenInfo.source,
    captureTime: Date.now()
  };
  
  chrome.runtime.sendMessage({
    action: 'tokenCaptured',
    tokenInfo: fullTokenInfo
  });
}

/**
 * 从Cookie中提取Token
 * Requirements: 2.2
 */
function extractTokenFromCookie() {
  // 优先使用TokenExtractor模块
  if (tokenExtractor) {
    return tokenExtractor.extractFromCookie();
  }
  
  // 回退到原始实现
  const cookies = document.cookie.split(';');
  for (const cookie of cookies) {
    const [name, value] = cookie.trim().split('=');
    if (name === CONFIG.TOKEN_COOKIE_NAME && value) {
      console.log('[Content] Token found in cookie');
      return decodeURIComponent(value);
    }
  }
  return null;
}

/**
 * 从localStorage中提取Token
 * Requirements: 2.2
 */
function extractTokenFromStorage() {
  // 优先使用TokenExtractor模块
  if (tokenExtractor) {
    return tokenExtractor.extractFromLocalStorage();
  }
  
  // 回退到原始实现 - YL_TOKEN 是 JMS 系统使用的 key，放在最前面
  try {
    const possibleKeys = ['YL_TOKEN', 'token', 'authtoken', 'auth_token', 'accessToken', 'access_token'];
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

/**
 * 从sessionStorage中提取Token
 */
function extractTokenFromSessionStorage() {
  // 优先使用TokenExtractor模块
  if (tokenExtractor) {
    return tokenExtractor.extractFromSessionStorage();
  }
  
  // 回退到原始实现 - YL_TOKEN 是 JMS 系统使用的 key
  try {
    const possibleKeys = ['YL_TOKEN', 'token', 'authtoken', 'auth_token', 'accessToken', 'access_token'];
    for (const key of possibleKeys) {
      const value = sessionStorage.getItem(key);
      if (value) {
        console.log('[Content] Token found in sessionStorage:', key);
        return value;
      }
    }
  } catch (error) {
    console.error('[Content] Failed to read sessionStorage:', error);
  }
  return null;
}

/**
 * 尝试从所有来源提取Token
 */
function extractToken() {
  // 优先使用TokenExtractor模块
  if (tokenExtractor) {
    return tokenExtractor.extractFromAllSources();
  }
  
  // 回退到原始实现
  // 优先从Cookie提取
  let token = extractTokenFromCookie();
  if (token) {
    return { token, source: 'cookie' };
  }
  
  // 尝试localStorage
  token = extractTokenFromStorage();
  if (token) {
    return { token, source: 'localStorage' };
  }
  
  // 尝试sessionStorage
  token = extractTokenFromSessionStorage();
  if (token) {
    return { token, source: 'sessionStorage' };
  }
  
  return null;
}

/**
 * 提取用户ID（从页面或Token中）
 */
function extractUserId() {
  // 尝试从页面元素获取用户信息
  try {
    // 常见的用户信息元素选择器
    const userElements = document.querySelectorAll('[class*="user"], [class*="account"], [id*="user"]');
    for (const el of userElements) {
      const text = el.textContent.trim();
      if (text && text.length < 50) {
        return text;
      }
    }
  } catch (error) {
    console.log('[Content] Failed to extract userId from page');
  }
  
  // 使用时间戳作为临时ID
  return 'user_' + Date.now();
}

/**
 * 提取登录账号
 * 从 localStorage 的 br-user 或 userData 中获取
 */
function extractAccount() {
  try {
    // 优先从 br-user 获取（JMS系统使用）
    const brUser = localStorage.getItem('br-user');
    if (brUser && brUser.trim()) {
      console.log('[Content] Account found in br-user:', brUser);
      return brUser.trim();
    }
    
    // 尝试从 userData 获取
    const userDataStr = localStorage.getItem('userData');
    if (userDataStr) {
      try {
        const userData = JSON.parse(userDataStr);
        // 可能的账号字段
        const account = userData.account || userData.username || userData.loginName || userData.name;
        if (account) {
          console.log('[Content] Account found in userData:', account);
          return account;
        }
      } catch (e) {
        console.log('[Content] Failed to parse userData');
      }
    }
    
    // 尝试从 cookie 获取 account
    const cookies = document.cookie.split(';');
    for (const cookie of cookies) {
      const [name, value] = cookie.trim().split('=');
      if (name === 'account' && value) {
        console.log('[Content] Account found in cookie:', value);
        return decodeURIComponent(value);
      }
    }
  } catch (error) {
    console.error('[Content] Failed to extract account:', error);
  }
  
  return null;
}


// ============== 登录监听 ==============

/**
 * 监听页面导航变化
 * Requirements: 2.1
 */
function observeNavigation() {
  // 使用MutationObserver监听URL变化
  let currentUrl = window.location.href;
  
  const observer = new MutationObserver(() => {
    if (window.location.href !== currentUrl) {
      const oldUrl = currentUrl;
      currentUrl = window.location.href;
      handleUrlChange(oldUrl, currentUrl);
    }
  });
  
  observer.observe(document.body, {
    childList: true,
    subtree: true
  });
  
  // 同时监听popstate事件
  window.addEventListener('popstate', () => {
    if (window.location.href !== currentUrl) {
      const oldUrl = currentUrl;
      currentUrl = window.location.href;
      handleUrlChange(oldUrl, currentUrl);
    }
  });
  
  console.log('[Content] Navigation observer started');
}

/**
 * 处理URL变化
 * Requirements: 2.1
 */
function handleUrlChange(oldUrl, newUrl) {
  console.log('[Content] URL changed:', oldUrl, '->', newUrl);
  
  const oldPageType = getPageTypeFromUrl(oldUrl);
  const newPageType = getPageTypeFromUrl(newUrl);
  
  // 通知Background页面变化
  chrome.runtime.sendMessage({
    action: 'pageChanged',
    pageType: newPageType,
    oldPageType: oldPageType
  });
  
  // 如果从登录页跳转到首页，说明登录成功
  if (oldPageType === 'login' && newPageType === 'index') {
    console.log('[Content] Login success detected!');
    handleLoginSuccess();
  }
}

/**
 * 从URL获取页面类型
 */
function getPageTypeFromUrl(url) {
  if (url.includes('/login')) return 'login';
  if (url.includes('/index') || url.endsWith('jms.jtexpress.com.cn/')) return 'index';
  return 'other';
}

/**
 * 处理登录成功
 * Requirements: 2.2, 2.3
 */
function handleLoginSuccess() {
  if (!isMonitoring) {
    console.log('[Content] Not monitoring, skip token capture');
    return;
  }
  
  // 延迟一点时间等待Token写入
  setTimeout(() => {
    captureAndSendToken();
  }, 500);
}

/**
 * 捕获并发送Token
 */
function captureAndSendToken() {
  console.log('[Content] Attempting to capture token...');
  
  // 调试：打印所有Cookie
  console.log('[Content] All cookies:', document.cookie);
  
  // 调试：打印localStorage
  console.log('[Content] localStorage keys:', Object.keys(localStorage));
  for (const key of Object.keys(localStorage)) {
    console.log(`[Content] localStorage[${key}]:`, localStorage.getItem(key)?.substring(0, 100));
  }
  
  // 调试：打印sessionStorage
  console.log('[Content] sessionStorage keys:', Object.keys(sessionStorage));
  for (const key of Object.keys(sessionStorage)) {
    console.log(`[Content] sessionStorage[${key}]:`, sessionStorage.getItem(key)?.substring(0, 100));
  }
  
  const tokenResult = extractToken();
  
  if (tokenResult) {
    const tokenInfo = {
      token: tokenResult.token,
      userId: extractUserId(),
      account: extractAccount(),  // 添加账号信息
      source: tokenResult.source,
      captureTime: Date.now()
    };
    
    console.log('[Content] Token captured, sending to background, account:', tokenInfo.account);
    
    // 发送到Background
    chrome.runtime.sendMessage({
      action: 'tokenCaptured',
      tokenInfo: tokenInfo
    }, (response) => {
      // 检查是否有运行时错误
      if (chrome.runtime.lastError) {
        console.error('[Content] Runtime error:', chrome.runtime.lastError.message);
        showNotification('Token同步失败: ' + chrome.runtime.lastError.message, 'error');
        return;
      }
      
      console.log('[Content] Response received:', JSON.stringify(response));
      
      // 检查响应
      if (response && response.success) {
        console.log('[Content] Token sent successfully');
        showNotification('Token已同步', 'success');
      } else if (response && response.error) {
        console.error('[Content] Failed to send token:', response.error);
        showNotification('Token同步失败: ' + response.error, 'error');
      } else {
        // 其他情况也认为成功（兼容旧版本）
        console.log('[Content] Token sent (legacy response)');
        showNotification('Token已同步', 'success');
      }
    });
  } else {
    console.log('[Content] No token found');
    showNotification('未找到Token', 'warning');
  }
}

// ============== 网络请求拦截 ==============

/**
 * 专门拦截JMS登录API响应
 * 这是获取Token的主要方式
 */
function interceptLoginApi() {
  console.log('[Content] Setting up login API interceptor');
  
  // 拦截XHR
  const originalXHROpen = XMLHttpRequest.prototype.open;
  const originalXHRSend = XMLHttpRequest.prototype.send;
  
  XMLHttpRequest.prototype.open = function(method, url) {
    this._url = url;
    return originalXHROpen.apply(this, arguments);
  };
  
  XMLHttpRequest.prototype.send = function(body) {
    const xhr = this;
    const url = this._url || '';
    
    // 监听JMS登录API
    if (url.includes('jmsgw.jtexpress.com.cn') && url.includes('webOauth/login')) {
      console.log('[Content] Intercepting login XHR:', url);
      
      xhr.addEventListener('load', function() {
        if (xhr.status === 200) {
          try {
            const data = JSON.parse(xhr.responseText);
            if (data.succ && data.data && data.data.token) {
              console.log('[Content] Token found in login response!');
              handleTokenFromLoginApi(data.data.token);
            }
          } catch (e) {
            console.log('[Content] Failed to parse login response:', e);
          }
        }
      });
    }
    
    return originalXHRSend.apply(this, arguments);
  };
  
  // 拦截Fetch
  const originalFetch = window.fetch;
  window.fetch = function(input, init) {
    const url = typeof input === 'string' ? input : input.url;
    
    const fetchPromise = originalFetch.apply(this, arguments);
    
    // 监听JMS登录API
    if (url.includes('jmsgw.jtexpress.com.cn') && url.includes('webOauth/login')) {
      console.log('[Content] Intercepting login fetch:', url);
      
      return fetchPromise.then(response => {
        const clonedResponse = response.clone();
        
        clonedResponse.text().then(text => {
          try {
            const data = JSON.parse(text);
            if (data.succ && data.data && data.data.token) {
              console.log('[Content] Token found in login response!');
              handleTokenFromLoginApi(data.data.token);
            }
          } catch (e) {
            console.log('[Content] Failed to parse login response:', e);
          }
        }).catch(() => {});
        
        return response;
      });
    }
    
    return fetchPromise;
  };
}

/**
 * 处理从登录API获取的Token
 */
function handleTokenFromLoginApi(token) {
  if (!isMonitoring) {
    console.log('[Content] Not monitoring, ignoring token');
    return;
  }
  
  const tokenInfo = {
    token: token,
    userId: extractUserId(),
    account: extractAccount(),  // 添加账号信息
    source: 'login_response',
    captureTime: Date.now()
  };
  
  console.log('[Content] Sending token to background, account:', tokenInfo.account);
  
  chrome.runtime.sendMessage({
    action: 'tokenCaptured',
    tokenInfo: tokenInfo
  }, (response) => {
    // 检查是否有运行时错误
    if (chrome.runtime.lastError) {
      console.error('[Content] Runtime error:', chrome.runtime.lastError.message);
      showNotification('Token同步失败: ' + chrome.runtime.lastError.message, 'error');
      return;
    }
    
    console.log('[Content] Response received:', JSON.stringify(response));
    
    // 检查响应
    if (response && response.success) {
      console.log('[Content] Token sent successfully');
      showNotification('Token已同步', 'success');
    } else if (response && response.error) {
      console.error('[Content] Failed to send token:', response.error);
      showNotification('Token同步失败: ' + response.error, 'error');
    } else {
      // 其他情况也认为成功（兼容旧版本）
      console.log('[Content] Token sent (legacy response)');
      showNotification('Token已同步', 'success');
    }
  });
}

/**
 * 拦截XHR请求获取Token
 */
function interceptXHR() {
  const originalOpen = XMLHttpRequest.prototype.open;
  const originalSetRequestHeader = XMLHttpRequest.prototype.setRequestHeader;
  
  XMLHttpRequest.prototype.open = function(method, url) {
    this._url = url;
    return originalOpen.apply(this, arguments);
  };
  
  XMLHttpRequest.prototype.setRequestHeader = function(name, value) {
    if (name.toLowerCase() === 'authorization' && value && isMonitoring) {
      console.log('[Content] Token found in XHR header');
      handleTokenFromHeader(value);
    }
    return originalSetRequestHeader.apply(this, arguments);
  };
}

/**
 * 拦截Fetch请求获取Token
 */
function interceptFetch() {
  const originalFetch = window.fetch;
  
  window.fetch = function(input, init) {
    if (init && init.headers && isMonitoring) {
      const headers = init.headers;
      let authHeader = null;
      
      if (headers instanceof Headers) {
        authHeader = headers.get('authorization');
      } else if (typeof headers === 'object') {
        authHeader = headers['authorization'] || headers['Authorization'];
      }
      
      if (authHeader) {
        console.log('[Content] Token found in fetch header');
        handleTokenFromHeader(authHeader);
      }
    }
    
    return originalFetch.apply(this, arguments);
  };
}

/**
 * 处理从请求头获取的Token
 */
function handleTokenFromHeader(authHeader) {
  // 移除Bearer前缀
  let token = authHeader;
  if (token.startsWith('Bearer ')) {
    token = token.substring(7);
  }
  
  const tokenInfo = {
    token: token,
    userId: extractUserId(),
    source: 'response',
    captureTime: Date.now()
  };
  
  chrome.runtime.sendMessage({
    action: 'tokenCaptured',
    tokenInfo: tokenInfo
  });
}


// ============== 页面跳转 ==============

/**
 * 跳转到登录页
 * Requirements: 1.3
 */
function navigateToLogin() {
  console.log('[Content] Navigating to login page');
  window.location.href = CONFIG.LOGIN_PAGE;
}

/**
 * 跳转到首页
 */
function navigateToIndex() {
  console.log('[Content] Navigating to index page');
  window.location.href = CONFIG.INDEX_PAGE;
}

// ============== UI通知 ==============

/**
 * 显示页面内通知
 */
function showNotification(message, type = 'info') {
  // 创建通知元素
  const notification = document.createElement('div');
  notification.className = 'jms-token-notification';
  notification.textContent = message;
  
  // 设置样式
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
    animation: slideIn 0.3s ease;
  `;
  
  // 添加动画样式
  if (!document.getElementById('jms-notification-style')) {
    const style = document.createElement('style');
    style.id = 'jms-notification-style';
    style.textContent = `
      @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
      }
    `;
    document.head.appendChild(style);
  }
  
  document.body.appendChild(notification);
  
  // 3秒后自动移除
  setTimeout(() => {
    notification.style.animation = 'slideIn 0.3s ease reverse';
    setTimeout(() => notification.remove(), 300);
  }, 3000);
}

// ============== 消息处理 ==============

/**
 * 监听来自Background的消息
 */
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log('[Content] Received message:', message.action);
  
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
      // Requirements: 6.3, 6.4 - 处理Token失效
      handleTokenExpiredNotification(message.reason, message.userId);
      sendResponse({ success: true });
      break;
      
    case 'tokenRecovered':
      handleTokenRecoveredNotification();
      sendResponse({ success: true });
      break;
      
    case 'tokenSynced':
      handleTokenSyncedNotification(message.tokenId);
      sendResponse({ success: true });
      break;
      
    case 'tokenSyncFailed':
      handleTokenSyncFailedNotification(message.error);
      sendResponse({ success: true });
      break;
      
    case 'pageLoaded':
      handlePageLoaded(message);
      sendResponse({ success: true });
      break;
      
    case 'captureToken':
      captureAndSendToken();
      sendResponse({ success: true });
      break;
      
    default:
      sendResponse({ error: 'Unknown action' });
  }
  
  return true;
});

/**
 * 开始监听
 */
function startMonitoring() {
  if (isMonitoring) return;
  
  isMonitoring = true;
  console.log('[Content] Monitoring started');
  
  // 启动请求拦截器（如果TokenExtractor可用）
  if (requestInterceptor) {
    requestInterceptor.start();
    console.log('[Content] Request interceptor started - watching for login API');
  }
  // 注意：interceptLoginApi() 已在 init() 中调用，不再重复调用
  
  // 如果当前在首页，尝试从存储中捕获Token（作为备用方案）
  if (isIndexPage()) {
    setTimeout(captureAndSendToken, 500);
  }
}

/**
 * 停止监听
 */
function stopMonitoring() {
  isMonitoring = false;
  console.log('[Content] Monitoring stopped');
  
  // 停止请求拦截器
  if (requestInterceptor) {
    requestInterceptor.stop();
  }
}

/**
 * 处理Token失效通知
 * Requirements: 6.3, 6.4
 */
function handleTokenExpiredNotification(reason, userId) {
  console.log('[Content] Token expired notification received:', reason);
  
  // 显示失效提示
  showNotification('Token已失效: ' + (reason || '请重新登录'), 'warning');
  
  // 标记为自动监听模式
  isMonitoring = true;
  
  // 注意：跳转由background.js控制，这里不需要再跳转
  // 只需要准备好监听登录成功事件
  console.log('[Content] Waiting for user to re-login...');
}

/**
 * 处理Token恢复通知
 */
function handleTokenRecoveredNotification() {
  console.log('[Content] Token recovered notification received');
  showNotification('Token已恢复', 'success');
}

/**
 * 处理Token同步成功通知
 */
function handleTokenSyncedNotification(tokenId) {
  console.log('[Content] Token synced, id:', tokenId);
  showNotification('Token已同步', 'success');
}

/**
 * 处理Token同步失败通知
 */
function handleTokenSyncFailedNotification(error) {
  console.log('[Content] Token sync failed:', error);
  showNotification('Token同步失败: ' + (error || '未知错误'), 'error');
}

/**
 * 处理页面加载完成
 */
function handlePageLoaded(message) {
  if (message.isEnabled) {
    startMonitoring();
    
    // 如果没有Token且在首页，尝试捕获
    if (!message.hasToken && isIndexPage()) {
      setTimeout(captureAndSendToken, 500);
    }
  }
}

// ============== 初始化 ==============

/**
 * 初始化Content Script
 */
function init() {
  console.log('[Content] Initializing on:', window.location.href);
  console.log('[Content] Page type:', getCurrentPageType());
  
  // 初始化Token提取器
  initTokenExtractor();
  
  // 设置登录API拦截 - 这是获取Token的主要方式
  // 注意：只在这里调用一次，startMonitoring不再重复调用
  interceptLoginApi();
  
  // 开始监听导航变化
  observeNavigation();
  
  // 检查是否应该开始监听
  chrome.runtime.sendMessage({ action: 'checkShouldMonitor' }, (response) => {
    if (response && response.shouldMonitor) {
      startMonitoring();
    }
  });
  
  // 通知Background当前页面类型
  chrome.runtime.sendMessage({
    action: 'pageChanged',
    pageType: getCurrentPageType()
  });
  
  console.log('[Content] Content script initialized, ready to capture login token');
}

// 页面加载完成后初始化
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
