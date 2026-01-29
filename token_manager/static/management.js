/**
 * Token管理中心 - 前端JavaScript
 * 
 * 功能：
 * - Token列表加载和渲染
 * - 删除功能
 * - 刷新功能
 * - WebSocket实时更新
 * - 简单密码认证
 * 
 * Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 9.2
 */

// ============== 配置 ==============
const CONFIG = {
    API_BASE_URL: `${window.location.protocol}//${window.location.hostname}:${window.location.port || 8080}`,
    WS_URL: `ws://${window.location.hostname}:${window.location.port || 8080}/ws`,
    RECONNECT_INTERVAL: 5000,
    MAX_RECONNECT_ATTEMPTS: 3,
    TOAST_DURATION: 3000,
    AUTH_KEY: 'token_manager_auth'
};

// ============== 状态管理 ==============
const state = {
    isAuthenticated: false,
    tokens: [],
    connections: [],
    wsConnected: false,
    ws: null,
    reconnectAttempts: 0,
    deleteTargetId: null,
    showExpired: true
};

// ============== DOM元素引用 ==============
const elements = {
    authOverlay: null,
    authForm: null,
    passwordInput: null,
    authError: null,
    mainContainer: null,
    connectionStatus: null,
    lastRefresh: null,
    refreshBtn: null,
    logoutBtn: null,
    totalCount: null,
    activeCount: null,
    expiredCount: null,
    connectionCount: null,
    showExpiredCheckbox: null,
    tokenList: null,
    emptyState: null,
    deleteDialog: null,
    deleteUserId: null,
    cancelDelete: null,
    confirmDelete: null,
    toastContainer: null
};

// ============== 初始化 ==============
document.addEventListener('DOMContentLoaded', () => {
    initElements();
    initEventListeners();
    checkAuth();
});

function initElements() {
    elements.authOverlay = document.getElementById('auth-overlay');
    elements.authForm = document.getElementById('auth-form');
    elements.passwordInput = document.getElementById('password-input');
    elements.authError = document.getElementById('auth-error');
    elements.mainContainer = document.getElementById('main-container');
    elements.connectionStatus = document.getElementById('connection-status');
    elements.lastRefresh = document.getElementById('last-refresh');
    elements.refreshBtn = document.getElementById('refresh-btn');
    elements.logoutBtn = document.getElementById('logout-btn');
    elements.totalCount = document.getElementById('total-count');
    elements.activeCount = document.getElementById('active-count');
    elements.expiredCount = document.getElementById('expired-count');
    elements.connectionCount = document.getElementById('connection-count');
    elements.showExpiredCheckbox = document.getElementById('show-expired');
    elements.tokenList = document.getElementById('token-list');
    elements.emptyState = document.getElementById('empty-state');
    elements.deleteDialog = document.getElementById('delete-dialog');
    elements.deleteUserId = document.getElementById('delete-user-id');
    elements.cancelDelete = document.getElementById('cancel-delete');
    elements.confirmDelete = document.getElementById('confirm-delete');
    elements.toastContainer = document.getElementById('toast-container');
}

function initEventListeners() {
    // 认证表单
    elements.authForm.addEventListener('submit', handleAuth);
    
    // 刷新按钮
    elements.refreshBtn.addEventListener('click', () => {
        loadTokens();
        loadConnections();
    });
    
    // 退出按钮
    elements.logoutBtn.addEventListener('click', handleLogout);
    
    // 显示过期Token复选框
    elements.showExpiredCheckbox.addEventListener('change', (e) => {
        state.showExpired = e.target.checked;
        renderTokenList();
    });
    
    // 删除对话框
    elements.cancelDelete.addEventListener('click', hideDeleteDialog);
    elements.confirmDelete.addEventListener('click', confirmDeleteToken);
}

// ============== 认证相关 ==============
function checkAuth() {
    const authToken = sessionStorage.getItem(CONFIG.AUTH_KEY);
    if (authToken) {
        state.isAuthenticated = true;
        showMainContent();
    }
}

