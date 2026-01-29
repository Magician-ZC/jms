/**
 * JMS Token Manager - Token提取模块
 * 
 * 功能：
 * - 从HTTP响应中提取Token
 * - 从Cookie中提取Token
 * - 从localStorage中提取Token
 * - 从sessionStorage中提取Token
 * 
 * Requirements: 2.2
 */

// ============== 配置 ==============
const TOKEN_CONFIG = {
  // JMS登录API URL关键字
  LOGIN_API_KEYWORDS: ['webOauth/login', 'jmsgw.jtexpress.com.cn'],
  // Cookie中的Token名称
  COOKIE_NAMES: ['authtoken', 'token', 'auth_token', 'access_token'],
  // Storage中的Token键名 - YL_TOKEN 是 JMS 系统使用的 key
  STORAGE_KEYS: ['YL_TOKEN', 'token', 'authtoken', 'auth_token', 'accessToken', 'access_token', 'jms_token'],
  // 请求头中的Token名称
  HEADER_NAME: 'authorization',
  // Token最小长度（用于验证）
  MIN_TOKEN_LENGTH: 10,
  // Token最大长度
  MAX_TOKEN_LENGTH: 2048
};

/**
 * Token提取器类
 * 提供多种来源的Token提取功能
 */
class TokenExtractor {
  constructor() {
    this.lastExtractedToken = null;
    this.extractionCallbacks = [];
  }

  /**
   * 从Cookie中提取Token
   * @returns {string|null} Token值或null
   */
  extractFromCookie() {
    try {
      const cookies = document.cookie.split(';');
      
      for (const cookie of cookies) {
        const [name, ...valueParts] = cookie.trim().split('=');
        const value = valueParts.join('='); // 处理值中包含=的情况
        
        if (TOKEN_CONFIG.COOKIE_NAMES.includes(name.toLowerCase()) && value) {
          const decodedValue = this._decodeToken(value);
          if (this._isValidToken(decodedValue)) {
            console.log('[TokenExtractor] Token found in cookie:', name);
            return decodedValue;
          }
        }
      }
    } catch (error) {
      console.error('[TokenExtractor] Failed to extract from cookie:', error);
    }
    return null;
  }

  /**
   * 从localStorage中提取Token
   * @returns {string|null} Token值或null
   */
  extractFromLocalStorage() {
    try {
      for (const key of TOKEN_CONFIG.STORAGE_KEYS) {
        const value = localStorage.getItem(key);
        if (value && this._isValidToken(value)) {
          console.log('[TokenExtractor] Token found in localStorage:', key);
          return value;
        }
        
        // 尝试解析JSON格式的Token
        if (value) {
          const parsed = this._tryParseJson(value);
          if (parsed && typeof parsed === 'object') {
            // 可能是 {token: 'xxx'} 或 {accessToken: 'xxx'} 格式
            const tokenValue = parsed.token || parsed.accessToken || parsed.access_token;
            if (tokenValue && this._isValidToken(tokenValue)) {
              console.log('[TokenExtractor] Token found in localStorage (JSON):', key);
              return tokenValue;
            }
          }
        }
      }
    } catch (error) {
      console.error('[TokenExtractor] Failed to extract from localStorage:', error);
    }
    return null;
  }

  /**
   * 从sessionStorage中提取Token
   * @returns {string|null} Token值或null
   */
  extractFromSessionStorage() {
    try {
      for (const key of TOKEN_CONFIG.STORAGE_KEYS) {
        const value = sessionStorage.getItem(key);
        if (value && this._isValidToken(value)) {
          console.log('[TokenExtractor] Token found in sessionStorage:', key);
          return value;
        }
        
        // 尝试解析JSON格式
        if (value) {
          const parsed = this._tryParseJson(value);
          if (parsed && typeof parsed === 'object') {
            const tokenValue = parsed.token || parsed.accessToken || parsed.access_token;
            if (tokenValue && this._isValidToken(tokenValue)) {
              console.log('[TokenExtractor] Token found in sessionStorage (JSON):', key);
              return tokenValue;
            }
          }
        }
      }
    } catch (error) {
      console.error('[TokenExtractor] Failed to extract from sessionStorage:', error);
    }
    return null;
  }

  /**
   * 从HTTP响应头中提取Token
   * @param {string} authHeader Authorization头的值
   * @returns {string|null} Token值或null
   */
  extractFromHeader(authHeader) {
    if (!authHeader) return null;
    
    try {
      let token = authHeader;
      
      // 移除Bearer前缀
      if (token.toLowerCase().startsWith('bearer ')) {
        token = token.substring(7);
      }
      
      if (this._isValidToken(token)) {
        console.log('[TokenExtractor] Token extracted from header');
        return token;
      }
    } catch (error) {
      console.error('[TokenExtractor] Failed to extract from header:', error);
    }
    return null;
  }

