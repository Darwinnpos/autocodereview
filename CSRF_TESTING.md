# CSRF 保护测试指南

## ✅ 已完成的工作

1. **创建了CSRF管理器** (`app/static/js/csrf.js`)
   - 自动获取和缓存CSRF token
   - 拦截所有Axios请求，自动添加token
   - 包装原生fetch，自动添加token
   - 自动重试CSRF错误

2. **集成到所有页面**
   - ✓ `base.html` - 所有继承页面自动启用
   - ✓ `setup.html` - 首次设置向导页面

3. **启用后端CSRF保护**
   - ✓ Flask-WTF CSRF保护已启用
   - ✓ 支持通过 `X-CSRFToken` HTTP头传递token

## 🧪 测试步骤

### 测试1：检查CSRF脚本是否加载

1. **重启应用**
   ```bash
   # 停止当前运行的应用（Ctrl+C）
   python run.py
   ```

2. **打开浏览器控制台**
   - 访问 `http://localhost:5000/login`
   - 按 F12 打开开发者工具
   - 查看Console标签

3. **验证输出**
   应该看到：
   ```
   ✓ CSRF protection initialized
   ```

### 测试2：登录功能（最重要）

1. **使用管理员账户登录**
   - 用户名: `admin`
   - 密码: `admin123`

2. **预期结果**
   - ✅ 登录成功，跳转到主页
   - ✅ 控制台无CSRF错误

3. **如果失败**
   - 检查控制台错误信息
   - 检查Network标签，查看请求是否包含 `X-CSRFToken` 头

### 测试3：验证CSRF Token自动添加

1. **打开浏览器开发者工具 Network 标签**

2. **进行任意POST操作**（如登录、提交表单等）

3. **检查请求头**
   应该看到：
   ```
   Request Headers:
   X-CSRFToken: <token值>
   Cookie: session=...
   ```

### 测试4：模拟CSRF攻击（应该失败）

```bash
# 不带CSRF token的请求应该被拒绝
curl -X POST http://localhost:5000/api/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'
```

**预期结果**: 400 Bad Request，提示CSRF token缺失

### 测试5：正确的CSRF请求

```bash
# 1. 获取CSRF token
TOKEN=$(curl -s http://localhost:5000/api/csrf-token -c cookies.txt | grep -o '"csrf_token":"[^"]*"' | cut -d'"' -f4)

echo "CSRF Token: $TOKEN"

# 2. 使用token发送请求
curl -X POST http://localhost:5000/api/login \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: $TOKEN" \
  -b cookies.txt \
  -d '{"username": "admin", "password": "admin123"}'
```

**预期结果**: 登录成功

## 🔍 常见问题排查

### 问题1：登录时提示 "CSRF token missing"

**原因**: csrf.js脚本未正确加载

**解决**:
1. 检查 `app/static/js/csrf.js` 文件是否存在
2. 清除浏览器缓存（Ctrl+Shift+Delete）
3. 硬刷新页面（Ctrl+F5）

### 问题2：控制台显示 "Failed to fetch CSRF token"

**原因**: `/api/csrf-token` 端点不可访问

**解决**:
```bash
# 测试端点
curl http://localhost:5000/api/csrf-token

# 应该返回:
# {"success": true, "csrf_token": "..."}
```

### 问题3：所有POST请求都返回400

**原因**: CSRF token未添加到请求

**检查**:
1. 打开浏览器开发者工具 → Network
2. 选择一个失败的请求
3. 查看 Request Headers 是否有 `X-CSRFToken`

**修复**:
```javascript
// 在浏览器控制台手动测试
await getCSRFToken();  // 应该返回token字符串
```

### 问题4：Axios请求正常，原生fetch失败

**原因**: fetch未正确包装

**检查**:
```javascript
// 在浏览器控制台测试
console.log(window.fetch.toString().includes('csrfManager'));
// 应该返回 true
```

## 📊 监控CSRF保护

### 在浏览器控制台检查CSRF状态

```javascript
// 获取当前token
await window.csrfManager.getToken();

// 查看token过期时间
console.log(window.csrfManager.tokenExpiry);

// 强制刷新token
await window.csrfManager.refreshToken();

// 清除token缓存
window.clearCSRFToken();
```

### 验证Axios拦截器

```javascript
// 检查拦截器数量
console.log(axios.interceptors.request.handlers.length);  // 应该 > 0
console.log(axios.interceptors.response.handlers.length); // 应该 > 0
```

## 🛠️ 临时禁用CSRF（仅用于调试）

如果需要临时禁用CSRF进行调试：

```python
# app/__init__.py:29
app.config['WTF_CSRF_ENABLED'] = False  # 禁用
```

**⚠️ 警告**: 生产环境必须启用CSRF保护！

## ✅ 验证清单

在部署前确认：

- [ ] 浏览器控制台显示 "✓ CSRF protection initialized"
- [ ] 登录功能正常工作
- [ ] 所有POST/PUT/PATCH/DELETE请求包含 `X-CSRFToken` 头
- [ ] 不带token的请求被拒绝（返回400）
- [ ] `/api/csrf-token` 端点可访问
- [ ] 生产环境 `WTF_CSRF_ENABLED = True`

## 📝 技术细节

### CSRF保护流程

```
用户访问页面
    ↓
csrf.js 自动加载
    ↓
预加载 CSRF token (缓存10分钟)
    ↓
用户发起 POST/PUT/PATCH/DELETE 请求
    ↓
Axios/Fetch 拦截器自动添加 X-CSRFToken 头
    ↓
Flask-WTF 验证 token
    ↓
- 有效 → 处理请求
- 无效/缺失 → 返回 400错误
    ↓
如果是CSRF错误，自动刷新token并重试一次
```

### 性能优化

- Token缓存10分钟，减少服务器请求
- 页面加载时预加载token（异步，不阻塞渲染）
- 仅对需要保护的方法（POST等）添加token
- 自动重试机制，token过期时无感刷新

## 🔒 安全建议

1. **始终使用HTTPS**: CSRF token通过HTTP头传输，需要加密
2. **设置合理的session过期时间**: 默认24小时
3. **定期审查CSRF日志**: 检查异常的CSRF错误
4. **不要在URL中传递token**: 仅通过HTTP头
5. **确保CORS配置正确**: `supports_credentials=True`
