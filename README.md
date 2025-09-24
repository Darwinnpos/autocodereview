![cd8be7f3c553d3a372a842867584a057](https://github.com/user-attachments/assets/31483172-a741-4c39-a3fe-0843f6faea08)![d2ab3f363042fc2a1c55d1650b5a6401](https://github.com/user-attachments/assets/94f52421-f768-4b11-a848-0aeb74266b4d)

# AutoCodeReview - 自动化代码审查系统

基于Flask的自动化代码审查系统，支持GitLab集成，能够自动分析代码并在Merge Request中添加精准的行级评论。

## 🚀 功能特性

- **🔍 多语言支持**: Python、JavaScript、Java、C++等主流编程语言
- **🛡️ 安全扫描**: 自动检测常见安全漏洞和风险代码模式
- **⚡ 性能分析**: 识别性能瓶颈和优化建议
- **🎨 代码风格**: 检查代码规范和最佳实践
- **📝 精准评论**: 按行添加评论，精确定位问题
- **💾 持久化存储**: 完整记录每次审查的详细信息
- **🔧 可配置**: 灵活的用户配置和规则自定义
- **🌐 Web界面**: 直观的Web管理界面

## 📋 系统要求

- Python 3.8+
- GitLab 实例（支持API访问）
- 2GB+ 内存

## 🛠️ 安装部署

### 1. 克隆项目

```bash
git clone <repository_url>
cd autocodereview
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境

```bash
# 开发环境
export FLASK_ENV=development

# 生产环境
export FLASK_ENV=production
export SECRET_KEY=your-secret-key
export DATABASE_PATH=/path/to/reviews.db
export USER_CONFIG_DIR=/path/to/user_configs
```

### 4. 启动服务

```bash
python run.py
```

服务默认运行在 `http://localhost:5000`

## 🎯 快速开始

### 1. 配置用户信息

访问 `http://localhost:5000/config` 创建用户配置：

- **用户ID**: 唯一标识符
- **GitLab URL**: 您的GitLab实例地址
- **访问令牌**: GitLab个人访问令牌（需要API权限）

### 2. 开始代码审查

访问 `http://localhost:5000`：

1. 输入您的用户ID
2. 粘贴GitLab MR的完整URL
3. 点击"开始审查"

### 3. 查看结果

系统会自动：
- 分析MR中的代码变更
- 识别潜在问题
- 在GitLab MR中添加详细评论
- 生成审查总结

## 🔧 API 使用

### 开始代码审查

```bash
curl -X POST http://localhost:5000/api/review \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "your_user_id",
    "mr_url": "https://gitlab.com/group/project/-/merge_requests/123"
  }'
```

### 获取审查历史

```bash
curl "http://localhost:5000/api/reviews?user_id=your_user_id&limit=10"
```

### 创建用户配置

```bash
curl -X POST http://localhost:5000/api/config \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "your_user_id",
    "gitlab_url": "https://gitlab.com",
    "access_token": "glpat-xxxxxxxxxxxxxxxxxxxx",
    "reviewer_name": "AutoCodeReview"
  }'
```

## 📊 支持的检查类型

### 🔒 安全性检查
- 代码注入漏洞
- 不安全的函数使用
- 敏感信息泄露
- 认证和授权问题

### ⚡ 性能检查
- 低效算法
- 资源泄露
- 循环优化
- 内存使用

### 🎨 代码风格
- 命名规范
- 代码格式
- 注释质量
- 代码结构

### 🧠 逻辑检查
- 代码简化建议
- 最佳实践
- 可读性改进
- 维护性提升

## 🏗️ 项目结构

```
autocodereview/
├── app/                    # 应用主目录
│   ├── __init__.py        # Flask应用初始化
│   ├── models/            # 数据模型
│   │   ├── user.py        # 用户配置模型
│   │   └── review.py      # 审查记录模型
│   ├── services/          # 核心业务逻辑
│   │   ├── gitlab_client.py     # GitLab API客户端
│   │   ├── code_analyzer.py     # 代码分析引擎
│   │   ├── comment_generator.py # 评论生成器
│   │   └── review_service.py    # 审查服务协调器
│   ├── api/               # REST API端点
│   │   ├── auth.py        # 认证相关
│   │   ├── review.py      # 审查相关API
│   │   └── config.py      # 配置相关API
│   └── templates/         # Web界面模板
├── config/               # 配置文件
├── requirements.txt      # Python依赖
├── run.py               # 应用启动入口
└── README.md            # 项目说明
```

## 🔐 安全配置

### GitLab 访问令牌权限

创建GitLab个人访问令牌时，需要以下权限：
- `api` - 访问API
- `read_repository` - 读取仓库
- `write_repository` - 写入评论（可选）

### 环境变量配置

生产环境建议配置：

```bash
export SECRET_KEY=your-random-secret-key
export DATABASE_PATH=/secure/path/reviews.db
export USER_CONFIG_DIR=/secure/path/user_configs
export CORS_ORIGINS=https://your-domain.com
```

## 📈 监控和日志

系统提供以下监控端点：

- `/health` - 健康检查
- `/api/reviews/statistics` - 审查统计
- 详细的日志记录

## 🤝 贡献指南

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📝 更新日志

### v1.0.0 (2025-01-XX)
- 🎉 初始版本发布
- ✅ 支持Python、JavaScript、Java代码分析
- ✅ GitLab集成
- ✅ Web管理界面
- ✅ 持久化存储
- ✅ RESTful API

## 🆘 故障排除

### 常见问题

**Q: GitLab连接失败**
A: 检查GitLab URL和访问令牌是否正确，确保令牌具有足够权限

**Q: 评论发布失败**
A: 确认访问令牌具有写入权限，检查MR是否开放

**Q: 代码分析无结果**
A: 检查MR中是否有支持的文件类型，确认有代码变更

### 调试模式

```bash
export FLASK_ENV=development
python run.py
```

## 📞 支持

如有问题或建议，请：
- 创建 Issue
- 发送邮件至 support@example.com
- 查看Wiki文档

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情