  /**
   * 从HTTP响应体中提取Token
   * @param {string|object} responseBody 响应体
   * @returns {string|null} Token值或null
   */
  extractFromResponse(responseBody) {
    try {
      let data = responseBody;
      
      // 如果是字符串，尝试解析为JSON
      if (typeof data === 'string') {
        data = this._tryParseJson(data);
      }
      
      if (!data || typeof data !== 'object') return null;
      
      // 常见的Token字段名
      const tokenFields = ['token', 'accessToken', 'access_token', 'authToken', 'auth_token', 'data.token'];
      
      for (const field of tokenFields) {
        const value = this._getNestedValue(data, field);
        if (value && this._isValidToken(value)) {
          console.log('[TokenExtractor] Token found in response:', field);
          return value;
        }
      }
      
      // 递归搜索嵌套对象
      const foundToken = this._deepSearchToken(data);
      if (foundToken) {
        console.log('[TokenExtractor] Token found in nested response');
        return foundToken;
      }
    } catch (error) {
      console.error('[TokenExtractor] Failed to extract from response:', error);
    }
    return null;
  }

  /**
   * 尝试从所有来源提取Token
   * @returns {{token: string, source: string}|null} Token信息或null
   */
  extractFromAllSources() {
    // 按优先级尝试各个来源
    const sources = [
      { name: 'cookie', fn: () => this.extractFromCookie() },
      { name: 'localStorage', fn: () => this.extractFromLocalStorage() },
      { name: 'sessionStorage', fn: () => this.extractFromSessionStorage() }
    ];
    
    for (const source of sources) {
      const token = source.fn();
      if (token) {
        this.lastExtractedToken = { token, source: source.name };
        return this.lastExtractedToken;
      }
    }
    
    return null;
  }

  /**
   * 注册Token提取回调
   * @param {Function} callback 回调函数
   */
  onTokenExtracted(callback) {
    if (typeof callback === 'function') {
      this.extractionCallbacks.push(callback);
    }
  }

  /**
   * 触发Token提取回调
   * @param {object} tokenInfo Token信息
   */
  _notifyCallbacks(tokenInfo) {
    for (const callback of this.extractionCallbacks) {
      try {
        callback(tokenInfo);
      } catch (error) {
        console.error('[TokenExtractor] Callback error:', error);
      }
    }
  }

  /**
   * 验证Token是否有效
   * @param {string} token Token值
   * @returns {boolean} 是否有效
   */
  _isValidToken(token) {
    if (!token || typeof token !== 'string') return false;
    
    const trimmed = token.trim();
    
    // 检查长度
    if (trimmed.length < TOKEN_CONFIG.MIN_TOKEN_LENGTH) return false;
    if (trimmed.length > TOKEN_CONFIG.MAX_TOKEN_LENGTH) return false;
    
    // 检查是否包含非法字符（Token通常是字母数字和一些特殊字符）
    // 允许 JWT 格式: xxx.xxx.xxx
    if (!/^[\w\-_.=+/]+$/.test(trimmed)) return false;
    
    return true;
  }

  /**
   * 解码Token值
   * @param {string} value 编码的值
   * @returns {string} 解码后的值
   */
  _decodeToken(value) {
    try {
      return decodeURIComponent(value);
    } catch {
      return value;
    }
  }

  /**
   * 尝试解析JSON
   * @param {string} str JSON字符串
   * @returns {object|null} 解析结果或null
   */
  _tryParseJson(str) {
    try {
      return JSON.parse(str);
    } catch {
      return null;
    }
  }

  /**
   * 获取嵌套对象的值
   * @param {object} obj 对象
   * @param {string} path 路径，如 'data.token'
   * @returns {any} 值
   */
  _getNestedValue(obj, path) {
    const keys = path.split('.');
    let current = obj;
    
    for (const key of keys) {
      if (current === null || current === undefined) return undefined;
      current = current[key];
    }
    
    return current;
  }

  /**
   * 深度搜索Token
   * @param {object} obj 对象
   * @param {number} depth 当前深度
   * @returns {string|null} Token值或null
   */
  _deepSearchToken(obj, depth = 0) {
    // 限制搜索深度
    if (depth > 5) return null;
    if (!obj || typeof obj !== 'object') return null;
    
    const tokenKeywords = ['token', 'accesstoken', 'authtoken'];
    
    for (const [key, value] of Object.entries(obj)) {
      // 检查键名是否包含token关键字
      if (tokenKeywords.some(kw => key.toLowerCase().includes(kw))) {
        if (typeof value === 'string' && this._isValidToken(value)) {
          return value;
        }
      }
      
      // 递归搜索嵌套对象
      if (typeof value === 'object' && value !== null) {
        const found = this._deepSearchToken(value, depth + 1);
        if (found) return found;
      }
    }
    
    return null;
  }
}

