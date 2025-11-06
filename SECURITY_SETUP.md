# 安全设置指南

## 初始管理员账户设置

为了提高安全性，系统不再使用硬编码的默认密码。您有两种方式创建初始管理员账户：

### 方式一：通过环境变量（推荐用于自动化部署）

启动应用前设置环境变量：

```bash
export INITIAL_ADMIN_PASSWORD="your-strong-password"
python run.py
```

系统将自动创建用户名为 `admin`、邮箱为 `admin@autocodereview.com` 的管理员账户。

### 方式二：通过首次设置向导（推荐用于手动部署）

1. 启动应用（不设置 INITIAL_ADMIN_PASSWORD）
2. 访问 Web 界面
3. 系统会检测到没有管理员账户，显示首次设置页面
4. 输入管理员用户名、邮箱和密码
5. 完成设置

也可以通过 API 手动创建：

```bash
curl -X POST http://localhost:5000/api/auth/initial-setup \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "email": "admin@example.com",
    "password": "your-strong-password"
  }'
```

**注意**：
- 首次设置只能执行一次，创建第一个管理员后此功能将被禁用
- 密码最少6位字符
- 建议使用强密码（包含大小写字母、数字和特殊字符）

## 检查系统状态

可以通过以下 API 检查系统是否已初始化：

```bash
curl http://localhost:5000/api/auth/system-status
```

响应示例：
```json
{
  "success": true,
  "initialized": true,
  "needs_setup": false
}
```

## 密码安全建议

1. **密码复杂度**：使用至少12位字符的强密码
2. **定期更换**：建议每90天更换一次密码
3. **避免重用**：不要在多个系统中使用相同密码
4. **密码管理器**：推荐使用密码管理工具（如 1Password、Bitwarden）
