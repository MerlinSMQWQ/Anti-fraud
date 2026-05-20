# 识诈 (Anti-Fraud Explorer)

面向反诈宣传、案例检索、问答讲解与内容转化的本地 Web 智能体。

## 功能概览

- 案例检索：内置 86 条反诈案例，基于 `data/processed/case_items.json` 提供关键词、拼音和可选的向量检索
- 智能问答：围绕案例库做依据式回答，不命中时会明确说明资料边界
- 场景推荐：按校园、社区、企业、老年等宣讲场景筛选更合适的案例
- 内容转化：生成讲解词、学习任务、展示方案、提醒文案等
- 语音播报：支持服务端 TTS 与浏览器语音回退

## 环境要求

- Python `>= 3.14`
- Windows / Linux / macOS
- 建议终端使用 UTF-8，尤其是在包含中文路径的 Windows 环境里

## 快速开始

### 1. 创建虚拟环境

Windows PowerShell:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Linux / macOS:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`：

```powershell
Copy-Item .env.example .env
```

```bash
cp .env.example .env
```

核心配置：

- `AI_API_KEY`：问答与内容生成模型密钥
- `AI_BASE_URL`：兼容 OpenAI 的接口地址，默认 `https://api.deepseek.com`
- `AI_MODEL`：模型名，默认 `deepseek-v4-flash`

可选配置：

- `EMBEDDING_API_KEY`：启用语义检索时需要
- `SEARCH_USE_EMBEDDING`：设为真后启用混合检索
- `VOLC_TTS_*`：启用火山引擎 TTS 时需要
- `DATASET_PATH`：自定义数据文件路径，默认 `data/processed/case_items.json`

### 3. 准备数据

仓库已包含可直接运行的规范化数据：

- `data/processed/case_items.json`

如果你需要从原始案例重新生成当前数据集，请运行：

```powershell
python .\scripts\process_raw_data.py
```

```bash
python scripts/process_raw_data.py
```

原始数据默认来自：

- `data/raw/dataset.json`

### 4. 构建嵌入索引（可选）

如果要启用语义检索，先准备好嵌入 API 配置，再执行：

```powershell
python .\scripts\maintenance\rebuild_embedding_index.py
```

```bash
python scripts/maintenance/rebuild_embedding_index.py
```

生成结果默认写入：

- `data/embeddings/case_embeddings.json`

### 5. 启动服务

```powershell
python .\app.py
```

```bash
python app.py
```

默认地址：

- [http://127.0.0.1:5070](http://127.0.0.1:5070)

## 当前数据结构

项目当前使用的是规范化后的案例结构（`schema_version: 4`），核心字段包括：

- `case_id`
- `title`
- `summary`
- `ccl2023_category`
- `custom_subcategory`
- `risk_level`
- `entry_channels`
- `impersonated_identity`
- `key_methods`
- `risk_signals`
- `prevention_advice`
- `source_name`
- `victim_group`

说明：

- 现在的数据模型直接匹配 `case_items.json`
- 多值字段统一使用 JSON 数组，例如 `entry_channels`、`impersonated_identity`、`key_methods`、`tags`
- 旧版兼容字段如 `family`、`level`、`history`、`province`、`city`、`district` 已移除
- 地区字段不再作为结构化数据存储，相关检索逻辑会按当前 schema 处理

## 常用命令

运行测试：

```powershell
python -m pytest -q
```

```bash
python -m pytest -q
```

静态检查：

```powershell
python -m ruff check .
```

```bash
python -m ruff check .
```

## 项目结构

```text
反诈/
├── app.py
├── pyproject.toml
├── data/
│   ├── raw/
│   │   └── dataset.json
│   ├── processed/
│   │   └── case_items.json
│   └── embeddings/
│       └── case_embeddings.json
├── scripts/
│   ├── process_raw_data.py
│   └── maintenance/
│       └── rebuild_embedding_index.py
├── src/
│   └── anti_fraud_explorer/
│       ├── agent/
│       ├── ai/
│       ├── domain/
│       │   └── dataset.py
│       ├── service/
│       ├── web/
│       ├── config.py
│       └── prompts.py
├── static/
├── templates/
├── tests/
└── docs/
```

## 文档

- [数据采集与标注规范](docs/反诈数据采集与标注规范_简洁专业版_v1.2.docx)

## License

内部项目。
