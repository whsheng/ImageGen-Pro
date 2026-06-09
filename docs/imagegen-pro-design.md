# ImageGen Pro — 图片生成服务 设计文档

> 版本：v0.1（图片生成优先，视频生成后续版本支持）  
> 日期：2026-06-07  
> 目标：自用 + 内部团队使用，提供 Web UI 与 OpenAI 兼容 API

---

## 一、项目背景

手上有多个 AI 厂商的 API Key（Gemini、Agens、Qwen、Wulin 等），均支持图片生成。目前调用分散，缺少统一入口，也无法高效管理多 Key 轮换和 Prompt 模板。

**ImageGen Pro 的目标**：提供一个统一的 Web 服务，统一管理多个模型的 API Key，稳定输出公司内部市场物料（产品图、场景图、社媒配图等），同时提供 OpenAI 兼容 API 供第三方工具集成。

---

## 二、核心需求

### 2.1 功能需求

| 功能 | 说明 | 优先级 |
|------|------|--------|
| 图片生成 | 调用配置的 AI 模型生成图片 | P0 |
| 多 Key 轮询 | 同一模型配置多个 Key，简单轮询调用 | P0 |
| Key 健康检查 | 自动检测 quota_exceeded / rate_limit，标记不可用；2天后自动重试；连续3次失败标记为「作废」 | P0 |
| OpenAI 兼容 API | `/v1/images/generations` 格式，方便第三方接入 | P0 |
| Prompt 模板库 | 保存常用 Prompt 模板，支持变量替换 | P1 |
| 生成历史记录 | 记录每次生成的 Prompt、参数、结果，支持重新生成 | P1 |
| Web UI | 简洁的上下分栏布局，支持中文 Prompt（自动翻译为英文） | P0 |
| 图片本地存储 | 生成图片存本地磁盘，返回本地文件路径 | P0 |
| 全局 API Key 认证 | 简单高效的 API 调用认证方式 | P0 |

### 2.2 非功能需求

| 需求 | 说明 |
|------|------|
| 部署方式 | 本地 MacBook 运行，通过 Cloudflare Tunnel 暴露到外网（VPS 做反向代理） |
| 目标用户 | 自用 + 内部团队，不需多租户、注册登录 |
| 可观测性 | 状态栏实时显示当前模型、当前 Key、今日生成次数、剩余配额 |
| 扩展性 | 视频生成作为后续版本，架构预留扩展点 |

---

## 三、Key 管理策略（核心设计）

### 3.1 多 Key 轮询

- 同一模型可配置多个 Key（如 Agens 有3个不同账号的 Key）
- 调用时按**简单轮询**顺序选取下一个可用 Key
- 只从状态为 `active` 的 Key 中选取

### 3.2 Key 状态机

```
active  ──[quota_exceeded / rate_limit]──>  cooling(冷却期，2天)
cooling ──[2天后重试成功]──> active
cooling ──[连续3次失败]──>  invalid(作废，需人工更换)
```

| 状态 | 说明 |
|------|------|
| `active` | 正常可用 |
| `cooling` | 临时禁用，2天后自动重试 |
| `invalid` | 已作废，需人工更换 Key |

### 3.3 配置文件格式（初期用 JSON/YAML，不用数据库）

```json
{
  "models": {
    "agens": {
      "display_name": "Agens Image",
      "api_base": "https://api.agens.ai/v1",
      "keys": [
        {
          "id": "agens-01",
          "key": "sk-xxx",
          "status": "active",
          "cooling_until": null,
          "consecutive_failures": 0,
          "last_used": "2026-06-07T16:00:00"
        },
        {
          "id": "agens-02",
          "key": "sk-yyy",
          "status": "active",
          "cooling_until": null,
          "consecutive_failures": 0,
          "last_used": null
        }
      ]
    },
    "gemini": {
      "display_name": "Gemini 2.0",
      "api_base": "https://generativelanguage.googleapis.com/v1beta",
      "keys": [
        {
          "id": "gemini-01",
          "key": "xxx",
          "status": "active",
          "cooling_until": null,
          "consecutive_failures": 0,
          "last_used": null
        }
      ]
    }
  }
}
```

---

## 四、技术架构

### 4.1 技术栈（推荐）

