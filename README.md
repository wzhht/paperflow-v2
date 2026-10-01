# PaperFlow V2

**中文** | [English](README_EN.md)

PaperFlow V2 是一个面向学术论文的本地处理流水线：根据 DOI 选择出版社路线，优先获取结构化全文；必要时使用合法获得的 PDF，通过外部 MinerU 解析；最后输出适合后续 LLM 阅读、检索和分析的 Markdown，并执行保守的科学内容 QA。

本项目的设计目标不是“把 Markdown 变漂亮”，而是尽量保证：

- 正文不被误删；
- 表格及表格中的数值不被静默改写；
- References 保留；
- 图片本体不进入最终 Markdown；
- 独立展示公式可以移除，但正文中的科学符号和行内量应尽量保留；
- 无法获得完整全文时明确标记为 partial / restricted，不猜测、不补写缺失内容。

> PaperFlow V2 不是通用 DOI 下载器，也不会绕过付费墙或访问控制。所有 PDF 和受限内容都应由用户通过合法方式获得。

---

## 1. 当前支持范围

### Elsevier / ScienceDirect

支持 DOI：

```text
10.1016/...
```

典型路线：

```text
DOI
→ Elsevier Article Retrieval XML
→ 结构化全文完整性检查
→ Markdown
→ 保守清理
→ QA
```

典型 source：

```text
elsevier_xml
```

特点：

- 优先使用出版社结构化 XML，而不是 PDF OCR；
- 保留正文、References 和结构化表格；
- 对表格数字进行保守处理；
- 删除最终 Markdown 中不需要的图片内容；
- 删除独立 display equations；
- 尽量保留行内科学量，例如 `SHGC`、`WWR`、`ACH`、`R²`、`CV(RMSE)`、`NMBE`、`kWh/m²`、`W/m²K`、`°C`、`%`；
- Elsevier 如果某个“表格”实际上只有出版社提供的图片而没有结构化单元格，PaperFlow 不会伪造表格内容，而是保留可用输出并给出 warning。

---

### Building Simulation

支持 DOI：

```text
10.1007/s12273...
```

这一路线主要是 PDF → MinerU。

优先级大致为：

```text
显式 --pdf
→ DOI 输出目录中唯一的本地 PDF
→ 可公开获取的 Springer 主文 PDF
→ 无完整 PDF 时的受限/部分信息恢复
```

PDF 路线：

```text
PDF
→ 基础 PDF 校验
→ 外部 MinerU Advanced
→ structured_content.json
→ PaperFlow renderer
→ QA
```

典型 source：

```text
building_simulation_pdf_mineru
local_pdf_mineru
```

---

### Nature Portfolio

支持 DOI：

```text
10.1038/...
```

优先级：

```text
显式 --pdf
→ Springer Nature Open Access JATS
→ DOI 输出目录中唯一的本地 PDF
→ Nature 公开主文 PDF
→ restricted metadata / partial recovery
```

当 OA JATS 足够完整时：

```text
DOI
→ Springer Nature OA JATS
→ JATS 完整性检查
→ PaperFlow JATS renderer
→ 表格数值 QA
```

典型 source：

```text
springer_nature_jats
```

如果 JATS 不完整或不可用，但能取得主文 PDF：

```text
PDF
→ MinerU Advanced
→ structured_content.json
→ PaperFlow renderer
→ QA
```

典型 source：

```text
nature_pdf_mineru
local_pdf_mineru
```

如果公开全文和公开 PDF 都不可用，PaperFlow 可以保存可恢复的 bibliographic / abstract metadata，并明确标记为：

```text
springer_restricted_partial
Status = warning
```

这种输出不是完整全文。

---

## 2. 不支持的内容

PaperFlow V2 当前不是通用出版商解析器。

未实现的 DOI 路线会被拒绝，例如不属于以下范围的 DOI：

```text
10.1016/...
10.1007/s12273...
10.1038/...
```

也不要假设所有 `10.1007/...` Springer DOI 都受支持；当前专门支持的是 Building Simulation 的：

```text
10.1007/s12273...
```

