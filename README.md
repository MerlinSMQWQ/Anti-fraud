# 识诈 (Anti-Fraud Explorer)

面向反诈宣传、案例检索与科普提醒的本地 Web 智能体。

## 功能

- **案例检索** — 86 个反诈案例，14 个类别（刷单返利、冒充领导熟人、虚假投资理财等），支持关键词、拼音、语义搜索
- **智能问答** — AI 模型驱动的反诈知识问答
- **场景匹配** — 根据宣讲场景（校园/社区/企业/老年）推荐合适案例
- **内容转化** — 自动生成宣讲方案、学习任务、双语传播文案
- **语音播报** — 火山引擎 TTS 语音合成

## 快速开始

### 环境要求

- Python >= 3.10
- Windows / Linux / macOS

### 安装

```bash
git clone <repo-url>
cd 反诈
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows
pip install -e ".[dev]"
```

### 配置

复制 `.env.example` 为 `.env`，填入 API 密钥：

```bash
cp .env.example .env
```

必填项：
- `AI_API_KEY` — DeepSeek / OpenAI 兼容 API 密钥
- `AI_BASE_URL` — API 端点（默认 `https://api.deepseek.com`）
- `AI_MODEL` — 模型名（默认 `deepseek-v4-flash`）

可选：
- `EMBEDDING_API_KEY` — 向量嵌入 API 密钥（启用语义搜索时需要）
- `VOLC_TTS_*` — 火山引擎 TTS 配置（启用语音合成时需要）

### 准备数据

项目已包含预处理后的数据 `data/processed/case_items.json`。
如需从原始数据重建：

```bash
python scripts/build_dataset.py
```

### 构建嵌入索引（可选）

```bash
# Linux/macOS
scripts/maintenance/rebuild_embedding_index.sh

# Windows PowerShell
scripts/maintenance/rebuild_embedding_index.ps1

# 或直接 Python
python scripts/maintenance/rebuild_embedding_index.py
```

### 运行

```bash
python app.py
```

打开 http://127.0.0.1:5070

## 项目结构

```
反诈/
├── app.py                       # 应用入口
├── pyproject.toml               # 项目元数据与依赖
├── src/anti_fraud_explorer/     # 核心代码
│   ├── config.py                # 配置（pydantic-settings）
│   ├── web.py                   # Flask Web 应用
│   ├── agent/                   # AI Agent 调度
│   ├── ai/                      # LLM 调用与语音
│   └── dataset.py               # 数据加载
├── data/
│   ├── raw/dataset.json         # 原始案例数据（86条）
│   └── processed/               # 预处理后的数据
├── templates/                   # Jinja2 模板
├── static/                      # 静态资源（CSS/JS/媒体）
├── tests/                       # 测试
└── docs/                        # 文档
```

## 测试

```bash
pytest tests/ -v
```

## 文档

- [数据采集与标注规范](docs/反诈数据采集与标注规范_简洁专业版_v1.2.docx)

## License

内部项目。