async function handleAuth(e) {
    e.preventDefault();
    const password = elements.passwordInput.value;
    
    try {
        const response = await fetch(`${CONFIG.API_BASE_URL}/api/auth/verify`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password })
        });
        
        if (response.ok) {
            const data = await response.json();
            if (data.success) {
                sessionStorage.setItem(CONFIG.AUTH_KEY, 'authenticated');
                state.isAuthenticated = true;
                showMainContent();
                return;
            }
        }
        
        // 认证失败
        elements.authError.style.display = 'block';
        elements.passwordInput.value = '';
        elements.passwordInput.focus();
    } catch (error) {
        console.error('认证请求失败:', error);
        elements.authError.textContent = '网络错误，请重试';
        elements.authError.style.display = 'block';
    }
}

function handleLogout() {
    sessionStorage.removeItem(CONFIG.AUTH_KEY);
    state.isAuthenticated = false;
    
    // 断开WebSocket
    if (state.ws) {
        state.ws.close();
        state.ws = null;
    }
    
    // 显示认证界面
    elements.mainContainer.style.display = 'none';
    elements.authOverlay.style.display = 'flex';
    elements.passwordInput.value = '';
    elements.authError.style.display = 'none';
}

function showMainContent() {
    elements.authOverlay.style.display = 'none';
    elements.mainContainer.style.display = 'flex';
    
    // 加载数据
    loadTokens();
    loadConnections();
    
    // 连接WebSocket
    connectWebSocket();
}

// ============== API调用 ==============
async function loadTokens() {
    try {
        const response = await fetch(`${CONFIG.API_BASE_URL}/api/tokens?include_expired=true`);
        if (!response.ok) throw new Error('获取Token列表失败');
        
        const data = await response.json();
        state.tokens = data.tokens || [];
        
        updateStats();
        renderTokenList();
        updateLastRefresh();
    } catch (error) {
        console.error('加载Token失败:', error);
        showToast('加载Token列表失败', 'error');
    }
}

async function loadConnections() {
    try {
        const response = await fetch(`${CONFIG.API_BASE_URL}/api/connections`);
        if (!response.ok) throw new Error('获取连接列表失败');
        
        const data = await response.json();
        state.connections = data.connections || [];
        elements.connectionCount.textContent = data.total || 0;
    } catch (error) {
        console.error('加载连接失败:', error);
    }
}

