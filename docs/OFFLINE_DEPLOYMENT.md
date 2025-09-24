# 🚀 AutoCodeReview 离线部署指南

## 概览

AutoCodeReview 系统已完全支持离线部署，所有前端资源已本地化，无需外网连接即可正常运行。

## ✅ 已解决的离线部署问题

### 1. 静态资源本地化

**之前的CDN依赖：**
```html
<!-- 原有的CDN引用 -->
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.7.2/font/bootstrap-icons.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/axios/dist/axios.min.js"></script>
```

**现在的本地引用：**
```html
<!-- 本地化后的引用 -->
<link href="{{ url_for('static', filename='css/bootstrap.min.css') }}" rel="stylesheet">
<link href="{{ url_for('static', filename='css/bootstrap-icons.css') }}" rel="stylesheet">
<script src="{{ url_for('static', filename='js/bootstrap.bundle.min.js') }}"></script>
<script src="{{ url_for('static', filename='js/axios.min.js') }}"></script>
```

### 2. 本地静态资源文件结构

```
app/static/
├── css/
│   ├── bootstrap.min.css          (163KB)
│   ├── bootstrap-icons.css        (73KB)
│   └── fonts/
│       ├── bootstrap-icons.woff2  (92KB)
│       └── bootstrap-icons.woff   (120KB)
└── js/
    ├── bootstrap.bundle.min.js    (78KB)
    └── axios.min.js               (55KB)
```

**总大小：** 约 580KB 的静态资源

## 🔧 离线部署步骤

### 1. 环境准备
```bash
# Python 环境
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 2. 数据库初始化
```bash
# 系统会自动创建SQLite数据库
# auth.db - 用户认证数据
# reviews.db - 审查记录数据
```

### 3. 配置文件准备
```bash
# 配置环境变量（可选）
export FLASK_ENV=production
export SECRET_KEY=your-secret-key-here
```

### 4. 启动服务
```bash
# 开发环境
python3 run.py

# 生产环境
gunicorn -w 4 -b 0.0.0.0:5000 run:app
```

## 🌐 网络要求

### 离线模式支持
- ✅ **Web界面**: 完全离线，无需外网连接
- ✅ **静态资源**: 全部本地化
- ✅ **数据库**: SQLite本地数据库
- ✅ **基础功能**: 用户管理、审查记录等

### 需要网络连接的功能
- 🌐 **GitLab集成**: 需要访问GitLab服务器
- 🌐 **AI代码分析**: 需要访问AI API（OpenAI等）

## ⚙️ 配置选项

### 1. GitLab配置
用户需要配置：
- GitLab服务器地址
- Access Token
- 项目权限

### 2. AI分析配置（可选）
- AI API URL
- API密钥
- 模型选择

如果不配置AI，系统仍可正常运行，只是无AI分析功能。

## 📦 部署包准备

### 完整离线部署包应包含：
```
autocodereview/
├── app/                    # 应用主目录
│   ├── static/            # 本地静态资源 ✅
│   ├── templates/         # HTML模板
│   ├── models/           # 数据模型
│   ├── services/         # 业务逻辑
│   └── api/              # API接口
├── requirements.txt       # Python依赖
├── run.py                # 启动脚本
└── config/               # 配置文件
```

### 部署检查清单
- ✅ 所有Python依赖已安装
- ✅ 静态资源文件完整
- ✅ 数据库权限正确
- ✅ 端口配置正确
- ✅ 防火墙规则设置
- ⚠️ GitLab连接配置（如需要）
- ⚠️ AI API配置（如需要）

## 🔍 验证部署

### 1. 静态资源测试
```bash
# 测试CSS文件
curl -I http://localhost:5000/static/css/bootstrap.min.css

# 测试JS文件
curl -I http://localhost:5000/static/js/bootstrap.bundle.min.js

# 测试字体文件
curl -I http://localhost:5000/static/css/fonts/bootstrap-icons.woff2
```

### 2. 功能验证
- 访问主页，检查样式是否正常
- 测试用户注册/登录
- 检查图标显示是否正常
- 验证表单交互功能

## 🚨 故障排除

### 1. 静态资源404错误
- 检查 `app/static/` 目录是否存在
- 验证文件权限是否正确
- 确认Flask静态文件配置

### 2. 样式/图标不显示
- 检查浏览器开发者工具网络面板
- 验证字体文件是否下载完整
- 检查Content-Type是否正确

### 3. JavaScript功能异常
- 检查axios.min.js是否正常加载
- 验证bootstrap.bundle.min.js完整性
- 查看浏览器控制台错误信息

## 📊 性能优化

### 1. 静态资源缓存
```python
# 在生产环境中启用静态文件缓存
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000  # 1年
```

### 2. 压缩优化
- 静态文件已使用min版本
- 可考虑启用gzip压缩
- 使用CDN(如果有内网CDN)

## ✨ 离线部署优势

1. **安全性**: 不依赖外部CDN，避免供应链攻击
2. **稳定性**: 不受外网影响，服务更稳定
3. **速度**: 本地资源加载更快
4. **合规性**: 满足内网部署要求
5. **成本**: 降低带宽消耗

---

🎉 **AutoCodeReview 现已完全支持离线部署！** 可以在任何内网环境中安全稳定运行。