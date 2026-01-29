"""
Token Manager Server Tests
FastAPI服务端点测试模块
"""

import os
import pytest
from fastapi.testclient import TestClient

# 设置测试数据库
os.environ['TOKEN_DB_URL'] = 'sqlite:///test_server_api.db'

from token_manager.server import app
from token_manager.token_service import reset_token_service
from token_manager.websocket_manager import reset_websocket_manager
from token_manager.models import close_database, init_database


@pytest.fixture(autouse=True)
def setup_teardown():
    """每个测试前后的设置和清理"""
    # 重置服务（先重置服务再关闭数据库）
    reset_token_service()
    reset_websocket_manager()
    close_database()
    init_database()
    
    yield
    
    # 清理（先重置服务再关闭数据库）
    reset_token_service()
    reset_websocket_manager()
    close_database()
    
    # 删除测试数据库
    if os.path.exists('test_server_api.db'):
        try:
            os.remove('test_server_api.db')
        except:
            pass


@pytest.fixture
def client():
    """创建测试客户端"""
    return TestClient(app)


class TestHealthEndpoint:
    """健康检查端点测试"""
    
    def test_health_check(self, client):
        """测试健康检查端点"""
        response = client.get('/health')
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'
        assert 'timestamp' in data


class TestTokensAPI:
    """Token REST API测试"""
    
    def test_get_tokens_empty(self, client):
        """测试获取空Token列表"""
        response = client.get('/api/tokens')
        assert response.status_code == 200
        data = response.json()
        assert data['total'] == 0
        assert data['tokens'] == []
    
    def test_create_token(self, client):
        """测试创建Token"""
        response = client.post('/api/tokens', json={
            'token': 'test_token_value_12345678901234567890',
            'user_id': 'test_user_001',
            'extension_id': 'ext_001'
        })
        assert response.status_code == 200
        data = response.json()
        assert data['id'] == 1
        assert data['user_id'] == 'test_user_001'
        assert data['status'] == 'active'
        assert 'token_masked' in data
        # 验证Token已脱敏
        assert '...' in data['token_masked']
    
    def test_create_token_invalid(self, client):
        """测试创建无效Token"""
        response = client.post('/api/tokens', json={
            'token': 'short',  # 太短
            'user_id': 'test_user'
        })
        assert response.status_code == 400
    
    def test_update_existing_token(self, client):
        """测试更新已存在的Token"""
        # 创建第一个Token
        client.post('/api/tokens', json={
            'token': 'first_token_value_12345678901234567890',
            'user_id': 'test_user_001'
        })
        
        # 更新同一用户的Token
        response = client.post('/api/tokens', json={
            'token': 'second_token_value_12345678901234567890',
            'user_id': 'test_user_001'
        })
        assert response.status_code == 200
        
        # 验证只有一条记录
        response = client.get('/api/tokens')
        assert response.json()['total'] == 1
    
    def test_get_token_by_user(self, client):
        """测试获取指定用户Token"""
        # 创建Token
        client.post('/api/tokens', json={
            'token': 'test_token_value_12345678901234567890',
            'user_id': 'test_user_001'
        })
        
        # 获取Token
        response = client.get('/api/tokens/test_user_001')
        assert response.status_code == 200
        data = response.json()
        assert data['user_id'] == 'test_user_001'
    
    def test_get_token_by_user_not_found(self, client):
        """测试获取不存在的用户Token"""
        response = client.get('/api/tokens/nonexistent_user')
        assert response.status_code == 404
    
    def test_delete_token(self, client):
        """测试删除Token"""
        # 创建Token
        response = client.post('/api/tokens', json={
            'token': 'test_token_value_12345678901234567890',
            'user_id': 'test_user_001'
        })
        token_id = response.json()['id']
        
        # 删除Token
        response = client.delete(f'/api/tokens/{token_id}')
        assert response.status_code == 200
        assert response.json()['success'] == True
        
        # 验证已删除
        response = client.get('/api/tokens/test_user_001')
        assert response.status_code == 404
    
    def test_delete_token_not_found(self, client):
        """测试删除不存在的Token"""
        response = client.delete('/api/tokens/9999')
        assert response.status_code == 404


