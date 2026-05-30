# doc-translator

面向 **PDF 学术论文** 的英译中工具：通过 [MinerU](https://mineru.net) 云端 OCR/结构化解析，将论文转为 Markdown，再调用**你自己配置的大模型 API** 完成翻译。解析结果可缓存，重复调试翻译时无需反复付费解析——**省心、省钱**。

## 特性

- **PDF 智能解析**：调用 MinerU API，支持复杂排版、公式、表格，输出结构化 Markdown
- **灵活翻译后端**：兼容 OpenAI 接口（DeepSeek、OpenAI、本地代理等），在 `config.yaml` 中配置 `base_url` 与 `model` 即可
- **解析缓存**：同一 PDF 解析一次后本地复用，跳过后续 MinerU 调用
- **长文分段 + 并发翻译**：按章节/长度自动切分，多线程并发（推荐 `max_concurrency: 3`）
- **日志完善**：控制台 + 滚动文件日志，便于排查进度与耗时
- **RAG 知识库入库**：层次切片（Section + Leaf）+ SQLite 存储 + OpenAI 兼容 Embedding（Chroma）

## 工作流程

```
PDF / Markdown
      ↓
  文件类型检测
      ↓
 PDF ──→ MinerU API 解析 ──→ Markdown（可缓存）
 MD  ──→ 直接读取 ─────────→ Markdown
      ↓
  分段 + LLM 翻译（可配置 API）
      ↓
  {文件名}_zh.md
```

## 快速开始

### 环境要求

- Python 3.9+
- [MinerU API Token](https://mineru.net/user-center/api-token)（PDF 解析）
- 大模型 API Key（如 [DeepSeek](https://platform.deepseek.com)）
- 向量化：默认 **本地 BGE-M3**（无需 API Key）；或 OpenAI 兼容 Embedding API

### 安装

```bash
git clone <your-repo-url>
cd doc-translator
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate   # Linux / macOS
pip install -r requirements.txt
```

### 配置环境变量

PowerShell 示例：

```powershell
$env:MINERU_API_KEY = "你的_MinerU_Token"
$env:DEEPSEEK_API_KEY = "sk-你的_DeepSeek_Key"
# 仅 index.embedding.provider=openai 时需要：
# $env:OPENAI_API_KEY = "sk-你的_OpenAI_Key"
```

也可在 `config.yaml` 中用 `${MINERU_API_KEY}`、`${DEEPSEEK_API_KEY}` 等引用环境变量，**请勿将密钥写入代码或提交到 Git**。

**Embedding 默认本地 `BAAI/bge-m3`**：首次 `index` 会从 Hugging Face 下载模型；需 `pip install FlagEmbedding`。改用云端时在 `config.yaml` 设 `index.embedding.provider: openai`。

### 运行

#### 翻译（默认命令，兼容旧用法）

```bash
# 以下两种写法等价
python main.py tests/2009.06732v3.pdf
python main.py translate tests/2009.06732v3.pdf -o output/paper_zh.md

# 强制重新解析 PDF（忽略缓存）
python main.py translate tests/paper.pdf --no-cache -v
```

#### 知识库入库（RAG 阶段一）

```bash
# 解析 + 层次切片 + 写入 SQLite（不翻译）
python main.py ingest tests/2009.06732v3.pdf

# 入库后立即向量化（默认本地 BGE-M3，无需 API Key）
python main.py ingest tests/paper.pdf --index

# 对已入库文档做 embedding
python main.py index --doc-id <doc_id>
python main.py index --all

# 强制重新切片 / 重新向量化
python main.py ingest tests/paper.pdf --force
python main.py index --doc-id <doc_id> --force
```

入库成功后终端会打印 `doc_id`；数据位于 `data/doc_translator.db` 与 `data/vector/`。

#### 单文档问答（RAG 阶段二，默认中文）

```bash
# 需已完成 index，且配置 DEEPSEEK_API_KEY（复用 llm 配置）
python main.py query "这篇论文的主要贡献是什么？" --doc-id <doc_id>

# 不显示参考来源
python main.py query "Transformer 有哪些效率优化方法？" --doc-id <doc_id> --no-sources
```

检索在指定 `doc_id` 内进行；回答使用 **简体中文**（`query.answer_lang: zh`）。

## 配置说明

编辑项目根目录 `config.yaml`：

| 配置项 | 说明 |
|--------|------|
| `llm.model` | 翻译模型，如 `deepseek-v4-flash` |
| `llm.base_url` | API 地址，如 `https://api.deepseek.com` |
| `mineru.model` | 解析模型，`vlm`（高精度）或 `pipeline` |
| `cache.enabled` | 是否启用 PDF 解析缓存 |
| `translation.batch_size` | 单段最大字符数（默认 4000） |
| `translation.max_concurrency` | 翻译并发数，建议 **3**（过高可能变慢） |
| `index.leaf_target_size` | RAG 叶子块目标字符数（默认 700） |
| `index.section_heading_levels` | 开新 section 的标题级别（默认 `#`、`##`） |
| `index.embedding.provider` | `bge_m3`（本地，默认）或 `openai`（云端 API） |
| `index.embedding.model` | 如 `BAAI/bge-m3` 或 `text-embedding-3-small` |
| `index.embedding.use_fp16` | BGE-M3 是否用半精度（有 GPU 时建议 true） |
| `query.top_k` | 检索返回的 leaf 数量（默认 6） |
| `query.use_parent_context` | 是否附带父 section 上下文（建议 true） |
| `query.max_context_chars` | 送入 LLM 的上下文上限（默认 8000 字） |
| `query.answer_lang` | 回答语言，默认 `zh`（中文） |

使用其他厂商时，保持 `provider: openai`，修改 `base_url` 与 `model` 即可对接兼容 OpenAI 格式的服务。

## 命令行参数

子命令：`translate`（默认）、`ingest`、`index`、`query`。全局选项：`-c`、`-v`、`--log-file`、`--no-log-file`。

| 子命令 | 主要参数 |
|--------|----------|
| `translate <file>` | `-o` 输出路径；`--no-cache` 禁用解析缓存 |
| `ingest <file>` | `--force` 强制重新入库；`--index` 入库后向量化；`--no-cache` |
| `index` | `--doc-id` 指定文档；`--all` 处理全部 `chunked`；`--force` 重新向量化 |
| `query <问题>` | **`--doc-id` 必填**；`--no-sources` 隐藏来源列表 |

## 项目结构

```
doc-translator/
├── main.py                    # CLI 入口
├── config.yaml
├── requirements.txt
├── src/
│   ├── core/models/           # Chunk 等数据模型
│   ├── infra/                 # 配置、日志
│   ├── parser/                # PDF/MD 解析（MinerU API）
│   ├── chunking/              # 翻译切分 + 层次切片（HierarchicalChunker）
│   ├── translator/            # LLM 翻译
│   ├── storage/               # 解析缓存、SQLite、Chroma
│   ├── pipeline/              # translate / ingest / index / query
│   ├── io/                    # 文件输出
│   └── rag/                   # embedding / retrieval / answer
├── data/                      # 知识库（db、向量、parsed 快照，gitignore）
├── .cache/parse/              # MinerU 解析缓存（自动生成）
└── logs/                      # 运行日志
```

## 省钱小贴士

1. **解析缓存**：同一篇论文反复调翻译参数时，第二次起只走翻译，不再调用 MinerU。
2. **选用高性价比模型**：如 DeepSeek v4-flash，翻译质量与成本较均衡。
3. **并发不宜过高**：`max_concurrency: 3` 在实测中比 6 更稳、总耗时更短。
4. **知识库与翻译分离**：`ingest` 只索引原文语言，不调用翻译 API；向量化单独 `index`，便于调试切片参数。

## 许可

按仓库实际情况补充许可证信息。
