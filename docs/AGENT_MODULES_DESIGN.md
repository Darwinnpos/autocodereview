# AI Agent代码审查系统 - 模块组织设计

## 总体模块架构

```
app/
├── agents/                          # Agent核心模块
│   ├── __init__.py
│   ├── core/                        # 核心Agent组件
│   │   ├── __init__.py
│   │   ├── base_agent.py           # Agent基础类
│   │   ├── conversation.py         # 对话管理
│   │   ├── state_machine.py        # 状态机管理
│   │   └── context.py              # 上下文管理
│   ├── analyzers/                   # 专门化分析器
│   │   ├── __init__.py
│   │   ├── code_analyzer.py        # 代码分析Agent (当前实现)
│   │   ├── security_analyzer.py    # 安全分析Agent (未来)
│   │   ├── performance_analyzer.py # 性能分析Agent (未来)
│   │   └── style_analyzer.py       # 代码风格Agent (未来)
│   └── orchestration/               # 编排系统
│       ├── __init__.py
│       ├── orchestrator.py         # 主编排器
│       ├── task_scheduler.py       # 任务调度器
│       ├── resource_manager.py     # 资源管理器
│       └── result_aggregator.py    # 结果聚合器
├── services/                        # 现有服务层
│   ├── ai_analyzer.py              # 传统AI分析器 (保留兼容)
│   ├── ai_agent.py                 # Agent实现 (当前位置)
│   ├── review_service.py           # 审查服务主控制器
│   ├── gitlab_client.py            # GitLab API客户端
│   └── comment_generator.py        # 评论生成器
├── permissions/                     # 权限管理模块
│   ├── __init__.py
│   ├── manager.py                  # 权限管理器
│   ├── policies.py                 # 权限策略
│   ├── authorizer.py               # 授权器
│   └── audit.py                    # 审计日志
├── ui/                             # 用户界面模块
│   ├── __init__.py
│   ├── progress/                   # 进度展示
│   │   ├── tracker.py              # 进度跟踪器
│   │   └── visualizer.py           # 进度可视化
│   ├── comments/                   # 评论管理界面
│   │   ├── manager.py              # 评论管理器
│   │   ├── preview.py              # 评论预览
│   │   └── editor.py               # 评论编辑器
│   └── permissions/                # 权限界面
│       ├── confirmer.py            # 权限确认界面
│       └── history.py              # 权限历史
├── models/                         # 数据模型
│   ├── agent_models.py             # Agent相关模型
│   ├── comment_models.py           # 评论数据模型
│   ├── permission_models.py        # 权限数据模型
│   └── session_models.py           # 会话数据模型
├── api/                            # API接口层
│   ├── agents/                     # Agent相关API
│   │   ├── __init__.py
│   │   ├── analysis.py             # 分析API
│   │   └── status.py               # 状态API
│   ├── comments/                   # 评论相关API
│   │   ├── __init__.py
│   │   ├── management.py           # 评论管理API
│   │   └── preview.py              # 评论预览API
│   └── permissions/                # 权限相关API
│       ├── __init__.py
│       ├── requests.py             # 权限请求API
│       └── decisions.py            # 权限决策API
└── utils/                          # 工具模块
    ├── monitoring/                 # 监控工具
    │   ├── metrics.py              # 指标收集
    │   ├── alerts.py               # 告警系统
    │   └── performance.py          # 性能监控
    ├── caching/                    # 缓存系统
    │   ├── redis_cache.py          # Redis缓存
    │   └── memory_cache.py         # 内存缓存
    └── security/                   # 安全工具
        ├── filters.py              # 安全过滤器
        └── validators.py           # 输入验证器
```

## 分阶段实现计划

### 阶段1：核心Agent基础 (当前阶段)
**目标：** 建立可工作的基础Agent系统

**当前状态：**
```
✅ app/services/ai_agent.py         # 基础Agent实现
✅ 集成到review_service.py         # 基础集成完成
```

**下一步：**
```
📋 测试基础功能
📋 创建核心模块分离
```

### 阶段2：模块分离重构
**目标：** 将代码重构为模块化架构

**计划重构：**
```
app/services/ai_agent.py → app/agents/analyzers/code_analyzer.py
新增: app/agents/core/base_agent.py
新增: app/agents/core/conversation.py
新增: app/agents/core/state_machine.py
```

### 阶段3：编排系统
**目标：** 实现多Agent编排和任务调度

**新增模块：**
```
app/agents/orchestration/orchestrator.py
app/agents/orchestration/task_scheduler.py
app/agents/orchestration/resource_manager.py
```

### 阶段4：权限管理
**目标：** 完整的权限控制体系

**新增模块：**
```
app/permissions/manager.py
app/permissions/policies.py
app/ui/permissions/confirmer.py
```

### 阶段5：用户界面增强
**目标：** 丰富的用户交互界面