---

## 3. 环境设计

PaperFlow 自身保持轻量。

PDF 解析使用独立的 MinerU 环境，因此 PaperFlow V2 环境中不需要安装：

```text
torch
transformers
mineru
lmdeploy
```

建议结构：

```text
D:\paper\
├─ paperflow-v2\
│  └─ .venv\
├─ mineru4\
│  └─ .venv\
└─ outputs\
```

PaperFlow 通过 `MINERU_EXECUTABLE` 调用外部 MinerU CLI。

---

## 4. 安装

进入仓库：

```cmd
cd /d D:\paper\paperflow-v2
```

创建并激活虚拟环境。Python 版本应满足 `pyproject.toml` 中的 `requires-python`：

```cmd
python -m venv .venv
.venv\Scripts\activate
```

升级 pip：

```cmd
python -m pip install --upgrade pip
```

安装 PaperFlow 和开发依赖：

```cmd
python -m pip install -e ".[dev]"
```

确认 CLI：

```cmd
paperflow --help
```

---

## 5. 配置

不要把真实 API key 提交到 Git。

项目使用本地：

```text
.env
```

仓库只应提交：

```text
.env.example
```

建议 `.env`：

```env
ELSEVIER_API_KEY=your_elsevier_key
SPRINGER_OA_API_KEY=your_springer_open_access_key
SPRINGER_META_API_KEY=your_springer_meta_key

MINERU_EXECUTABLE=D:\paper\mineru4\.venv\Scripts\mineru-kit.exe
MINERU_TIER=advanced
```

其中：

- `ELSEVIER_API_KEY`：Elsevier 结构化全文路线；
- `SPRINGER_OA_API_KEY`：Springer Nature Open Access JATS；
- `SPRINGER_META_API_KEY`：受限全文情况下的 metadata recovery；
- `MINERU_EXECUTABLE`：外部 MinerU CLI 可执行文件；
- `MINERU_TIER`：当前推荐 `advanced`。

---

## 6. 单篇论文处理

基本命令：

```cmd
paperflow process DOI --library-root "输出目录"
```

例如 Elsevier：

```cmd
paperflow process 10.1016/j.buildenv.2025.113542 --library-root "D:\paper\outputs\paperflow"
```

Nature：

```cmd
paperflow process 10.1038/s41467-019-11026-x --library-root "D:\paper\outputs\paperflow"
```

Building Simulation：

```cmd
paperflow process 10.1007/s12273-026-1484-2 --library-root "D:\paper\outputs\paperflow"
```

PaperFlow 会为每个 DOI 创建独立目录，例如：

```text
D:\paper\outputs\paperflow\
└─ 10.1038_s41467-019-11026-x\
```

---

## 7. 显式使用本地 PDF

对于 Nature / Building Simulation 等 PDF 路线，可以显式指定主文 PDF：

```cmd
paperflow process 10.1038/example --pdf "D:\papers\article.pdf" --library-root "D:\paper\outputs\paperflow"
```

或者：

```cmd
paperflow process 10.1007/s12273-example --pdf "D:\papers\article.pdf" --library-root "D:\paper\outputs\paperflow"
```

`--pdf` 的优先级最高。

Elsevier `10.1016/...` 路线以结构化 XML 为主，不使用本地 PDF 替代其正常 XML 路线。

---

## 8. 后来才拿到 PDF 怎么办

这是 PaperFlow V2 支持的正常工作流。

例如第一次运行 Nature 论文时：

```text
Source = springer_restricted_partial
Status = warning
```

说明当时没有取得完整公开全文。

后来合法拿到主文 PDF 后，把 **恰好一个** `.pdf` 文件放进这个 DOI 的输出目录：

```text
D:\paper\outputs\paperflow\
└─ 10.1038_s41558-024-02108-w\
   └─ 任意文件名.pdf
```

然后重新运行原命令：

```cmd
paperflow process 10.1038/s41558-024-02108-w --library-root "D:\paper\outputs\paperflow"
```

PaperFlow 会发现本地 PDF，并重新走 PDF → MinerU 路线。