| 层 | 技术 | 理由 |
|----|------|------|
| 后端 | **Python 3.13 + FastAPI** | AI SDK 生态丰富，异步支持好 |
| 前端 | **原生 HTML + CSS + JS**（初期）或 **React**（后期） | 初期追求简单，后续可升级 |
| 存储 | **本地文件系统**（图片）+ **SQLite**（历史记录、模板） | 自用场景足够，无需独立数据库 |
| 部署 | **本地 MacBook 运行** + **Cloudflare Tunnel** 暴露服务 | 免费、稳定、无需管理服务器 |
| 进程管理 | **systemd**（Linux VPS 上跑 tunnel）+ **launchd**（macOS 本地服务） | 系统级进程守护 |

### 4.2 目录结构（建议）

```
image-gen-pro/
├── backend/
│   ├── main.py              # FastAPI 入口
│   ├── config.json          # Key 和模型配置
│   ├── app/
│   │   ├── routers/
│   │   │   ├── images.py   # 图片生成 API
│   │   │   ├── models.py   # 模型/Key 管理 API
│   │   │   └── admin.py    # 健康检查、统计 API
│   │   ├── services/
│   │   │   ├── generator.py    # 图片生成核心逻辑
│   │   │   ├── key_manager.py   # Key 轮询 + 健康检查
│   │   │   └── translator.py    # 中文 Prompt 翻译
│   │   └── db/
│   │       ├── sqlite_db.py     # SQLite 操作封装
│   │       ├── templates.py     # Prompt 模板 CRUD
│   │       └── history.py       # 生成历史 CRUD
│   └── static/
│       └── outputs/         # 生成图片存储目录
├── frontend/
│   ├── index.html           # 主页面（上下分栏布局）
│   ├── css/
│   │   └── style.css
│   └── js/
│       ├── app.js           # 主逻辑
│       └── api.js           # API 调用封装
├── cf-tunnel/              # Cloudflare Tunnel 配置
│   └── config.yml
└── requirements.txt
```

---

## 五、API 设计

### 5.1 OpenAI 兼容接口（供第三方集成）

```
POST /v1/images/generations
Header: Authorization: Bearer {全局_API_KEY}
```

请求体（与 OpenAI 完全一致）：

```json
{
  "model": "agens",
  "prompt": "A white D606 GPS tracker on a white background, product photography",
  "n": 1,
  "size": "1024x1024"
}
```

响应体（与 OpenAI 完全一致）：

```json
{
  "created": 1717765423,
  "data": [
    {
      "url": "http://your-domain.com/static/outputs/2026-06-07/abc123.png"
    }
  ]
}
```

### 5.2 管理接口（Web UI 使用）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/models` | 获取可用模型列表及 Key 状态 |
| POST | `/api/images/generate` | 生成图片（Web UI 专用，支持中文 Prompt） |
| GET | `/api/templates` | 获取 Prompt 模板列表 |
| POST | `/api/templates` | 新建 Prompt 模板 |
| GET | `/api/history` | 获取生成历史 |
| DELETE | `/api/history/{id}` | 删除历史记录 |
| GET | `/api/health` | 健康检查（各模型 Key 状态） |
| GET | `/api/stats` | 使用统计（今日生成次数、各 Key 配额等） |

---

## 六、Web UI 设计

### 6.1 整体布局（上下分栏）

```
┌─────────────────────────────────────────────┐
│  顶部状态栏：模型选择 | Key 状态指示灯 | 配额  │
├─────────────────────────────────────────────┤
│                                             │
│            Prompt 输入区（上半部）              │
│  ┌─────────────────────────────────────┐    │
│  │  输入图片描述...（支持中文）           │    │
│  └─────────────────────────────────────┘    │
│  生成数量: [1]     [生成图片]  [模板库] [历史] │
│                                             │
├─────────────────────────────────────────────┤
│                                             │
│          生成结果展示区（下半部）               │
│  ┌──────┐  ┌──────┐  ┌──────┐            │
│  │ 图1  │  │ 图2  │  │ 图3  │            │
│  └──────┘  └──────┘  └──────┘            │
│  [全部下载] [复制全部链接] [清空结果]          │
│                                             │
├─────────────────────────────────────────────┤
│  底部状态栏：当前模型 | 当前 Key | 今日生成次数  │
└─────────────────────────────────────────────┘
```

### 6.2 顶部状态栏

- **模型选择**：下拉选择当前使用的模型（Gemini 2.0 / Agens / Qwen / Wulin）
- **Key 状态指示灯**：● 绿色=正常，● 黄色=冷却中，● 红色=作废
- **配额显示**：显示当前 Key 的剩余配额百分比

### 6.3 Prompt 输入区

- 大文本输入框（支持多行）
- 中文 Prompt 自动翻译为英文（调用翻译 API 或内置模型）
- 生成数量选择（1~4）
- 「生成图片」主按钮
- 「模板库」按钮：展开面板，选择预设模板
- 「历史记录」按钮：展开面板，查看历史并一键重新生成