**新增模块：**
```
app/ui/progress/tracker.py
app/ui/comments/manager.py
app/api/agents/analysis.py
```

## 模块间依赖关系

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   UI Layer      │    │   API Layer     │    │ Permissions     │
│                 │    │                 │    │                 │
│ progress/       │◄───┤ agents/         │    │ manager.py      │
│ comments/       │    │ comments/       │    │ policies.py     │
│ permissions/    │    │ permissions/    │    │ authorizer.py   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
              ┌─────────────────────────────────────┐
              │         Services Layer              │
              │                                     │
              │ review_service.py ←→ gitlab_client  │
              │        ↕                            │
              │ comment_generator.py                │
              └─────────────────────────────────────┘
                                 │
              ┌─────────────────────────────────────┐
              │         Agents Layer                │
              │                                     │
              │ orchestration/  ←→  analyzers/      │
              │     ↕                  ↕            │
              │   core/         ←→   models/        │
              └─────────────────────────────────────┘
                                 │
              ┌─────────────────────────────────────┐
              │         Utils Layer                 │
              │                                     │
              │ monitoring/ caching/ security/      │
              └─────────────────────────────────────┘
```

## 配置管理

### 用户配置扩展
```python
# 在现有user.ai_config基础上扩展
user_config = {
    "ai_config": {
        # 现有AI配置
        "ai_api_url": "...",
        "ai_api_key": "...",
        "ai_model": "...",

        # Agent配置扩展
        "agent_mode": "enabled",  # enabled/disabled
        "max_conversation_turns": 5,
        "max_questions_per_file": 3,
        "analysis_depth_preference": "adaptive",  # shallow/medium/deep/adaptive
        "enable_multi_agent": False,  # 多Agent模式
    },
    "review_config": {
        # 现有审查配置
        "review_severity_level": "standard",

        # Agent相关配置
        "agent_permissions": {
            "auto_approve_low_risk": False,
            "require_confirmation_threshold": 0.8,
            "enable_batch_operations": True
        }
    }
}
```

## 数据库设计扩展

### Agent会话表
```sql
CREATE TABLE agent_sessions (
    id VARCHAR(50) PRIMARY KEY,
    review_id VARCHAR(50),
    agent_type VARCHAR(50),  -- 'code_analyzer', 'security_analyzer', etc.
    file_path TEXT,
    state VARCHAR(20),       -- 当前Agent状态
    conversation_history JSON,
    analysis_result JSON,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (review_id) REFERENCES reviews(id)
);
```

### Agent评论表
```sql
CREATE TABLE agent_comments (
    id VARCHAR(50) PRIMARY KEY,
    session_id VARCHAR(50),
    file_path TEXT,
    line_number INTEGER,
    content TEXT,
    severity VARCHAR(20),
    category VARCHAR(50),
    confidence_score FLOAT,
    agent_reasoning TEXT,     -- Agent推理过程
    conversation_summary TEXT, -- 对话摘要
    status VARCHAR(20) DEFAULT 'pending',
    user_modified_content TEXT,
    created_at TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES agent_sessions(id)
);
```

## 接口设计

### Agent分析API
```python
# POST /api/agents/analyze
{
    "mr_url": "...",
    "analysis_options": {
        "depth": "adaptive",
        "agent_types": ["code_analyzer"],
        "max_turns": 5
    }
}

# GET /api/agents/status/{review_id}
{
    "status": "analyzing",
    "progress": 0.65,
    "active_agents": [
        {
            "agent_id": "agent_001",
            "file_path": "src/main.py",
            "state": "questioning",
            "current_turn": 3
        }
    ]
}
```

### 评论管理API
```python
# GET /api/comments/preview/{review_id}
{
    "total_comments": 15,
    "by_severity": {"error": 2, "warning": 8, "info": 5},
    "files": [
        {
            "file_path": "src/main.py",
            "comments": [...],
            "agent_info": {
                "analysis_depth": "deep",
                "confidence_score": 0.92
            }
        }
    ]
}
```

## 测试策略

### 单元测试
```
tests/
├── agents/
│   ├── test_code_analyzer.py
│   ├── test_conversation.py
│   └── test_orchestrator.py
├── permissions/
│   └── test_manager.py
└── integration/
    ├── test_agent_integration.py
    └── test_review_flow.py
```

### 集成测试
- Agent与GitLab API集成测试
- 多Agent协调测试
- 权限管理流程测试
- 用户界面交互测试

这样的模块组织设计确保了：
1. **清晰的职责分离**：每个模块有明确的职责边界
2. **可扩展性**：新功能可以独立开发和部署
3. **可测试性**：模块化设计便于单元测试和集成测试
4. **向后兼容**：保留现有接口，逐步迁移
5. **渐进实施**：可以分阶段实现，不影响现有功能