本地 PDF 自动发现规则：

```text
0 个 PDF
→ 继续尝试在线路线

恰好 1 个 PDF
→ 自动使用

超过 1 个 PDF
→ 判定歧义并停止，不自动猜测
```

不要把主文 PDF 和 Supplementary PDF 一起放在 DOI 目录中。

---

## 9. 批量处理

准备一个文本文件，每行一个 DOI，例如：

```text
10.1016/j.buildenv.2025.113542
10.1007/s12273-026-1484-2
10.1038/s41467-019-11026-x
10.1038/s41558-024-02108-w
```

例如保存为：

```text
D:\paper\dois.txt
```

批量运行：

```cmd
paperflow process-list "D:\paper\dois.txt" --library-root "D:\paper\outputs\paperflow_batch"
```

运行过程中会逐条显示：

```text
[1/N] DOI -> success (...)
[2/N] DOI -> warning (...)
[3/N] DOI -> FAILED
```

批量结束后会生成：

```text
batch_results.csv
```

用于查看每篇论文的 route、source、status 和失败/警告情况。

对于后来补到 PDF 的论文，不需要整批重跑。把 PDF 放入对应 DOI 目录后，只重新运行那一篇即可。

---

## 10. 输出文件

不同路线生成的中间文件不同，但核心输出通常包括：

```text
paper_llm.md
qa.json
```

可能还包括：

```text
paper_raw.md
paper.xml
paper.jats.xml
springer_oa_response.xml
paper.pdf
mineru.zip
structured_content.json
springer_meta.json
access.json
```

### `paper_llm.md`

面向后续 LLM 阅读 / RAG / 文献分析的最终 Markdown。

### `qa.json`

必须重点查看。

它记录：

- DOI；
- route；
- source；
- status；
- fallback 是否发生；
- 表格 QA；
- References 检查；
- PDF / MinerU 检查；
- warnings；
- failures。

### `access.json`

当论文无法取得完整公开全文时，用于记录 restricted / partial 状态以及后续补入合法 PDF 的提示。

---

## 11. Status 含义

### `success`

当前路线通过主要 QA，没有已知需要人工注意的 warning。

### `warning`

已经生成可用输出，但存在明确 caveat。

常见情况包括：

- Nature / Springer 完整全文不可公开获取，只保存 metadata / abstract；
- PDF → MinerU 路线存在非致命警告；
- Elsevier 某个表格只有图片，没有结构化表格内容；
- 其他 QA 可以接受但值得人工查看的情况。

`warning` 不等于完整全文。

必须结合：

```text
Source
qa.json
access.json
```

判断实际内容级别。

### `failed`

发生硬失败，例如：

- 不支持的 route；
- XML 不满足最低完整性要求；
- 结构化表格内容丢失；
- 表格数字审计失败；
- References 应存在但丢失；
- PDF 不可解析；
- 最终 Markdown 仍残留不允许的图片 / base64 / display equation。

---

## 12. 科学内容处理原则

PaperFlow V2 采用保守策略。

### 正文

尽量完整保留正文文本，不进行摘要式压缩。

### 表格

对于结构化表格：

- 保留表格；
- 保留单元格内容；
- 对关键路线进行 table numeric audit；
- 不主动“修正”数值；
- 不因为 Markdown 美观而重写科学数据。

### 图片

最终 Markdown 不保留图片本体，包括：

```text
Markdown image
HTML <img>
base64 image
MinerU image_source
```

图片 caption 在有意义时可以保留。

### 公式

独立展示公式可以移除，以减少复杂 LaTeX / OCR 噪声。

但行内科学量应尽量保留，例如：

```text
U-value
SHGC
WWR
ACH
R²
R2
CV(RMSE)
NMBE
kWh/m²
W/m²K
°C
%
```

### References

References 是完整性检查的重要组成部分，不应为了清理 Markdown 而删除。

---

## 13. 重要限制

### 13.1 PDF 数值审计不是 PDF 真值校验

对于 PDF → MinerU 路线，PaperFlow 的 numeric audit 检查的是：

