# Auto Garment Producer (Web)

从主题图自动生成商业成衣裁片的 Web 服务。原 CLI Skill 的完整功能移植到 FastAPI + Python 流水线。

## 架构

- **FastAPI**: Web API + 前端静态页面托管
- **BackgroundTasks**: 异步处理流水线（无需 Redis）
- **Python 直接调用 LLM / Neo AI**: 流程固化，单次 Vision LLM 调用 + Python 规则引擎
- **Pillow**: 确定性裁片渲染（完整保留原有逻辑）

## 功能保留

| 原 CLI 功能 | Web 版状态 |
|---|---|
| 主题图解析（多格式/URL/base64） | ✅ 保留 |
| 视觉分析（visual_elements.json） | ✅ 保留完整 schema，LLM 单次调用 |
| 设计简报（texture_prompts.json） | ✅ 保留，Python 规则引擎生成 |
| Neo AI 单纹理生成（main/secondary/accent_light） | ✅ 保留，Python 直接调用 API |
| 透明主图生成（hero_motif） | ✅ 保留 |
| 主题前片切半（theme_front_full/left/right） | ✅ 保留完整逻辑 |
| 裁片填充计划（规则引擎 + 对称约束 + 成对相位） | ✅ 保留完整逻辑 |
| 左右前片跨中缝对齐渲染 | ✅ 保留完整逻辑 |
| 3 套单纹理变体渲染 | ✅ 保留 |
| 预览图（透明底 + 白底） | ✅ 保留 |
| 缓存与复用机制 | ⏸️ 暂不实现（可后续添加） |

## 快速开始

### 1. 安装依赖

```bash
cd auto-garment-web
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY 和 NEO_AI_ACCESS_TOKEN
```

### 3. 启动服务

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

访问 http://localhost:8000/ 打开前端页面。

## API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/tasks` | 创建任务（上传主题图） |
| GET | `/api/v1/tasks/{task_id}` | 查询任务状态 |
| GET | `/api/v1/tasks/{task_id}/preview` | 预览图（PNG） |
| GET | `/api/v1/tasks/{task_id}/preview_white` | 白底预览图（JPG） |
| GET | `/api/v1/tasks/{task_id}/pieces/{piece_id}` | 单裁片 PNG |
| GET | `/api/v1/tasks/{task_id}/summary` | 结果摘要 JSON |
| GET | `/api/v1/tasks/{task_id}/download` | 下载全部结果 ZIP |

## 项目结构

```
auto-garment-web/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 配置管理
│   ├── api/
│   │   ├── tasks.py         # 任务 API
│   │   └── results.py       # 结果下载 API
│   ├── core/
│   │   ├── pipeline.py      # 固化流水线（6 阶段）
│   │   ├── prompt_blocks.py # 提示词模板（完整保留）
│   │   ├── neo_ai_client.py # Neo AI HTTP API 封装
│   │   ├── renderer.py      # Pillow 渲染核心（完整保留）
│   │   └── image_utils.py   # 图像工具
│   ├── services/
│   │   ├── vision_service.py     # 视觉分析（单次 LLM）
│   │   ├── prompt_engine.py      # 提示词生成（完整保留）
│   │   ├── fill_plan_service.py  # 填充计划（完整保留）
│   │   ├── front_split_service.py # 前片切半（完整保留）
│   │   └── template_service.py   # 模板加载
│   ├── models/
│   │   └── schemas.py       # Pydantic 模型
│   └── templates_data/      # 服装模板资产
├── frontend/
│   └── index.html           # 单页前端
├── storage/                 # 运行时产物（gitignore）
├── requirements.txt
└── .env.example
```

## 流水线阶段

```
pending → analyzing (视觉分析 + 提示词生成)
      → generating (hero 主图 + 3 textures 并行生成)
      → rendering (填充计划 + 3 套变体渲染)
      → completed
```

## 技术说明

### 为什么去掉 LLM 的思考过程？

原 CLI 流程中，LLM 需要执行"视觉分析 → 自检 → 重写 → 设计简报"等多轮思考。Web 版将其固化为：

1. **单次 Vision LLM 调用**: 上传图片 + 固定完整 prompt，LLM 直接返回完整的 `visual_elements.json`
2. **Python 规则引擎**: 使用 `prompt_blocks.py` 中的固化模板，自动注入 family_contract、micro_structure、palette_constraints 等

这样 LLM 只做"从图片提取视觉信息"这一件事，所有工程化组装由 Python 完成，响应更快更稳定。

### 为什么不使用 Redis/Celery？

当前版本使用 FastAPI `BackgroundTasks` 处理异步流水线。对于单节点部署足够使用。
当需要分布式扩展时，可以：
1. 启用 `worker/celery_app.py`
2. 将 `pipeline.py` 中的 `run_pipeline` 改为 Celery task
3. 任务状态从文件系统迁移到 Redis
# auto-garment-web