class TestWebSocketEndpoint:
    """WebSocket端点测试"""
    
    def test_websocket_register(self, client):
        """测试WebSocket注册"""
        with client.websocket_connect('/ws') as websocket:
            # 发送注册消息
            websocket.send_json({
                'type': 'register',
                'timestamp': 1234567890000,
                'payload': {
                    'extensionId': 'test_ext_001',
                    'version': '1.0.0'
                }
            })
            
            # 接收注册确认
            response = websocket.receive_json()
            assert response['type'] == 'register_ack'
            assert response['payload']['success'] == True
    
    def test_websocket_token_upload(self, client):
        """测试WebSocket Token上报"""
        with client.websocket_connect('/ws') as websocket:
            # 注册
            websocket.send_json({
                'type': 'register',
                'timestamp': 1234567890000,
                'payload': {'extensionId': 'test_ext_001', 'version': '1.0.0'}
            })
            websocket.receive_json()  # 接收注册确认
            
            # 上报Token
            websocket.send_json({
                'type': 'token_upload',
                'timestamp': 1234567890001,
                'payload': {
                    'token': 'ws_test_token_12345678901234567890',
                    'userId': 'ws_user_001',
                    'source': 'response'
                }
            })
            
            # 接收确认
            response = websocket.receive_json()
            assert response['type'] == 'token_ack'
            assert response['payload']['success'] == True
            assert 'tokenId' in response['payload']
        
        # 验证Token已存储
        response = client.get('/api/tokens/ws_user_001')
        assert response.status_code == 200
    
    def test_websocket_heartbeat(self, client):
        """测试WebSocket心跳"""
        with client.websocket_connect('/ws') as websocket:
            # 注册
            websocket.send_json({
                'type': 'register',
                'timestamp': 1234567890000,
                'payload': {'extensionId': 'test_ext_001', 'version': '1.0.0'}
            })
            websocket.receive_json()
            
            # 发送心跳
            websocket.send_json({
                'type': 'heartbeat',
                'timestamp': 1234567890002,
                'payload': {'extensionId': 'test_ext_001'}
            })
            
            # 接收心跳确认
            response = websocket.receive_json()
            assert response['type'] == 'heartbeat_ack'
    
    def test_websocket_invalid_first_message(self, client):
        """测试WebSocket第一条消息非注册消息"""
        with client.websocket_connect('/ws') as websocket:
            # 发送非注册消息
            websocket.send_json({
                'type': 'heartbeat',
                'timestamp': 1234567890000,
                'payload': {'extensionId': 'test_ext_001'}
            })
            
            # 应该收到错误消息
            response = websocket.receive_json()
            assert response['type'] == 'error'


class TestConnectionsAPI:
    """WebSocket连接列表API测试"""
    
    def test_get_connections_empty(self, client):
        """测试获取空连接列表"""
        response = client.get('/api/connections')
        assert response.status_code == 200
        data = response.json()
        assert data['total'] == 0
        assert data['connections'] == []
    
    def test_get_connections_with_active(self, client):
        """测试获取有活跃连接的列表"""
        with client.websocket_connect('/ws') as websocket:
            # 注册
            websocket.send_json({
                'type': 'register',
                'timestamp': 1234567890000,
                'payload': {'extensionId': 'test_ext_001', 'version': '1.0.0'}
            })
            websocket.receive_json()
            
            # 获取连接列表
            response = client.get('/api/connections')
            assert response.status_code == 200
            data = response.json()
            assert data['total'] == 1
            assert data['connections'][0]['extension_id'] == 'test_ext_001'



class TestAuthAPI:
    """认证API测试"""
    
    def test_verify_password_correct(self, client):
        """测试正确密码验证"""
        response = client.post('/api/auth/verify', json={
            'password': 'admin123'  # 默认密码
        })
        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True
        assert data['message'] == '认证成功'
    
    def test_verify_password_incorrect(self, client):
        """测试错误密码验证"""
        response = client.post('/api/auth/verify', json={
            'password': 'wrong_password'
        })
        assert response.status_code == 200
        data = response.json()
        assert data['success'] == False
        assert data['message'] == '密码错误'
    
    def test_verify_password_empty(self, client):
        """测试空密码验证"""
        response = client.post('/api/auth/verify', json={
            'password': ''
        })
        # 空密码应该被Pydantic验证拒绝
        assert response.status_code == 422


class TestManagementRoutes:
    """管理界面路由测试"""
    
    def test_root_redirect(self, client):
        """测试根路径访问"""
        response = client.get('/')
        # 应该返回HTML文件或404（如果静态文件不存在）
        assert response.status_code in [200, 404]
    
    def test_management_page(self, client):
        """测试管理界面路径"""
        response = client.get('/management')
        # 应该返回HTML文件或404（如果静态文件不存在）
        assert response.status_code in [200, 404]
