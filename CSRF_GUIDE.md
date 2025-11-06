# CSRF 保护使用指南

## 概述

系统已启用 CSRF (Cross-Site Request Forgery) 保护，所有状态改变的请求（POST、PUT、PATCH、DELETE）都需要包含有效的 CSRF token。

## 前端使用方法

### 1. 获取 CSRF Token

在发送需要保护的请求之前，先获取 CSRF token：

```javascript
// 获取 CSRF token
async function getCsrfToken() {
    const response = await fetch('/api/csrf-token', {
        method: 'GET',
        credentials: 'include'  // 重要：携带 session cookie
    });
    const data = await response.json();
    return data.csrf_token;
}
```

### 2. 在请求中包含 CSRF Token

#### 方法一：通过 HTTP 头（推荐）

```javascript
// 示例：登录请求
async function login(username, password) {
    const csrfToken = await getCsrfToken();

    const response = await fetch('/api/login', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken  // 包含 CSRF token
        },
        credentials: 'include',  // 携带 cookie
        body: JSON.stringify({ username, password })
    });

    return response.json();
}
```

#### 方法二：通过表单字段

```html
<!-- HTML 表单 -->
<form method="POST" action="/api/some-action">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <!-- 其他表单字段 -->
</form>
```

### 3. Axios 全局配置（如果使用 Axios）

```javascript
// 在应用初始化时配置
async function setupAxios() {
    const csrfToken = await getCsrfToken();

    // 设置默认请求头
    axios.defaults.headers.common['X-CSRFToken'] = csrfToken;
    axios.defaults.withCredentials = true;
}

// 调用
setupAxios();
```

### 4. 请求拦截器（自动刷新 token）

```javascript
// 创建 axios 实例
const api = axios.create({
    baseURL: '/api',
    withCredentials: true
});

// 请求拦截器：自动添加 CSRF token
api.interceptors.request.use(async (config) => {
    // 仅对状态改变的方法添加 CSRF token
    if (['post', 'put', 'patch', 'delete'].includes(config.method.toLowerCase())) {
        const csrfToken = await getCsrfToken();
        config.headers['X-CSRFToken'] = csrfToken;
    }
    return config;
}, (error) => {
    return Promise.reject(error);
});

// 响应拦截器：处理 CSRF 错误
api.interceptors.response.use(
    (response) => response,
    async (error) => {
        if (error.response && error.response.status === 400) {
            const errorData = error.response.data;
            if (errorData.error && errorData.error.includes('CSRF')) {
                // CSRF token 失效，刷新并重试
                const csrfToken = await getCsrfToken();
                error.config.headers['X-CSRFToken'] = csrfToken;
                return api.request(error.config);
            }
        }
        return Promise.reject(error);
    }
);
```

## 重要注意事项

### 1. 凭证携带

所有请求必须携带 credentials（session cookie）：

```javascript
// Fetch API
fetch(url, {
    credentials: 'include'  // 必须！
});

// Axios
axios.defaults.withCredentials = true;
```

### 2. CORS 配置

如果前后端分离部署，确保后端 CORS 配置正确：

```python
# 后端已配置
CORS(app, supports_credentials=True)
```

前端也需要正确配置：

```javascript
// 允许携带凭证
axios.defaults.withCredentials = true;
```

### 3. Token 生命周期

- CSRF token 与 session 绑定
- Token 不会自动过期（依赖 session 过期）
- 登录/登出后会生成新的 token
- 建议在每次请求前获取新的 token（性能开销很小）

### 4. 错误处理

如果收到 CSRF 相关错误：

```javascript
// 典型错误响应
{
    "error": "The CSRF token is missing."
}
{
    "error": "The CSRF token is invalid."
}
```

处理方法：
1. 检查是否包含 `X-CSRFToken` 头
2. 检查是否携带 `credentials: 'include'`
3. 重新获取 token 并重试

## 示例：完整的登录流程

```javascript
// 完整示例
async function performLogin() {
    try {
        // 1. 获取 CSRF token
        const csrfToken = await getCsrfToken();

        // 2. 发送登录请求
        const response = await fetch('/api/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            credentials: 'include',
            body: JSON.stringify({
                username: 'admin',
                password: 'your-password'
            })
        });

        // 3. 处理响应
        const data = await response.json();

        if (data.success) {
            console.log('登录成功');
        } else {
            console.error('登录失败:', data.error);
        }

    } catch (error) {
        console.error('请求失败:', error);
    }
}
```

## 测试 CSRF 保护

### 测试有效请求

```bash
# 1. 获取 CSRF token
curl -X GET http://localhost:5000/api/csrf-token \
  -c cookies.txt

# 2. 提取 token（假设返回 {"success": true, "csrf_token": "abc123"}）
TOKEN="abc123"

# 3. 发送受保护的请求
curl -X POST http://localhost:5000/api/login \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: $TOKEN" \
  -b cookies.txt \
  -d '{"username": "admin", "password": "password"}'
```

### 测试无效请求（应该失败）

```bash
# 不包含 CSRF token
curl -X POST http://localhost:5000/api/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "password"}'

# 预期：400 Bad Request，CSRF token missing
```

## 常见问题

### Q1: 为什么我的请求总是返回 CSRF 错误？

**A**: 检查以下几点：
1. 是否在请求头中包含了 `X-CSRFToken`
2. 是否设置了 `credentials: 'include'`（Fetch）或 `withCredentials: true`（Axios）
3. CSRF token 是否是最新的（登录后需要重新获取）

### Q2: 开发环境能否临时禁用 CSRF？

**A**: 不推荐！但如果必须，可以在配置中设置：

```python
# config/development.py
WTF_CSRF_ENABLED = False  # 仅用于调试，生产环境必须启用
```

### Q3: 如何在单页应用（SPA）中使用？

**A**: 在应用启动时获取一次 token，存储在内存中：

```javascript
// app.js
let csrfToken = null;

async function initApp() {
    // 获取并缓存 token
    csrfToken = await getCsrfToken();

    // 配置 axios
    axios.defaults.headers.common['X-CSRFToken'] = csrfToken;
    axios.defaults.withCredentials = true;
}

initApp();
```

## 安全最佳实践

1. **始终启用 CSRF 保护**（生产环境）
2. **使用 HTTPS**：防止 token 被窃取
3. **设置正确的 CORS 策略**：只允许可信域名
4. **定期刷新 token**：虽然不强制，但建议每次关键操作前获取新 token
5. **监控 CSRF 错误**：异常的 CSRF 错误可能表明正在遭受攻击