### 6.4 生成结果区

- 图片缩略图并排展示（最多4张）
- 每张图片支持：下载、复制链接、删除
- 批量操作：全部下载、复制全部链接、清空结果

### 6.5 模板库面板（展开式）

- 列表展示已保存的模板
- 每个模板显示：名称、描述、预览图
- 支持：新建、编辑、删除、一键使用
- 模板变量示例：`产品图：{产品名}，白色背景，高清`

### 6.6 历史记录面板（展开式）

- 按时间倒序展示历史生成记录
- 每条记录显示：Prompt、缩略图、生成时间、使用模型
- 支持：一键重新生成、删除记录

---

## 七、数据库设计（SQLite）

### 7.1 表：generation_history（生成历史）

```sql
CREATE TABLE generation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt TEXT NOT NULL,
    prompt_translated TEXT,
    model VARCHAR(50) NOT NULL,
    key_id VARCHAR(50),
    image_count INTEGER DEFAULT 1,
    image_paths TEXT,  -- JSON array of paths
    size VARCHAR(20),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 7.2 表：prompt_templates（Prompt 模板库）

```sql
CREATE TABLE prompt_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    template TEXT NOT NULL,  -- 支持 {变量} 格式
    category VARCHAR(50),    -- 产品图 / 场景图 / 社媒图 等
    preview_image_path TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 7.3 表：key_status（Key 状态追踪，可选，也可放在 config.json）

```sql
CREATE TABLE key_status (
    key_id VARCHAR(50) PRIMARY KEY,
    model VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    consecutive_failures INTEGER DEFAULT 0,
    cooling_until DATETIME,
    last_success_at DATETIME,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 八、部署方案

### 8.1 本地运行（macOS）

```bash
# 安装依赖
pip install -r requirements.txt

# 启动后端（默认 8000 端口）
python backend/main.py

# 前端直接打开
open frontend/index.html
# 或用地 Python 简单 HTTP 服务
python -m http.server 8080 --directory frontend
```

### 8.2 Cloudflare Tunnel 配置

```yaml
# cf-tunnel/config.yml
tunnel: <tunnel-id>
credentials-file: /path/to/credentials.json

ingress:
  - hostname: image-gen.your-domain.com
    service: http://localhost:8000
  - service: http_status:404
```

启动 tunnel：
```bash
cloudflared tunnel run
```

### 8.3 进程守护（macOS launchd）

创建 `~/Library/LaunchAgents/com.imagegen.pro.plist`，让服务开机自启。

---

## 九、实施顺序（建议）

| 阶段 | 内容 | 产出 |
|------|------|------|
| **Phase 1** | 后端核心：FastAPI + 单模型图片生成 + 简单 Key 轮询 | 可生成图片 |
| **Phase 2** | Key 健康检查完整逻辑（cooling + invalid 状态机） | Key 自动管理 |
| **Phase 3** | OpenAI 兼容 API 接口 | 第三方可接入 |
| **Phase 4** | Web UI 基础版（Prompt 输入 + 结果展示） | 可通过浏览器使用 |
| **Phase 5** | Prompt 模板库 + 生成历史 | 提升物料生产效率 |
| **Phase 6** | Cloudflare Tunnel 部署 | 外网可访问 |
| **Phase 7** | 中文 Prompt 自动翻译 | 提升使用体验 |
| **Phase 8** | 图片存储升级（Cloudflare R2 / AWS S3） | 支持外网图片链接 |
| **Phase 9** | 视频生成支持 | 完整产品 |

---

## 十、关键注意事项

1. **各模型 API 差异**：Gemini / Agens / Qwen / Wulin 的请求格式不完全一致，需要在 `generator.py` 里做适配器层
2. **图片下载**：AI 模型通常返回图片 URL 或 base64，需要统一处理为「下载并保存到本地」
3. **超时处理**：图片生成可能耗时 10~60 秒，需要设置合理超时（建议 120 秒）
4. **并发控制**：初期不做并发限制，后续可加简单信号量控制同时请求数
5. **错误处理**：所有 AI API 调用必须有 try/except，错误时自动切换下一个 Key

---

## 附录：参考资料

- OpenAI Images API 文档：https://platform.openai.com/docs/api-reference/images
- Gemini API 图片生成：https://ai.google.dev/docs/gemini_api
- Cloudflare Tunnel 文档：https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/
- FastAPI 异步文档：https://fastapi.tiangolo.com/
