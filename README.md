# ImageGen Pro

按 `ImageGen-Pro-设计文档.md` 落地的首版实现，包含：

- FastAPI 后端
- OpenAI 兼容图片生成接口 `/v1/images/generations`
- 多模型 / 多 Key 轮询与冷却状态管理
- SQLite 模板库与生成历史
- 本地图片落盘
- 原生 HTML/CSS/JS 管理界面

## 目录

```text
backend/      FastAPI、SQLite、图片输出
frontend/     静态管理界面
cf-tunnel/    Cloudflare Tunnel 样例配置
launchd/      macOS launchd 样例配置
tests/        基础接口与状态机测试
```

## 快速启动

1. 创建本地虚拟环境并安装依赖：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

2. 准备本地配置：

```bash
cp backend/config.providers.example.json backend/config.local.json
```

- 仓库内的 [backend/config.json](/lzcapp/document/01-Work/02-Project/03-Works/imagegen-pro/backend/config.json) 现在是可提交的安全兜底配置，只用于本地 demo / mock 流程
- 实际可用的模型 key、代理 base URL、全局访问口令，请写在 `backend/config.local.json`
- 启动时配置优先级为：`IMAGEGEN_CONFIG_PATH` > `backend/config.local.json` > `backend/config.json`
- `backend/config.local.json` 已加入 `.gitignore`，适合每台机器本地单独填写
- 真实 provider 的字段写法可参考 [backend/config.providers.example.json](/lzcapp/document/01-Work/02-Project/03-Works/imagegen-pro/backend/config.providers.example.json)
- 当前项目已按文档接入 `OpenAI`、`Agens`、`Qwen`、`WuLi`
- `Gemini` 请求结构已修正为当前 `generateContent + generationConfig.imageConfig` 形式，但真实出图仍需要有额度和计费权限的 key
- 如需中文自动翻译，额外配置 `translation`

上线前建议：

- 不要保留默认的 `change-me`
- 优先用 `IMAGEGEN_GLOBAL_API_KEY` 注入全局访问口令
- 不要把 `backend/config.local.json`、`keys.txt` 或任何真实 provider key 推到远程仓库

3. 启动服务：

```bash
.venv/bin/python backend/main.py
```

也可显式指定全局访问口令：

```bash
IMAGEGEN_GLOBAL_API_KEY="your-strong-api-key" .venv/bin/python backend/main.py
```

4. 使用方式：

- Web UI: `http://127.0.0.1:8000/ui` 或 `http://localhost:8000/ui`
- Web UI 首次打开后，在顶部输入全局 API Key，默认样例值为 `change-me`
- 不要用 `http://0.0.0.1:8000`，这个地址不用于浏览器访问
- 通过 FastAPI 挂载的 `/ui` 访问时，前端会自动使用当前站点作为 API 地址
- 如果前端不是通过 FastAPI 的 `/ui` 挂载访问，而是单独打开 `frontend/index.html` 或用 `python -m http.server` 启动，请把顶部的 `API 地址` 设为后端地址，例如 `http://localhost:8000`
- 管理接口: `http://localhost:8000/api/*`
- OpenAI 兼容接口: `http://localhost:8000/v1/images/generations`

## 本地验证

1. 先验证后端是否读到了你期望的配置文件：

```bash
curl -H "X-API-Key: your-global-api-key" http://127.0.0.1:8000/api/health
```

返回里会带 `config_path`。

2. 再验证模型列表：

```bash
curl -H "X-API-Key: your-global-api-key" http://127.0.0.1:8000/api/models
```

3. 如果只想验证项目主流程，不想真实调用外部厂商，可强制使用仓库内安全 mock 配置：

```bash
IMAGEGEN_CONFIG_PATH=backend/config.json .venv/bin/python backend/main.py
```

4. 项目内置了一条经由 `/v1/images/generations` 的烟测脚本：

```bash
.venv/bin/python scripts/project_provider_smoke.py --models agens --config-path backend/config.json
```

## macOS launchd

设计文档要求本地 macOS 用 `launchd` 守护，样例文件已放在 [launchd/com.imagegen.pro.plist](/lzcapp/document/01-Work/02-Project/03-Works/imagegen-pro/launchd/com.imagegen.pro.plist)。

使用前需要把其中两个占位路径改成你机器上的绝对路径：

- `/ABSOLUTE/PATH/TO/imagegen-pro`
- `/ABSOLUTE/PATH/TO/imagegen-pro/backend/main.py`

## Cloudflare Tunnel

- Tunnel 配置样例见 [cf-tunnel/config.yml](/lzcapp/document/01-Work/02-Project/03-Works/imagegen-pro/cf-tunnel/config.yml)
- 如果你要在 Linux VPS 上用 `systemd` 守护 `cloudflared`，可参考 [cf-tunnel/cloudflared-imagegen.service](/lzcapp/document/01-Work/02-Project/03-Works/imagegen-pro/cf-tunnel/cloudflared-imagegen.service)
- 样例 service 默认使用 `/etc/cloudflared/imagegen-pro.yml`，以及 `/usr/local/bin/cloudflared`，上线前需要改成你机器上的实际路径

## 说明

- 当前默认配置使用 `mock` provider，便于本地验证流程，不依赖外部模型服务。
- 当前机器若存在 `backend/config.local.json`，服务会优先读取它；这可以避免把真实 key 放进仓库。
- 如果启动时看到 `WARNING: global_api_key is still 'change-me'`，说明服务仍在使用默认全局口令，不适合直接暴露到外网。
- `openai_compatible` provider 支持对接返回 `url` 或 `b64_json` 的图片接口，并支持 `bearer/header/query` 三种认证模式。
- 如果厂商接口会返回剩余配额，可通过 `provider_options.quota_remaining_percent_header` 或 `provider_options.quota_remaining_percent_json_path` 把它映射为 `0-100` 的百分比；若接口返回的是 `0-1` 小数，可再配 `quota_remaining_percent_multiplier: 100`
- `gemini_native` provider 已实现 Gemini 原生 `generateContent` 图片生成调用，请求会使用 `generationConfig.imageConfig`，并自动把 `1024x1024` 这类尺寸映射到 Gemini 所需的 `aspectRatio`；Gemini 3.x/2.5 图像模型还会额外映射 `imageSize`。
- `Agens` 已按官方说明作为 `openai_compatible` 接入，默认目标是 `https://apihub.agnes-ai.com/v1/images/generations`
- `qwen_native` 已按阿里云百炼 `multimodal-generation` 文档实现，请求会发到 `https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation`
- `WuLi` 已按开放平台 `submit -> query` 异步任务流程实现 native adapter，请求会发到 `https://platform.wuli.art/api/v1/platform`
# ImageGen-Pro
