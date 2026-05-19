# 识诈

识诈是一个面向反诈宣传、案例检索和科普提醒的本地 Web 智能体。它围绕反诈案例资料库组织搜索优先、多轮追问、Markdown 回答和数字人播报这套交互框架。

当前版本适合做三类事情：

- 查询某类骗局的常见套路、风险信号和防范建议
- 从案例库里筛选适合校园宣讲、社区宣传、老年防骗或企业培训的案例
- 把案例整理成口播稿、提醒文案、班会提纲或简单对照表

## 项目结构

```text
反诈/
├── app.py
├── dataset.json                        # 原始案例库
├── data/
│   ├── processed/
│   │   ├── case_items.json             # 归一化后的主数据集
│   │   └── ai_fields.json              # 展示补充字段
│   └── embeddings/
│       └── case_embeddings.json        # 本地 embedding 索引，按需生成
├── scripts/
│   ├── build_dataset.py                # 数据集改动后先运行它
│   └── maintenance/
│       ├── rebuild_embedding_index.py  # 向量索引重建脚本
│       └── rebuild_embedding_index.ps1
├── src/anti_fraud_explorer/
├── static/
└── templates/
```

## 快速开始

### 1. 安装依赖

```powershell
cd D:\Projects\反诈
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 2. 构建归一化数据

只要 `dataset.json` 有变化，就先运行：

```powershell
python .\scripts\build_dataset.py
```

它会生成：

- `data/processed/case_items.json`
- `data/processed/ai_fields.json`

这一步是必须的。Web 服务和检索逻辑都读这两个处理后的文件，不直接读原始 `dataset.json`。

### 3. 创建本地配置

```powershell
copy .env.example .env
```

默认不填 AI Key 也能打开页面、检索案例。需要大模型问答时，再补：

```env
AI_BASE_URL=https://api.deepseek.com
AI_MODEL=deepseek-v4-flash
AI_API_KEY=你的密钥
```

### 4. 启动服务

```powershell
python .\app.py
```

默认地址：

```text
http://127.0.0.1:5070
```

## 向量检索

项目支持可选 embedding 混合检索。

先在 `.env` 中配置：

```env
SEARCH_USE_EMBEDDING=1
EMBEDDING_BASE_URL=https://api.vectorengine.ai/v1
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_API_KEY=你的密钥
```

然后重建索引：

```powershell
python .\scripts\maintenance\rebuild_embedding_index.py --no-resume
```

或者：

```powershell
.\scripts\maintenance\rebuild_embedding_index.ps1 -NoResume
```

## 什么时候需要重建

### 只改了前端、提示词、接口逻辑

不用重建数据，也不用重建向量索引。

### 改了 `dataset.json`

先运行：

```powershell
python .\scripts\build_dataset.py
```

如果启用了向量检索，再继续运行：

```powershell
python .\scripts\maintenance\rebuild_embedding_index.py --no-resume
```

可以简单理解成两步：

1. `build_dataset.py` 负责把原始案例整理成系统能读的标准结构
2. `rebuild_embedding_index.py` 负责给标准结构重新生成向量索引

## 默认能力

- 右侧案例检索：按关键词和分类浏览案例
- 搜索优先问答：先召回候选案例，再交给模型决定是否继续精查
- 最近五轮上下文：支持“它”“这个骗局”“再加一个同类案例”这类追问
- 动态分类标签：从数据集自动读取，而不是写死在前端
- Markdown 回答：列表、表格、分段内容直接渲染
- 数字人状态切换：待机、思考、播报

## 主要环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | 服务监听地址 |
| `PORT` | `5070` | Web 端口 |
| `DATASET_PATH` | `data/processed/case_items.json` | 主数据集 |
| `EMBEDDING_INDEX_PATH` | `data/embeddings/case_embeddings.json` | 向量索引 |
| `SEARCH_USE_EMBEDDING` | `0` | 是否启用向量检索 |
| `AI_BASE_URL` | `https://api.deepseek.com` | OpenAI 兼容接口 |
| `AI_MODEL` | `deepseek-v4-flash` | 聊天模型 |
| `AI_API_KEY` | 空 | 大模型密钥 |

## Git 约定

这是一个单独的新仓库目录。比赛相关文档建议单独放在本地文件夹里，并继续保持不提交。

当前 `.gitignore` 已忽略：

- `.env`
- `data/embeddings/`
- `competition_docs/`
- 常见缓存和临时文件

## 下一步建议

如果我们继续把它做成竞赛作品，优先级建议是：

1. 把左侧数字人角色文案继续打磨成更稳定的反诈宣教语气
2. 设计更贴近反诈场景的专题任务模板，比如：
   - 校园宣讲
   - 老年防骗提醒
   - 社区宣传栏
   - 企业财务培训