/**
 * 网络请求拦截器
 * 用于从XHR和Fetch请求中提取Token
 * 特别针对JMS登录API: jmsgw.jtexpress.com.cn/webOauth/login
 */
class RequestInterceptor {
  constructor(tokenExtractor) {
    this.extractor = tokenExtractor;
    this.isActive = false;
    this.originalXHROpen = null;
    this.originalXHRSend = null;
    this.originalFetch = null;
  }

  /**
   * 启动拦截
   */
  start() {
    if (this.isActive) return;
    
    this._interceptXHR();
    this._interceptFetch();
    this.isActive = true;
    console.log('[RequestInterceptor] Started - watching for JMS login API');
  }

  /**
   * 停止拦截
   */
  stop() {
    if (!this.isActive) return;
    
    this._restoreXHR();
    this._restoreFetch();
    this.isActive = false;
    console.log('[RequestInterceptor] Stopped');
  }

  /**
   * 检查URL是否是JMS登录API
   */
  _isLoginApi(url) {
    if (!url) return false;
    return url.includes('jmsgw.jtexpress.com.cn') && url.includes('webOauth/login');
  }

  /**
   * 从JMS登录响应中提取Token
   * 响应格式: { succ: true, data: { token: "xxx" } }
   */
  _extractTokenFromLoginResponse(responseText) {
    try {
      const data = JSON.parse(responseText);
      if (data.succ && data.data && data.data.token) {
        console.log('[RequestInterceptor] Found token in login response!');
        return data.data.token;
      }
    } catch (e) {
      console.log('[RequestInterceptor] Failed to parse response:', e);
    }
    return null;
  }

  /**
   * 拦截XHR请求
   */
  _interceptXHR() {
    const self = this;
    this.originalXHROpen = XMLHttpRequest.prototype.open;
    this.originalXHRSend = XMLHttpRequest.prototype.send;
    
    XMLHttpRequest.prototype.open = function(method, url) {
      this._requestUrl = url;
      this._requestMethod = method;
      return self.originalXHROpen.apply(this, arguments);
    };
    
    XMLHttpRequest.prototype.send = function(body) {
      const xhr = this;
      const url = this._requestUrl;
      
      // 监听登录API的响应
      if (self._isLoginApi(url)) {
        console.log('[RequestInterceptor] Intercepting XHR login request:', url);
        
        xhr.addEventListener('load', function() {
          if (xhr.status === 200) {
            const token = self._extractTokenFromLoginResponse(xhr.responseText);
            if (token) {
              self.extractor._notifyCallbacks({
                token,
                source: 'login_response',
                url
              });
            }
          }
        });
      }
      
      return self.originalXHRSend.apply(this, arguments);
    };
  }

  /**
   * 恢复XHR
   */
  _restoreXHR() {
    if (this.originalXHROpen) {
      XMLHttpRequest.prototype.open = this.originalXHROpen;
    }
    if (this.originalXHRSend) {
      XMLHttpRequest.prototype.send = this.originalXHRSend;
    }
  }

  /**
   * 拦截Fetch请求
   */
  _interceptFetch() {
    const self = this;
    this.originalFetch = window.fetch;
    
    window.fetch = function(input, init) {
      const url = typeof input === 'string' ? input : input.url;
      
      // 调用原始fetch
      const fetchPromise = self.originalFetch.apply(this, arguments);
      
      // 监听登录API的响应
      if (self._isLoginApi(url)) {
        console.log('[RequestInterceptor] Intercepting fetch login request:', url);
        
        return fetchPromise.then(response => {
          // 克隆响应以便读取body
          const clonedResponse = response.clone();
          
          clonedResponse.text().then(text => {
            const token = self._extractTokenFromLoginResponse(text);
            if (token) {
              self.extractor._notifyCallbacks({
                token,
                source: 'login_response',
                url
              });
            }
          }).catch(e => {
            console.log('[RequestInterceptor] Failed to read response:', e);
          });
          
          return response;
        });
      }
      
      return fetchPromise;
    };
  }

  /**
   * 恢复Fetch
   */
  _restoreFetch() {
    if (this.originalFetch) {
      window.fetch = this.originalFetch;
    }
  }
}

// 导出模块（用于ES模块环境）
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { TokenExtractor, RequestInterceptor, TOKEN_CONFIG };
}

// 全局导出（用于浏览器环境）
if (typeof window !== 'undefined') {
  window.TokenExtractor = TokenExtractor;
  window.RequestInterceptor = RequestInterceptor;
  window.TOKEN_CONFIG = TOKEN_CONFIG;
}
