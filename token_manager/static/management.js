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
    AUTH_KEY: 'token_manager_auth',
    HEARTBEAT_INTERVAL: 25000  // 心跳间隔25秒，小于服务端的30秒检测间隔
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
    showExpired: true,
    filterType: 'all',  // 账号类型筛选: all, agent, network
    heartbeatTimer: null,
    extensionId: null
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
    elements.filterAll = document.getElementById('filter-all');
    elements.filterAgent = document.getElementById('filter-agent');
    elements.filterNetwork = document.getElementById('filter-network');
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
    
    // 账号类型筛选按钮
    elements.filterAll.addEventListener('click', () => handleFilterChange('all'));
    elements.filterAgent.addEventListener('click', () => handleFilterChange('agent'));
    elements.filterNetwork.addEventListener('click', () => handleFilterChange('network'));
    
    // 删除对话框
    elements.cancelDelete.addEventListener('click', hideDeleteDialog);
    elements.confirmDelete.addEventListener('click', confirmDeleteToken);
}

/**
 * 处理账号类型筛选切换
 */
function handleFilterChange(type) {
    state.filterType = type;
    
    // 更新按钮状态
    elements.filterAll.classList.toggle('active', type === 'all');
    elements.filterAgent.classList.toggle('active', type === 'agent');
    elements.filterNetwork.classList.toggle('active', type === 'network');
    
    renderTokenList();
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
    
    // 按账号类型筛选
    if (state.filterType !== 'all') {
        tokensToShow = tokensToShow.filter(t => t.account_type === state.filterType);
    }
    
    // 按过期状态筛选
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
    
    // 账号类型显示
    const accountTypeText = {
        'agent': '代理区',
        'network': '网点'
    }[token.account_type] || '代理区';
    
    const accountTypeClass = token.account_type === 'network' ? 'type-network' : 'type-agent';
    
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
                    <span class="account-type ${accountTypeClass}">${accountTypeText}</span>
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
                ${token.status === 'active' && token.account_type === 'agent' ? `
                <button class="btn btn-success btn-sm" onclick="showWaybillDownloadDialog(${token.id}, '${escapeHtml(token.account || token.user_id)}')" title="寄件运单下载">
                    📦 寄件运单下载
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
    
    // 清理旧的心跳定时器
    if (state.heartbeatTimer) {
        clearInterval(state.heartbeatTimer);
        state.heartbeatTimer = null;
    }
    
    try {
        state.ws = new WebSocket(CONFIG.WS_URL);
        
        state.ws.onopen = () => {
            console.log('WebSocket连接成功');
            state.wsConnected = true;
            state.reconnectAttempts = 0;
            updateConnectionStatus(true);
            
            // 生成唯一的extensionId
            state.extensionId = 'management-ui-' + Date.now();
            
            // 发送注册消息（作为管理界面客户端）
            sendWsMessage({
                type: 'register',
                payload: {
                    extensionId: state.extensionId,
                    version: '1.0.0'
                },
                timestamp: Date.now()
            });
            
            // 启动心跳定时器
            startHeartbeat();
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
            
            // 停止心跳
            stopHeartbeat();
            
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

/**
 * 启动心跳定时器
 */
function startHeartbeat() {
    if (state.heartbeatTimer) {
        clearInterval(state.heartbeatTimer);
    }
    
    state.heartbeatTimer = setInterval(() => {
        if (state.ws && state.ws.readyState === WebSocket.OPEN) {
            sendWsMessage({
                type: 'heartbeat',
                payload: {
                    extensionId: state.extensionId
                },
                timestamp: Date.now()
            });
            console.log('发送心跳');
        }
    }, CONFIG.HEARTBEAT_INTERVAL);
    
    console.log(`心跳定时器已启动，间隔=${CONFIG.HEARTBEAT_INTERVAL}ms`);
}

/**
 * 停止心跳定时器
 */
function stopHeartbeat() {
    if (state.heartbeatTimer) {
        clearInterval(state.heartbeatTimer);
        state.heartbeatTimer = null;
        console.log('心跳定时器已停止');
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

// ============== 寄件运单下载功能 ==============

// 任务中心状态
const taskCenterState = {
    tasks: [],
    isVisible: false,
    refreshTimer: null
};

/**
 * 显示寄件运单下载对话框
 */
function showWaybillDownloadDialog(tokenId, userName) {
    // 设置默认日期为昨天
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    const dateStr = yesterday.toISOString().split('T')[0];
    
    document.getElementById('waybill-token-id').value = tokenId;
    document.getElementById('waybill-start-date').value = dateStr;
    document.getElementById('waybill-end-date').value = dateStr;
    document.getElementById('waybill-user-name').textContent = userName;
    document.getElementById('waybill-dialog').style.display = 'flex';
}

/**
 * 隐藏寄件运单下载对话框
 */
function hideWaybillDownloadDialog() {
    document.getElementById('waybill-dialog').style.display = 'none';
}

/**
 * 提交寄件运单下载任务
 */
async function submitWaybillDownloadTask() {
    const tokenId = document.getElementById('waybill-token-id').value;
    const startDate = document.getElementById('waybill-start-date').value;
    const endDate = document.getElementById('waybill-end-date').value;
    
    if (!startDate || !endDate) {
        showToast('请选择日期范围', 'error');
        return;
    }
    
    if (new Date(startDate) > new Date(endDate)) {
        showToast('开始日期不能大于结束日期', 'error');
        return;
    }
    
    try {
        const response = await fetch(`${CONFIG.API_BASE_URL}/api/waybill-download/${tokenId}/submit`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                start_date: startDate,
                end_date: endDate
            })
        });
        
        const data = await response.json();
        
        if (!response.ok || !data.success) {
            throw new Error(data.detail || data.message || '提交任务失败');
        }
        
        showToast(`已创建${data.total_tasks}个下载子任务，请在任务中心查看进度`, 'success');
        hideWaybillDownloadDialog();
        
        // 显示任务中心
        showTaskCenter();
        refreshTaskList();
        
    } catch (error) {
        console.error('提交寄件运单下载任务失败:', error);
        showToast(`提交失败: ${error.message}`, 'error');
    }
}

/**
 * 显示/隐藏任务中心
 */
function toggleTaskCenter() {
    if (taskCenterState.isVisible) {
        hideTaskCenter();
    } else {
        showTaskCenter();
    }
}

function showTaskCenter() {
    taskCenterState.isVisible = true;
    document.getElementById('task-center').classList.add('visible');
    refreshTaskList();
    
    // 启动自动刷新
    if (!taskCenterState.refreshTimer) {
        taskCenterState.refreshTimer = setInterval(refreshTaskList, 10000);
    }
}

function hideTaskCenter() {
    taskCenterState.isVisible = false;
    document.getElementById('task-center').classList.remove('visible');
    
    // 停止自动刷新
    if (taskCenterState.refreshTimer) {
        clearInterval(taskCenterState.refreshTimer);
        taskCenterState.refreshTimer = null;
    }
}

/**
 * 刷新任务列表
 */
async function refreshTaskList() {
    try {
        const response = await fetch(`${CONFIG.API_BASE_URL}/api/waybill-download/tasks`);
        const data = await response.json();
        
        taskCenterState.tasks = data.tasks || [];
        renderTaskList();
        updateTaskBadge();
        
    } catch (error) {
        console.error('刷新任务列表失败:', error);
    }
}

/**
 * 渲染任务列表
 */
function renderTaskList() {
    const container = document.getElementById('task-list');
    
    if (taskCenterState.tasks.length === 0) {
        container.innerHTML = '<div class="task-empty">暂无下载任务</div>';
        return;
    }
    
    container.innerHTML = taskCenterState.tasks.map(task => {
        const statusText = {
            'pending': '等待中',
            'running': '进行中',
            'completed': '已完成',
            'partial': '部分完成',
            'failed': '失败'
        }[task.status] || task.status;
        
        const statusClass = {
            'pending': 'pending',
            'running': 'running',
            'completed': 'completed',
            'partial': 'partial',
            'failed': 'failed'
        }[task.status] || '';
        
        const progress = task.total_count > 0 
            ? Math.round((task.completed_count / task.total_count) * 100) 
            : 0;
        
        return `
            <div class="task-item ${statusClass}">
                <div class="task-header">
                    <span class="task-user">${escapeHtml(task.user_name)}</span>
                    <span class="task-status ${statusClass}">${statusText}</span>
                </div>
                <div class="task-info">
                    <span>${task.start_date} ~ ${task.end_date}</span>
                </div>
                <div class="task-progress">
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: ${progress}%"></div>
                    </div>
                    <span class="progress-text">${task.completed_count}/${task.total_count}</span>
                </div>
                <div class="task-actions">
                    ${task.downloaded_files > 0 ? `
                        <button class="btn btn-sm btn-primary" onclick="viewTaskFiles('${task.task_id}')">
                            📁 查看文件(${task.downloaded_files})
                        </button>
                    ` : ''}
                    <button class="btn btn-sm btn-outline" onclick="viewTaskDetail('${task.task_id}')">
                        详情
                    </button>
                    <button class="btn btn-sm btn-danger" onclick="deleteTask('${task.task_id}')">
                        删除
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

/**
 * 更新任务徽章
 */
function updateTaskBadge() {
    const badge = document.getElementById('task-badge');
    const runningCount = taskCenterState.tasks.filter(t => t.status === 'running').length;
    
    if (runningCount > 0) {
        badge.textContent = runningCount;
        badge.style.display = 'flex';
    } else {
        badge.style.display = 'none';
    }
}

/**
 * 查看任务详情
 */
async function viewTaskDetail(taskId) {
    try {
        const response = await fetch(`${CONFIG.API_BASE_URL}/api/waybill-download/tasks/${taskId}`);
        const task = await response.json();
        
        // 子任务状态映射
        const statusMap = {
            'pending': '等待中',
            'submitted': '已提交',
            'completed': '已完成',
            'failed': '任务失败',
            'download_failed': '下载失败'
        };
        
        // 检查是否有失败的子任务
        const hasFailedTasks = task.sub_tasks.some(st => st.status.includes('failed'));
        const isRunning = task.status === 'running';
        
        // 显示详情对话框
        const detailHtml = `
            <h4>任务详情: ${escapeHtml(task.user_name)}</h4>
            <p>日期范围: ${task.start_date} ~ ${task.end_date}</p>
            <p>状态: ${task.status} (${task.completed_count}/${task.total_count})</p>
            <div class="sub-task-list">
                ${task.sub_tasks.map(st => `
                    <div class="sub-task-item ${st.status}">
                        <span class="sub-task-name">${st.period} ${st.date}</span>
                        <span class="sub-task-status">${statusMap[st.status] || st.status}</span>
                        ${st.error ? `<span class="sub-task-error">${st.error}</span>` : ''}
                    </div>
                `).join('')}
            </div>
            ${(hasFailedTasks || task.status === 'partial') && !isRunning ? `
                <div class="task-detail-actions">
                    <button class="btn btn-primary" onclick="retryTask('${task.task_id}')">
                        🔄 重试失败任务
                    </button>
                </div>
            ` : ''}
        `;
        
        document.getElementById('task-detail-content').innerHTML = detailHtml;
        document.getElementById('task-detail-dialog').style.display = 'flex';
        
    } catch (error) {
        showToast('获取任务详情失败', 'error');
    }
}

/**
 * 重试任务
 */
async function retryTask(taskId) {
    try {
        showToast('正在重试任务...', 'info');
        
        const response = await fetch(`${CONFIG.API_BASE_URL}/api/waybill-download/tasks/${taskId}/retry`, {
            method: 'POST'
        });
        const data = await response.json();
        
        if (response.ok && data.success) {
            showToast('重试任务已启动', 'success');
            hideTaskDetailDialog();
            // 刷新任务列表
            await loadTaskList();
        } else {
            throw new Error(data.detail || data.message || '重试失败');
        }
    } catch (error) {
        console.error('重试任务失败:', error);
        showToast(`重试失败: ${error.message}`, 'error');
    }
}

function hideTaskDetailDialog() {
    document.getElementById('task-detail-dialog').style.display = 'none';
}

/**
 * 查看任务文件
 */
async function viewTaskFiles(taskId) {
    try {
        const response = await fetch(`${CONFIG.API_BASE_URL}/api/waybill-download/tasks/${taskId}`);
        const task = await response.json();
        
        if (!task.downloaded_files || task.downloaded_files.length === 0) {
            showToast('暂无已下载的文件', 'info');
            return;
        }
        
        const filesHtml = task.downloaded_files.map(file => `
            <div class="file-item">
                <span class="file-name">${escapeHtml(file.filename)}</span>
                <a href="${CONFIG.API_BASE_URL}/api/waybill-download/tasks/${taskId}/files/${encodeURIComponent(file.filename)}" 
                   class="btn btn-sm btn-primary" download>
                    下载
                </a>
            </div>
        `).join('');
        
        document.getElementById('task-detail-content').innerHTML = `
            <h4>已下载文件</h4>
            <div class="file-list">${filesHtml}</div>
        `;
        document.getElementById('task-detail-dialog').style.display = 'flex';
        
    } catch (error) {
        showToast('获取文件列表失败', 'error');
    }
}

/**
 * 删除任务
 */
async function deleteTask(taskId) {
    if (!confirm('确定要删除此任务吗？')) return;
    
    try {
        const response = await fetch(`${CONFIG.API_BASE_URL}/api/waybill-download/tasks/${taskId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showToast('任务已删除', 'success');
            refreshTaskList();
        } else {
            throw new Error('删除失败');
        }
    } catch (error) {
        showToast('删除任务失败', 'error');
    }
}

// 暴露全局函数
window.showWaybillDownloadDialog = showWaybillDownloadDialog;
window.hideWaybillDownloadDialog = hideWaybillDownloadDialog;
window.submitWaybillDownloadTask = submitWaybillDownloadTask;
window.toggleTaskCenter = toggleTaskCenter;
window.hideTaskCenter = hideTaskCenter;
window.viewTaskDetail = viewTaskDetail;
window.viewTaskFiles = viewTaskFiles;
window.deleteTask = deleteTask;
window.hideTaskDetailDialog = hideTaskDetailDialog;


// ============== Chrome插件更新功能 ==============

/**
 * 在线更新Chrome插件
 */
async function updateExtension() {
    if (!confirm('确定要从GitHub更新Chrome插件代码吗？\n\n更新后需要在Chrome扩展管理页面重新加载插件。')) {
        return;
    }
    
    showToast('正在更新插件代码...', 'info');
    
    try {
        const response = await fetch(`${CONFIG.API_BASE_URL}/api/extension/update`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (!response.ok || !data.success) {
            throw new Error(data.detail || data.message || '更新失败');
        }
        
        showToast(`插件更新成功！已更新 ${data.updated_files} 个文件`, 'success');
        
        // 显示更新详情
        if (data.files && data.files.length > 0) {
            console.log('更新的文件:', data.files);
        }
        
    } catch (error) {
        console.error('更新插件失败:', error);
        showToast(`更新失败: ${error.message}`, 'error');
    }
}

/**
 * 下载Chrome插件压缩包
 */
async function downloadExtension() {
    showToast('正在打包插件...', 'info');
    
    try {
        const response = await fetch(`${CONFIG.API_BASE_URL}/api/extension/download`);
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || '下载失败');
        }
        
        // 下载文件
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'chrome_extension.zip';
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        a.remove();
        
        showToast('插件下载成功', 'success');
    } catch (error) {
        console.error('下载插件失败:', error);
        showToast(`下载失败: ${error.message}`, 'error');
    }
}

window.updateExtension = updateExtension;
window.downloadExtension = downloadExtension;