async function deleteToken(tokenId) {
    try {
        const response = await fetch(`${CONFIG.API_BASE_URL}/api/tokens/${tokenId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) throw new Error('删除Token失败');
        
        // 从本地状态移除
        state.tokens = state.tokens.filter(t => t.id !== tokenId);
        updateStats();
        renderTokenList();
        showToast('Token已删除', 'success');
    } catch (error) {
        console.error('删除Token失败:', error);
        showToast('删除Token失败', 'error');
    }
}


// ============== 渲染函数 ==============
function updateStats() {
    const total = state.tokens.length;
    const active = state.tokens.filter(t => t.status === 'active').length;
    const expired = state.tokens.filter(t => t.status === 'expired' || t.status === 'invalid').length;
    
    elements.totalCount.textContent = total;
    elements.activeCount.textContent = active;
    elements.expiredCount.textContent = expired;
}

function renderTokenList() {
    // 过滤Token
    let tokensToShow = state.tokens;
    if (!state.showExpired) {
        tokensToShow = tokensToShow.filter(t => t.status === 'active');
    }
    
    // 清空列表
    elements.tokenList.innerHTML = '';
    
    // 显示空状态或列表
    if (tokensToShow.length === 0) {
        elements.emptyState.style.display = 'flex';
        elements.tokenList.style.display = 'none';
        return;
    }
    
    elements.emptyState.style.display = 'none';
    elements.tokenList.style.display = 'flex';
    
    // 渲染Token卡片
    tokensToShow.forEach(token => {
        const card = createTokenCard(token);
        elements.tokenList.appendChild(card);
    });
}

function createTokenCard(token) {
    const card = document.createElement('div');
    card.className = `token-card ${token.status !== 'active' ? 'expired' : ''}`;
    card.dataset.tokenId = token.id;
    
    // 账号显示 - 优先显示account
    const displayName = token.account || token.user_id || 'U';
    
    // 获取用户名首字母
    const initial = displayName.charAt(0).toUpperCase();
    
    // 状态显示
    const statusText = {
        'active': '✓ 活跃',
        'expired': '✗ 过期',
        'invalid': '⚠ 无效'
    }[token.status] || token.status;
    
    // 格式化时间
    const createdAt = formatTime(token.created_at);
    const updatedAt = formatTime(token.updated_at);
    const lastActiveAt = token.last_active_at ? formatTime(token.last_active_at) : null;
    
    card.innerHTML = `
        <div class="token-card-header">
            <div class="token-user-info">
                <div class="user-avatar">${initial}</div>
                <div class="user-details">
                    <h3>${escapeHtml(displayName)}</h3>
                    <span class="token-id">ID: ${token.id}</span>
                </div>
            </div>
            <span class="token-status ${token.status}">${statusText}</span>
        </div>
        <div class="token-card-body">
            <div class="token-value">${escapeHtml(token.token_masked)}</div>
        </div>
        <div class="token-card-footer">
            <div class="token-meta">
                <span class="meta-item"><strong>创建:</strong> ${createdAt}</span>
                <span class="meta-item"><strong>更新:</strong> ${updatedAt}</span>
                <span class="meta-item"><strong>活跃:</strong> ${lastActiveAt || '--'}</span>
            </div>
            <div class="token-actions">
                ${token.status === 'active' ? `
                <button class="btn btn-primary btn-sm" onclick="downloadFalseSignReport(${token.id}, '${escapeHtml(token.account || token.user_id)}')" title="下载虚假签收报表">
                    📊 虚假签收报表
                </button>
                ` : ''}
                <button class="btn btn-danger btn-sm" onclick="showDeleteDialog(${token.id}, '${escapeHtml(token.user_id)}')">
                    🗑️ 删除
                </button>
            </div>
        </div>
    `;
    
    return card;
}

function updateLastRefresh() {
    const now = new Date();
    elements.lastRefresh.textContent = `最后刷新: ${formatTime(now.toISOString())}`;
}

// ============== 删除对话框 ==============
function showDeleteDialog(tokenId, userId) {
    state.deleteTargetId = tokenId;
    elements.deleteUserId.textContent = userId;
    elements.deleteDialog.style.display = 'flex';
}

function hideDeleteDialog() {
    state.deleteTargetId = null;
    elements.deleteDialog.style.display = 'none';
}

function confirmDeleteToken() {
    if (state.deleteTargetId) {
        deleteToken(state.deleteTargetId);
        hideDeleteDialog();
    }
}

// ============== WebSocket连接 ==============
function connectWebSocket() {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        return;
    }
    
    try {
        state.ws = new WebSocket(CONFIG.WS_URL);
        
        state.ws.onopen = () => {
            console.log('WebSocket连接成功');
            state.wsConnected = true;
            state.reconnectAttempts = 0;
            updateConnectionStatus(true);
            
            // 发送注册消息（作为管理界面客户端）
            sendWsMessage({
                type: 'register',
                payload: {
                    extensionId: 'management-ui-' + Date.now(),
                    version: '1.0.0'
                },
                timestamp: Date.now()
            });
        };
        
        state.ws.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);
                handleWsMessage(message);
            } catch (error) {
                console.error('解析WebSocket消息失败:', error);
            }
        };
        
        state.ws.onclose = () => {
            console.log('WebSocket连接关闭');
            state.wsConnected = false;
            updateConnectionStatus(false);
            
            // 尝试重连
            if (state.isAuthenticated && state.reconnectAttempts < CONFIG.MAX_RECONNECT_ATTEMPTS) {
                state.reconnectAttempts++;
                console.log(`尝试重连 (${state.reconnectAttempts}/${CONFIG.MAX_RECONNECT_ATTEMPTS})...`);
                setTimeout(connectWebSocket, CONFIG.RECONNECT_INTERVAL);
            }
        };
        
        state.ws.onerror = (error) => {
            console.error('WebSocket错误:', error);
        };
    } catch (error) {
        console.error('创建WebSocket连接失败:', error);
        updateConnectionStatus(false);
    }
}

function sendWsMessage(message) {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify(message));
    }
}

function handleWsMessage(message) {
    console.log('收到WebSocket消息:', message.type);
    
    switch (message.type) {
        case 'register_ack':
            console.log('注册确认:', message.payload);
            break;
            
        case 'token_update':
            // Token更新通知，刷新列表
            loadTokens();
            showToast('Token列表已更新', 'info');
            break;
            
        case 'token_expired':
            // Token过期通知
            const userId = message.payload?.userId;
            if (userId) {
                showToast(`用户 ${userId} 的Token已过期`, 'error');
                loadTokens();
            }
            break;
            
        case 'connection_update':
            // 连接状态更新
            loadConnections();
            break;
            
        default:
            console.log('未处理的消息类型:', message.type);
    }
}

function updateConnectionStatus(connected) {
    if (connected) {
        elements.connectionStatus.className = 'status-indicator connected';
        elements.connectionStatus.querySelector('.status-text').textContent = '已连接';
    } else {
        elements.connectionStatus.className = 'status-indicator disconnected';
        elements.connectionStatus.querySelector('.status-text').textContent = '未连接';
    }
}

// ============== 工具函数 ==============
function formatTime(isoString) {
    if (!isoString) return '--';
    
    try {
        // 服务端存储的已经是中国时间，直接解析
        const date = new Date(isoString);
        const now = new Date();
        const diff = now - date;
        
        // 小于1分钟
        if (diff < 60000) {
            return '刚刚';
        }
        // 小于1小时
        if (diff < 3600000) {
            return `${Math.floor(diff / 60000)}分钟前`;
        }
        // 小于24小时
        if (diff < 86400000) {
            return `${Math.floor(diff / 3600000)}小时前`;
        }
        // 其他情况显示完整时间
        return date.toLocaleString('zh-CN', {
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
    } catch (error) {
        return isoString;
    }
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    const icon = {
        'success': '✓',
        'error': '✗',
        'info': 'ℹ'
    }[type] || 'ℹ';
    
    toast.innerHTML = `<span>${icon}</span><span>${escapeHtml(message)}</span>`;
    elements.toastContainer.appendChild(toast);
    
    // 自动移除
    setTimeout(() => {
        toast.style.animation = 'slideIn 0.3s ease reverse';
        setTimeout(() => toast.remove(), 300);
    }, CONFIG.TOAST_DURATION);
}

// 暴露全局函数供HTML调用
window.showDeleteDialog = showDeleteDialog;

/**
 * 下载虚假签收报表
 * @param {number} tokenId Token ID
 * @param {string} userName 用户名（用于显示）
 */
async function downloadFalseSignReport(tokenId, userName) {
    showToast(`正在为 ${userName} 下载虚假签收报表...`, 'info');
    
    try {
        const response = await fetch(`${CONFIG.API_BASE_URL}/api/false-sign-report/${tokenId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        
        // 检查Content-Type判断是JSON还是文件
        const contentType = response.headers.get('Content-Type') || '';
        
        if (contentType.includes('application/json')) {
            // JSON响应（可能是无数据或错误）
            const data = await response.json();
            if (data.success === false) {
                showToast(data.message || '无数据', 'info');
                return;
            }
            if (!response.ok) {
                throw new Error(data.detail || '下载失败');
            }
        }
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || '下载失败');
        }
        
        // 获取文件名
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = '虚假签收报表.xlsx';
        if (contentDisposition) {
            const match = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
            if (match && match[1]) {
                filename = decodeURIComponent(match[1].replace(/['"]/g, ''));
            }
        }
        
        // 下载文件
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        a.remove();
        
        showToast('报表下载成功', 'success');
    } catch (error) {
        console.error('下载虚假签收报表失败:', error);
        showToast(`下载失败: ${error.message}`, 'error');
    }
}

window.downloadFalseSignReport = downloadFalseSignReport;