```text
MinerU structured_content
→ PaperFlow Markdown
```

之间的数值是否保持一致。

它不能证明 MinerU OCR / PDF 解析阶段从原始 PDF 识别出的数字一定正确。

换句话说：

```text
PDF 原文 → MinerU
```

这一段仍受 MinerU 解析质量影响。

对于高风险或关键科学数据，仍建议回看原始 PDF。

---

### 13.2 图片型表格无法凭空恢复

如果出版社只提供一个表格图片，而没有结构化 cell 数据，PaperFlow 不会 OCR 后冒充“精确结构化表格”。

此类情况可能被标为 warning，并省略图片本体。

---

### 13.3 Restricted 结果不是完整全文

例如：

```text
Source = springer_restricted_partial
Status = warning
```

只表示 PaperFlow 保存了当时合法可获得的 bibliographic / abstract 信息。

它不会推断、生成或补写缺失的正文段落。

---

### 13.4 本地 PDF 身份由用户负责

如果手动把 PDF 放到 DOI 输出目录或使用 `--pdf`，请确认它确实对应目标 DOI。

PaperFlow 的主要目标是处理内容，不应被视为可靠的论文身份鉴定工具。

---

### 13.5 API / Publisher 可用性会变化

Elsevier、Springer Nature 和 Nature 网站的：

- API 权限；
- Open Access 状态；
- HTTP 行为；
- PDF 暴露方式；
- metadata 可用字段；

都可能变化。

因此同一 DOI 在不同时间、账户权限或网络环境下可能走不同 fallback。

---

### 13.6 不绕过访问限制

PaperFlow 不用于：

- 绕过 paywall；
- 绕过机构认证；
- 绕过出版社访问控制；
- 下载用户无权获取的内容。

对于受限论文，应由用户合法获得主文 PDF，再交给本地 PaperFlow 处理。

---

## 14. Repository structure

```text
paperflow-v2/
├─ .env.example
├─ .gitignore
├─ README.md
├─ pyproject.toml
│
├─ scripts/
│  ├─ rerender_mineru_batch.py
│  └─ smoke_elsevier_live.py
│
├─ src/
│  └─ paperflow/
│     ├─ batch.py
│     ├─ cli.py
│     ├─ config.py
│     ├─ models.py
│     ├─ pipeline.py
│     ├─ recovery.py
│     ├─ routing.py
│     ├─ cleaners/
│     ├─ parsers/
│     ├─ qa/
│     ├─ sources/
│     ├─ storage/
│     └─ utils/
│
└─ tests/
   └─ test_*.py
```

---

## 15. 开发与测试

格式化：

```cmd
python -m ruff format src tests scripts
```

静态检查：

```cmd
python -m ruff check src tests scripts
```

完整测试：

```cmd
pytest -q
```

PaperFlow V2 frozen baseline 在提交前的本地验证结果：

```text
Ruff:   All checks passed
Pytest: 116 passed
```

---

## 16. 当前验证快照

在一次 87 DOI 的本地批处理验证中，最终结果为：

```text
Total   = 87
Success = 74
Warning = 13
Failed  = 0
```

这不是跨出版商通用 benchmark。

其中 warning 包含 restricted partial metadata、PDF/MinerU caveat、图片型表格等情况，因此不能把 `Success + Warning` 简单理解为“全部获得完整全文”。

这个结果的意义主要是：在该验证集合上，PaperFlow 没有留下未处理的硬失败，同时能够明确区分完整成功与需要人工注意的结果。

---

## 17. 推荐工作流

单篇：

```text
DOI
→ paperflow process
→ 看 Status / Source
→ 打开 paper_llm.md
→ 检查 qa.json
```

批量：

```text
DOI list
→ paperflow process-list
→ 查看 batch_results.csv
→ 筛选 warning / failed
→ 对 warning 查看 qa.json / access.json
→ 后续补到 PDF 的论文单篇重跑
```

对于科研使用，建议始终保留原始 DOI / PDF / publisher source 作为最终核对依据，而不是把 Markdown 当作唯一事实来源。
