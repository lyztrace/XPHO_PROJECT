# Physics Competition Annotation MVP

物理竞赛题标注工具，将 Markdown 格式的物理竞赛题转换为结构化的 JSON 标注文件。输出格式完全对齐《最终模板.json》和《物理竞赛题标注规范和说明-0416.md》。

---

## 目录

1. [项目概述](#1-项目概述)
2. [技术栈](#2-技术栈)
3. [项目结构](#3-项目结构)
4. [完整工作流程](#4-完整工作流程)
   - [第一步：得到题目（原始 MD 文档）](#第一步得到题目原始-md-文档)
   - [第二步：Git 上传保留痕迹（init_commit）](#第二步git-上传保留痕迹init_commit)
   - [第三步：修改 MD 文档](#第三步修改-md-文档)
   - [第四步：运行脚本（pipeline）](#第四步运行脚本pipeline)
   - [第五步：填充脚本](#第五步填充脚本)
   - [第六步：Git 提交标注版本（final_commit）](#第六步git-提交标注版本final_commit)
5. [各脚本详细说明](#5-各脚本详细说明)
6. [JSON 输出结构](#6-json-输出结构)
7. [LLM 集成](#7-llm-集成)
8. [环境配置](#8-环境配置)
9. [枚举值规范](#9-枚举值规范)
10. [标注规范](#10-标注规范)

---

## 1. 项目概述

本项目旨在将物理竞赛题目（IPhO / 奥赛风格）从自然语言 Markdown 文档转换为结构化 JSON 标注数据，便于后续的 AI 训练、题库管理、自动判题等应用。

**核心能力**：

- **解析**：自动识别 Markdown 文档中的题目、解答、评分标准、图表代码等板块
- **拆分**：按 Part（A/B/C...）拆分子问题（A.1、A.2、B.1...）
- **标注**：借助 LLM（大语言模型）自动填充关联考点、物理模型、物理场景、条件提取、难度等元数据
- **图表**：从 Markdown 中提取 Python 绘图代码，自动渲染生成 PNG 图片
- **校验**：对输出 JSON 进行格式、枚举值、路径等合规性校验
- **留痕**：通过 Git 双重提交机制，完整保留"原始版本 → 标注版本"的修改轨迹

**样例数据**：`data/Q1/` 目录包含一道完整的 IPhO 风格物理题——关于**电动力缆绳（Electrodynamic Tether）的轨道衰减与电热平衡**，涵盖轨道力学、电磁感应、热物理三大交叉领域，共 10 分、8 个子问题。

---

## 2. 技术栈

| 层面 | 技术选型 |
|------|---------|
| 语言 | Python 3.10+ |
| LLM 调用 | OpenAI 兼容 API（支持 OpenAI / OpenRouter / DeepSeek 等） |
| 图表渲染 | Matplotlib（Agg 后端，无 GUI 依赖） |
| JSON 校验 | JSON Schema（Draft-07）+ 自定义校验脚本 |
| 版本控制 | Git（本地仓库，自动提交） |
| 环境管理 | python-dotenv（`.env` 文件） |

---

## 3. 项目结构

```
mvp/
├── .env                       # LLM 密钥等环境变量（需自行创建）
├── .env.example               # 环境变量模板
├── .gitignore                 # Git 忽略规则（work/、venv/、__pycache__/ 等）
├── README.md                  # 本文档
│
├── schema/
│   └── annotation_new.schema.json    # 输出 JSON 的 Schema 校验规范
│
├── data/
│   └── Q1/
│       ├── Q1_problem.md             # 【输入】原始物理题 Markdown 文档
│       ├── Q1_problem.json           # 【输出】标注后的结构化 JSON
│       ├── image/                    # 渲染生成的图片
│       │   ├── ipho_2025_1_1.png     # 场景配置图 1
│       │   └── ipho_2025_1_2.png     # 场景配置图 2
│       └── work/                     # 中间产物（自动生成）
│           ├── Q1.parsed.json        # 解析后的层级结构
│           ├── Q1.subquestions.json  # 拆分后的子问题数据
│           ├── Q1.diagram.py         # 提取的图表 Python 代码
│           ├── Q1.meta.json          # 元数据（来源/年份等）
│           └── Q1.review.todo.md     # 待人工补全字段清单
│
└── scripts/
    ├── pipeline_new.py              # 【核心】主工作流统一入口（一键执行）
    ├── parse_md.py                  # Markdown 层级结构解析器
    ├── split_subquestions.py        # 子问题拆分器 + 评分标准提取
    ├── fill_annotation_new.py       # 标注 JSON 生成器 + LLM 自动填充
    ├── llm_client.py                # LLM 调用客户端（OpenAI 兼容 API）
    ├── extract_diagram.py           # 图表代码提取器（从 MD 提取 Python 代码块）
    ├── render_diagram.py            # 图表渲染器（执行 Python 代码生成 PNG）
    ├── sync_image_refs_new.py       # 图片引用同步器（注入路径到 MD 和 JSON）
    ├── validate_annotation_new.py   # JSON 输出格式校验器
    ├── convert_to_new_format.py     # 旧格式 → 新格式转换工具
    ├── init_commit.py               # Git 原始版本提交（修改留痕第一轮）
    ├── final_commit.py              # Git 标注版本提交（修改留痕第二轮）
    └── git_utils.py                 # Git 公共工具函数
```

---

## 4. 完整工作流程

整体的标注流程如下图所示，共分为六大步骤：

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        完整标注工作流                                     │
│                                                                         │
│  ① 得到题目           ② Git 上传保留痕迹         ③ 修改 MD 文档          │
│  ┌──────────┐        ┌──────────────┐         ┌──────────────┐          │
│  │ 原始 MD  │  ───→  │ init_commit  │  ───→   │ 人工修改/补充 │          │
│  │ 题目文档 │        │ git 提交原版  │         │ MD 文档内容   │          │
│  └──────────┘        └──────────────┘         └──────┬───────┘          │
│                                                      │                  │
│  ⑥ Git 提交标注版      ⑤ 人工填充             ④ 运行脚本               │
│  ┌──────────────┐     ┌──────────────┐    ┌──────────────┐              │
│  │final_commit  │ ←── │ 按 TODO 清单 │ ←── │ pipeline     │              │
│  │git 提交产物  │     │ 补全剩余字段 │    │ 自动标注+渲染│              │
│  └──────────────┘     └──────────────┘    └──────────────┘              │
│                                                                         │
│  产出：Q{n}_problem.json（完整标注 JSON）+ 图片 + review_todo.md         │
└─────────────────────────────────────────────────────────────────────────┘
```

以下逐一详述每个步骤。

---

### 第一步：得到题目（原始 MD 文档）

**文件位置**：`data/{Qn}/Q{n}_problem.md`

**文档格式要求**：Markdown 文档需按以下结构组织：

```markdown
# 题目标题（可选，不限格式）

# Question
本题的题干部分，包括背景介绍、题目描述、图片引用等。

### Part A: 第一板块名称
A.1 子问题描述 ...
A.2 子问题描述 ...

### Part B: 第二板块名称
B.1 子问题描述 ...

# Answer
本题的标准解答。

### Part A: 第一板块名称
**[A.1's Standard Solution]** 解答过程...
**[Final Result]** : 最终答案...

**[A.2's Standard Solution]** 解答过程...
**[Final Result]** : 最终答案...

### Part B: 第二板块名称
...

# GradingRubric
评分标准（表格格式）。

| sub-part | item | marks | notes |
|----------|------|-------|-------|
| **A.1**  | correctly sets up equation | 0.3 | ... |
|          | obtains correct result     | 0.2 | ... |
| **A.2**  | ...                        | ... | ... |

# DiagramCode
用于生成图表的 Python 代码块。

```python
import matplotlib.pyplot as plt
# 绘图代码 ...
plt.savefig("Figure_1.png")
```

# QuestionReview
（可选）题目审查意见。

# AnswerValidation
（可选）答案校验意见。
```

**关键约定**：

| 标记 | 含义 | 级别 |
|------|------|------|
| `# Question` | 题目板块（白名单识别） | 一级标题 |
| `# Answer` | 解答板块 | 一级标题 |
| `# GradingRubric` | 评分标准板块 | 一级标题 |
| `# DiagramCode` | 图表代码板块 | 一级标题 |
| `### Part X: ...` | 子板块划分 | 三级标题 |
| `**A.1.**` | 子问题标记 | 加粗文本 |
| `**[A.1's Standard Solution]**` | 标准解答标记 | 加粗文本 |
| `**[Final Result]** :` | 最终答案标记 | 加粗文本 |

> **注意**：
> - 只有白名单中的一级标题（Question / Answer / DiagramCode / QuestionReview / AnswerValidation / GradingRubric）才会被识别为顶层节，其他 `#` 标题会被当作普通文本保留。
> - 子问题编号格式固定为 `**字母.数字.**`（如 `**A.1.**`、`**B.3.**`）。
> - 评分标准使用 Markdown 表格，sub-part 列空表示延续上一行的子问题。
> - 图表代码必须是 ` ```python ... ``` ` 代码块。

---

### 第二步：Git 上传保留痕迹（init_commit）

**目的**：在任何人机修改之前，把原始题目文档提交到 Git，作为不可篡改的原始版本。后续所有的标注修改都基于此版本，git diff 可清晰展示"原始 → 标注"的全部变更。

**脚本**：[`scripts/init_commit.py`](scripts/init_commit.py)

**执行方式**（通常由 pipeline 自动调用，也可单独运行）：

```bash
# 单独执行
python scripts/init_commit.py --file Q1

# 或通过 pipeline 指定 --git 参数自动执行
python scripts/pipeline_new.py --file Q1 --git
```

**执行逻辑**：

1. 检查 MVP 目录是否为 Git 仓库，若无则执行 `git init -b main` 初始化
2. 自动配置本地 Git 用户信息（若未配置）：`user.email = mvp@localhost`、`user.name = MVP Annotator`
3. 自动创建 `.gitignore` 文件（排除 `work/`、`__pycache__/`、虚拟环境等）
4. 将 `data/Q{n}/Q{n}_problem.md` 加入暂存区并提交，提交信息为：

   ```
   upload: original Q{n} before annotation
   ```
5. **幂等性保证**：若 Git 历史中已存在相同主题的提交，自动跳过，避免重复提交

**Git 提交记录示例**：

```
$ git log --oneline
abc1234 upload: original Q1 before annotation
```

---

### 第三步：修改 MD 文档

在 Git 提交原始版本之后、运行自动标注脚本之前，可以根据需要**人工修改 MD 文档**。常见的修改场景包括：

- 补充或修正题目原文中的错漏
- 补充或修正标准解答过程
- 完善评分标准（GradingRubric 表格）
- 修正 Markdown 格式（确保符合解析规范）
- 添加或修改 DiagramCode 中的图表代码

**为什么要在这一步修改？**

- Git 已保留了原始版本，所有修改都可以通过 `git diff` 追溯
- 后续 pipeline 会自动读取修改后的 MD 文档进行解析和标注
- 确保进入 pipeline 的数据是高质量的

---

### 第四步：运行脚本（pipeline）

**脚本**：[`scripts/pipeline_new.py`](scripts/pipeline_new.py)

这是整个工作流的**核心引擎**，一键顺序执行全部 7 个处理阶段。

#### 基本用法

```bash
# 最基本的用法：处理 Q1
python scripts/pipeline_new.py --file Q1

# 跳过 LLM 调用，只生成 JSON 骨架（省钱模式）
python scripts/pipeline_new.py --file Q1 --no-llm

# 带来源和年份参数
python scripts/pipeline_new.py --file Q1 --source ipho --year 2025

# 自动执行 git 提交（包含 init_commit + final_commit）
python scripts/pipeline_new.py --file Q1 --git

# 只跑特定阶段
python scripts/pipeline_new.py --file Q1 --stage original   # 只做原版 git 提交
python scripts/pipeline_new.py --file Q1 --stage annotate   # 只跑标注不提交
python scripts/pipeline_new.py --file Q1 --stage final      # 只做标注版 git 提交
```

#### 命令行参数

| 参数 | 说明 | 默认值 | 可选值 |
|------|------|--------|--------|
| `--file` | 题目编号（**必填**） | — | Q1, Q2, ... |
| `--source` | 题目来源 | `model-teacher` | ipho / cpho / model-teacher / 模拟题 |
| `--year` | 题目年份 | `2026` | 任意年份字符串 |
| `--supplement` | 补充信息 | `""` | 竞赛真题 / 来源说明等 |
| `--git` | 自动执行 git 提交 | 不启用 | flag，启用即生效 |
| `--stage` | 指定运行阶段 | `all` | all / original / annotate / final |
| `--no-llm` | 跳过 LLM 调用 | 不启用 | flag，启用即生效 |

#### Pipeline 内部执行顺序

```
启动 → 读取 .env → 创建 work/ 和 image/ 目录 → 生成 meta.json
                                                        │
    ┌───────────────────────────────────────────────────┘
    │
    ▼
① parse_md          ───  解析 MD 层级结构 → Q{n}.parsed.json
    │                    （识别 Question/Answer/GradingRubric/DiagramCode 板块）
    │
    ▼
② split_subquestions ───  拆分子问题 → Q{n}.subquestions.json
    │                    （按 Part 拆分 A.1/A.2/B.1...，提取解答/答案/评分标准/背景信息）
    │
    ▼
③ fill_annotation_new ──  生成标注 JSON → Q{n}_problem.json + Q{n}.review.todo.md
    │                    （填充 JSON 骨架 + LLM 自动标注元数据字段）
    │
    ▼
④ extract_diagram    ───  提取图表 Python 代码 → Q{n}.diagram.py
    │
    ▼
⑤ render_diagram     ───  执行代码渲染 PNG 图片 → image/ 目录
    │
    ▼
⑥ sync_image_refs_new ──  同步图片引用到 MD 和 JSON
    │
    ▼
⑦ validate_annotation_new ──  校验 JSON 格式合规性
    │
    ▼
  完成 → 输出 Q{n}_problem.json + 图片 + review_todo.md
```

#### 产出文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `data/Q{n}/Q{n}_problem.json` | 输出 | 完整的结构化标注 JSON |
| `data/Q{n}/image/*.png` | 输出 | 渲染生成的图片 |
| `data/Q{n}/work/Q{n}.review.todo.md` | 输出 | 待人工补全字段清单 |
| `data/Q{n}/work/Q{n}.parsed.json` | 中间 | 解析后的层级结构 |
| `data/Q{n}/work/Q{n}.subquestions.json` | 中间 | 拆分后的子问题数据 |
| `data/Q{n}/work/Q{n}.diagram.py` | 中间 | 提取的图表代码 |
| `data/Q{n}/work/Q{n}.meta.json` | 中间 | 元数据 |

---

### 第五步：填充脚本

Pipeline 运行后，会自动生成一个 **待办清单文件** `data/Q{n}/work/Q{n}.review.todo.md`，列出所有需要人工补全的字段。

#### 自动化填充 vs 人工填充

| 字段 | 无 LLM | 有 LLM | 填充来源 |
|------|:---:|:---:|------|
| 问题原文 / 解答过程 / 最终答案 | ✅ | ✅ | 从 MD 解析 |
| 判分标准 | ✅ | ✅ | 从 MD 解析（表格或 LLM 提取） |
| 背景信息 / 上下文 | ✅ | ✅ | 从 MD 解析 |
| 答案类型 / 答案单位 | ✅ | ✅ | 启发式规则推断 |
| 核心思路 | ❌ | ✅ | LLM（分类标签） |
| 物理模型 / 物理场景 | ❌ | ✅ | LLM（分类标签） |
| 关联考点（三级分类） | ❌ | ✅ | LLM（分类标签） |
| 难度（easy/medium/hard） | ❌ | ✅ | LLM（分类标签） |
| 显性条件 / 隐性条件 | ⚠️ 零星 | ✅ 完整 | LLM（条件提取） |
| **改造后问题 / 改造后答案** | ❌ | ❌ | **永远人工** |
| **多解法标注** | ❌ | ❌ | **永远人工** |
| **错误解题步骤** | ❌ | ❌ | **永远人工（暂不标注）** |

> **核心结论**：即使不调用 LLM（`--no-llm`），JSON 的核心内容（题目、解答、答案、判分标准）完全不受影响，结构完整可用。LLM 只是补充元数据标签和条件提取。

#### 人工补全清单示例

```markdown
# Review TODO

## Manual items (after pipeline)
- [ ] Fill 改造后问题 for A.1
- [ ] Fill 改造后答案 for A.1
- [ ] Fill 改造后答案类型 for A.1
- [ ] Fill 改造后答案单位 for A.1
- [ ] Fill 多解法标注 for A.1 (if applicable)
- [ ] Fill 错误解题步骤 for A.1 (if applicable)
...
- [ ] Manual physics correctness review
- [ ] Verify all values are in English
- [ ] Verify 关联图片路径 and 模态类型 per image
```

**人工操作步骤**：

1. 打开 `data/Q{n}/work/Q{n}.review.todo.md`，逐项检查
2. 打开 `data/Q{n}/Q{n}_problem.json`，找到对应字段手动编辑
3. （可选）重新运行 `python scripts/validate_annotation_new.py data/Q{n}/Q{n}_problem.json data/Q{n}/Q{n}_problem.md data/Q{n}/` 校验格式

---

### 第六步：Git 提交标注版本（final_commit）

**目的**：完成自动标注 + 人工定稿后，将最终产物提交到 Git，形成完整的"原始 → 标注"修改链路。

**脚本**：[`scripts/final_commit.py`](scripts/final_commit.py)

**执行方式**：

```bash
# 单独执行
python scripts/final_commit.py --file Q1

# 或通过 pipeline 指定 --git 自动执行
python scripts/pipeline_new.py --file Q1 --git
```

**提交内容**：

- `data/Q{n}/Q{n}_problem.md`（可能因图片占位符同步而更新）
- `data/Q{n}/Q{n}_problem.json`（标注 JSON 产物）
- `data/Q{n}/image/` 目录下所有生成的图片

**提交信息**：

```
annotate: Q{n} annotated per spec v0416
```

**完整的 Git 提交历史示例**：

```
$ git log --oneline
def5678 annotate: Q1 annotated per spec v0416    ← 标注版本
abc1234 upload: original Q1 before annotation    ← 原始版本
```

**查看修改痕迹**：

```bash
# 查看原始版本与标注版本的差异
git diff abc1234 def5678 -- data/Q1/Q1_problem.md
git diff abc1234 def5678 -- data/Q1/Q1_problem.json
```

---

## 5. 各脚本详细说明

### 5.1 pipeline_new.py — 主工作流

| 项目 | 说明 |
|------|------|
| 功能 | 一键执行全部标注流程的统一入口 |
| 输入 | `data/Q{n}/Q{n}_problem.md` |
| 输出 | `Q{n}_problem.json` + 图片 + `review.todo.md` |
| 内部调用 | parse_md → split_subquestions → fill_annotation_new → extract_diagram → render_diagram → sync_image_refs → validate_annotation_new |

### 5.2 parse_md.py — MD 层级解析

| 项目 | 说明 |
|------|------|
| 功能 | 解析 Markdown 文件的层级结构 |
| 识别规则 | 一级标题 `# ` 仅识别白名单（Question/Answer/DiagramCode/QuestionReview/AnswerValidation/GradingRubric）；三级标题 `### ` 识别为 Part 划分 |
| 输出格式 | `{ "Question": {"_intro": "...", "parts": {"Part A: ...": "...", ...}}, "Answer": {...}, ... }` |

### 5.3 split_subquestions.py — 子问题拆分

| 项目 | 说明 |
|------|------|
| 功能 | 按 Part 拆分子问题，提取解答、答案、背景信息、评分标准 |
| 正则匹配 | `**字母.数字.**`（子问题标记）、`**[字母.数字's Standard Solution]**`（解答标记）、`**[Final Result]** :`（答案标记） |
| 评分标准 | 解析 GradingRubric 表格，智能处理 LaTeX 中的 `|` 干扰，过滤小计行 |
| 上下文构建 | 为每个 Part 的第一个子问题（如 A.1、B.1）构建包含图片占位符的完整上下文 |

### 5.4 fill_annotation_new.py — 标注生成

| 项目 | 说明 |
|------|------|
| 功能 | 将子问题数据填充为最终模板格式的 JSON，可选 LLM 自动标注 |
| 启发式推断 | 答案类型（expression/numerical/choice/equation/open-ended/inequality）、答案单位（基于关键词匹配 N/V/W/m/s/K/A...）、模态类型 |
| LLM 填充字段 | 关联考点（三级分类）、物理模型、物理场景、显性条件、隐性条件、核心思路、难度 |
| 人工字段 | 改造后问题/答案/类型/单位、多解法标注、错误解题步骤（不通过 LLM 填充） |
| LaTeX 处理 | 自动修复常见格式问题（双句号、裸变量表达式） |

### 5.5 llm_client.py — LLM 客户端

| 项目 | 说明 |
|------|------|
| 功能 | 封装 OpenAI 兼容 API 的 LLM 调用 |
| 接口 | `chat()` — 文本模式、`chat_json()` — JSON 结构化输出模式、`annotate_subquestion()` — 标注专用入口 |
| 重试机制 | 最多 3 次，指数退避等待（2s / 4s / 6s） |
| 系统提示词 | 预置了物理学专家的 system prompt，要求 LLM 输出标准 IPhO 知识点分类体系 |
| 支持平台 | OpenAI / OpenRouter / DeepSeek / 任何 OpenAI 兼容 API |

### 5.6 extract_diagram.py — 图表代码提取

| 项目 | 说明 |
|------|------|
| 功能 | 从 MD 文件 `# DiagramCode` 节中提取第一个 ` ```python ... ``` ` 代码块 |
| 输出 | `work/Q{n}.diagram.py` |

### 5.7 render_diagram.py — 图表渲染

| 项目 | 说明 |
|------|------|
| 功能 | 在子进程中执行图表 Python 代码，生成 PNG 图片 |
| 兼容性 | Windows GBK 编码兼容（强制 UTF-8）；使用 Agg 后端（无需 GUI） |
| 超时 | 180 秒超时保护 |
| 多图处理 | 若脚本生成多张图，自动按 `{prefix}_{i}.png` 命名（如 `ipho_2025_1_1.png`、`ipho_2025_1_2.png`） |

### 5.8 sync_image_refs_new.py — 图片引用同步

| 项目 | 说明 |
|------|------|
| 功能 | 将渲染生成的图片路径注入 MD 文件（DiagramCode 节前）和 JSON 文件（第一个子问题的关联图片路径 + 模态类型） |
| MD 注入 | 在 `# DiagramCode` 前插入 `![]({rel_img})` |
| JSON 注入 | 更新第一个子问题的 `关联图片路径` 和 `模态类型` 字段 |

### 5.9 validate_annotation_new.py — 格式校验

| 项目 | 说明 |
|------|------|
| 功能 | 对输出 JSON 进行轻量规范校验 |
| 检查项 | JSON 数组格式、9 大节完整性、枚举值有效性、数组长度一致性、关联图片路径存在性、MD 图片格式规范、CJK 字符告警 |
| 返回值 | 非阻塞（在 MVP 阶段不因校验失败而中断流程） |

### 5.10 git_utils.py — Git 工具

| 项目 | 说明 |
|------|------|
| 功能 | 提供 Git 操作的公共工具函数 |
| 主要函数 | `ensure_repo()` — 初始化仓库并配置用户信息；`run_git()` — 执行 git 子命令；`has_staged_changes()` — 检查暂存区；`file_tracked()` — 检查文件是否被追踪 |

### 5.11 convert_to_new_format.py — 格式转换

| 项目 | 说明 |
|------|------|
| 功能 | 将旧格式 JSON（单个对象含 meta/subquestions）转换为新格式（数组形式、中文 key） |
| 用途 | 迁移历史数据时使用 |

---

## 6. JSON 输出结构

标注后的 JSON 输出是一个**数组**，每个元素对应一个子问题。完整的字段结构如下：

```json
[
  {
    "标注基础信息": {
      "来源": "ipho",
      "补充": "",
      "年份": "2025",
      "版块1": "Q1",
      "版块2": "Part-A",
      "版块3": "A.1"
    },

    "题目信息": {
      "背景信息": "...",
      "上下文": "...",
      "问题原文": "...",
      "改造后问题": "",
      "核心思路": "Apply Kepler's third law to derive the orbital period",
      "解答过程": "...",
      "最终答案": ["T_N = ..."],
      "改造后答案": [""],
      "答案类型": ["expression"],
      "改造后答案类型": [""],
      "答案单位": ["s"],
      "改造后答案单位": [""],
      "关联图片路径": ["image/ipho_2025_1_1.png"],
      "模态类型": ["text+illustration figure"],
      "难度": "medium"
    },

    "条件提取": {
      "显性条件": [
        "Initial orbital radius: r₀ = 7000 km",
        "Tether length: L = 20 km"
      ],
      "隐性条件": [
        {
          "条件原文": "The tether is perfectly conducting",
          "隐藏条件": "Electrical resistance of the tether is negligible (R ≈ 0)"
        }
      ]
    },

    "物理模型": "Two-body gravitational system in rotating reference frame",

    "关联考点": [
      ["Mechanics", "Orbital Mechanics", "Kepler's Laws"],
      ["Electromagnetism", "Motional EMF", "Faraday's Law"]
    ],

    "物理场景": "Electrodynamic tether orbiting Earth in equatorial plane",

    "判分标准": [
      "Award 0.3 pt if the answer correctly sets up the effective force equation. Otherwise, award 0 pt.",
      "Award 0.2 pt if the answer obtains the correct final result. Otherwise, award 0 pt."
    ],

    "错误解题步骤": [],

    "多解法标注": [
      {
        "核心思路": "Alternative approach using energy conservation",
        "关键步骤": ["Step 1: ...", "Step 2: ..."],
        "解答过程": "...",
        "适用场景": "When angular momentum is explicitly conserved"
      }
    ]
  }
]
```

### 九大必填节

| 中文 key | 类型 | 说明 |
|----------|------|------|
| `标注基础信息` | object | 来源、年份、版块层级定位 |
| `题目信息` | object | 问题原文、解答、答案、难度等核心字段 |
| `条件提取` | object | 显性条件（数组）+ 隐性条件（对象数组） |
| `物理模型` | string | 使用的物理模型描述 |
| `关联考点` | array of array | 三级知识点分类，每组 `[Level1, Level2, Level3]` |
| `物理场景` | string | 物理场景描述 |
| `判分标准` | array of string | 评分标准条目 |
| `错误解题步骤` | array of object | 考生常见错误记录（暂时留空） |
| `多解法标注` | array of object | 其他解法记录（暂时留空） |

### 标注语言规范

- **key（字段名）**：使用中文
- **value（字段值）**：使用英文
- **LaTeX 公式**：保持原样，使用 `$...$` 或 `$$...$$` 包裹
- **图片路径**：使用相对路径 `image/xxx.png`

---

## 7. LLM 集成

### 启用方式

Pipeline 启动时自动读取项目根目录的 `.env` 文件。在 `mvp/.env` 中配置 LLM 密钥：

```ini
LLM_API_KEY=sk-your-api-key-here
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o
LLM_MAX_TOKENS=4096
LLM_TEMPERATURE=0.3
```

> **注意**：环境变量名是 `LLM_API_KEY`（不是 `OPENAI_API_KEY`）。

### 使用第三方 API 代理

使用 OpenRouter 等代理时，修改 `LLM_BASE_URL` 和 `LLM_MODEL` 即可：

```ini
LLM_API_KEY=sk-or-v1-xxxxx
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=deepseek/deepseek-v3.2
```

### 未经 LLM 时

```bash
# 跳过 LLM，仅生成 JSON 骨架
python scripts/pipeline_new.py --file Q1 --no-llm
```

此时所有 LLM 专属字段（关联考点、物理模型、核心思路、难度等）将保持空值，列在 `review.todo.md` 中等待人工填写。

### LLM 调用的技术细节

| 特性 | 配置 |
|------|------|
| 调用模式 | JSON 模式（`response_format: {"type": "json_object"}`） |
| 重试次数 | 最多 3 次 |
| 文本截断 | 问题原文 ≤ 3000 字符、解答 ≤ 4000 字符、评分标准 ≤ 4000 字符 |
| System Prompt | 预置物理学专家角色，要求按 IPhO 知识点分类体系输出 |

---

## 8. 环境配置

### 前置依赖

```bash
# 安装 Python 依赖
pip install openai python-dotenv matplotlib

# Windows 环境下如遇 GBK 编码问题，设置环境变量
$env:PYTHONIOENCODING="utf-8"
$env:PYTHONUTF8="1"
```

### .env 配置模板

复制 `.env.example` 为 `.env` 并填写：

```ini
# 必需：LLM API 密钥（不填则仅生成 JSON 骨架）
LLM_API_KEY=sk-your-api-key-here

# 可选配置（以下均为默认值）
# LLM_BASE_URL=https://api.openai.com/v1
# LLM_MODEL=gpt-4o
# LLM_MAX_TOKENS=4096
# LLM_TEMPERATURE=0.3
```

---

## 9. 枚举值规范

### 答案类型（answer_type）

| 枚举值 | 说明 |
|--------|------|
| `expression` | 表达式答案（含变量的数学表达式） |
| `numerical` | 数值答案（具体数字） |
| `choice` | 选择题 |
| `equation` | 方程式答案 |
| `open-ended` | 开放性答案（文字描述） |
| `inequality` | 不等式答案 |

### 模态类型（modality_type）

| 枚举值 | 说明 |
|--------|------|
| `text-only` | 纯文字，无图表辅助 |
| `text+illustration figure` | 文字 + 场景示意图（图表描述场景，文字提供描述） |
| `text+variable figure` | 文字 + 变量图（图表明确关键变量或空间范围） |
| `text+data figure` | 文字 + 数据图（图表呈现文本中未给出的数据/函数曲线） |

### 难度（difficulty）

| 枚举值 | 说明 |
|--------|------|
| `easy` | 简单 |
| `medium` | 中等 |
| `hard` | 困难 |

---

## 10. 标注规范

本项目的标注规范遵循《物理竞赛题标注规范和说明-0416.md》，核心原则如下：

1. **所有标注内容使用英文（value 值），key 使用中文**
2. **LaTeX 数学公式保持原样**，不做翻译或格式转换
3. **图片使用相对路径** `image/xxx.png`，MD 中格式为 `![](image/xxx.png)`
4. **不建议翻译成中文后再修改，再翻译回英文**——保持原始语言一致性
5. **原版文件先 git 提交，再修改**（修改留痕）
6. **文件层级约定**：`data/Q{n}/Q{n}_problem.md`、`data/Q{n}/Q{n}_problem.json`、`data/Q{n}/image/`
7. **改造后问题/答案等字段**不通过 LLM 自动填充，必须由人工标注
8. **关联考点**使用三级分类 `[一级分类, 二级分类, 三级分类]`，遵循 IPhO 知识点分类体系

---

> **最后更新**：2026-04-27
