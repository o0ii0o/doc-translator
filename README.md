# doc-translator

面向 **PDF 学术论文** 的英译中工具：通过 [MinerU](https://mineru.net) 云端 OCR/结构化解析，将论文转为 Markdown，再调用**你自己配置的大模型 API** 完成翻译。解析结果可缓存，重复调试翻译时无需反复付费解析——**省心、省钱**。

## 特性

- **PDF 智能解析**：调用 MinerU API，支持复杂排版、公式、表格，输出结构化 Markdown
- **灵活翻译后端**：兼容 OpenAI 接口（DeepSeek、OpenAI、本地代理等），在 `config.yaml` 中配置 `base_url` 与 `model` 即可
- **解析缓存**：同一 PDF 解析一次后本地复用，跳过后续 MinerU 调用
- **长文分段 + 并发翻译**：按章节/长度自动切分，多线程并发（推荐 `max_concurrency: 3`）
- **日志完善**：控制台 + 滚动文件日志，便于排查进度与耗时

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
```

也可在 `config.yaml` 中用 `${MINERU_API_KEY}`、`${DEEPSEEK_API_KEY}` 引用环境变量，**请勿将密钥写入代码或提交到 Git**。

### 运行

```bash
# 翻译 PDF 论文（输出 tests/2009.06732v3_zh.md）
python main.py tests/2009.06732v3.pdf

# 指定输出路径
python main.py tests/paper.pdf -o output/paper_zh.md

# 强制重新解析 PDF（忽略缓存）
python main.py tests/paper.pdf --no-cache

# 调试模式（DEBUG 日志）
python main.py tests/paper.pdf -v
```

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

使用其他厂商时，保持 `provider: openai`，修改 `base_url` 与 `model` 即可对接兼容 OpenAI 格式的服务。

## 命令行参数

| 参数 | 说明 |
|------|------|
| `input_file` | 输入文件（`.pdf` / `.md`） |
| `-o, --output` | 输出路径（默认 `{原名}_zh.md`） |
| `-c, --config` | 配置文件路径（默认 `config.yaml`） |
| `-v, --verbose` | DEBUG 日志 |
| `--no-cache` | 禁用解析缓存 |
| `--no-log-file` | 仅输出到控制台 |

## 项目结构

```
doc-translator/
├── main.py              # 入口
├── config.yaml          # 配置
├── requirements.txt
├── src/
│   ├── file_handler.py  # 文件路由
│   ├── pdf_parser.py    # PDF → MinerU API
│   ├── parse_cache.py   # 解析缓存
│   ├── translator.py    # LLM 翻译
│   └── ...
├── tests/               # 测试样例
├── .cache/parse/        # 解析缓存（自动生成）
└── logs/                # 运行日志
```

## 省钱小贴士

1. **解析缓存**：同一篇论文反复调翻译参数时，第二次起只走翻译，不再调用 MinerU。
2. **选用高性价比模型**：如 DeepSeek v4-flash，翻译质量与成本较均衡。
3. **并发不宜过高**：`max_concurrency: 3` 在实测中比 6 更稳、总耗时更短。

## 许可

按仓库实际情况补充许可证信息。
