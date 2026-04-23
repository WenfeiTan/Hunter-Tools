# 技术执行说明（MVP + 并行开发约束）

## 1. 目标与边界

- 目标：交付 PRD 定义的 HRBP 搜索 MVP，支持从输入需求到候选人 CSV 的完整链路。
- 边界：仅实现 Google X-Ray 免费方案，不接入付费 API，不实现前端 dashboard。
- 结果物：可运行 CLI、可测核心模块、稳定字段契约、可并行开发的模块边界。

## 2. 目录职责（唯一责任制）

- `src/hunter_tools/config.py`：词库、默认 headers、评分权重、CSV 字段。
- `src/hunter_tools/models.py`：输入输出数据模型（SearchInput/SearchResult/Candidate）。
- `src/hunter_tools/query_builder.py`：Query 生成逻辑，输出 3-5 条语句。
- `src/hunter_tools/selenium_client.py`：Google 抓取与浏览器自动化，产出 SearchResult 列表。
- `src/hunter_tools/google_page.py`：Google 页面解析、反爬检测、原始 HTML 落盘。
- `src/hunter_tools/parser.py`：LinkedIn URL 过滤、字段提取、URL 归一化。
- `src/hunter_tools/scorer.py`：规则评分与命中词列表。
- `src/hunter_tools/pipeline.py`：流程编排（抓取/过滤/去重/评分/排序）。
- `src/hunter_tools/exporter.py`：CSV 导出。
- `src/hunter_tools/main.py`：CLI 参数与流程入口。
- `tests/`：单测，仅覆盖模块级功能，不访问外网。

约束：
- 禁止跨模块重复实现同一逻辑（例如 URL 归一化只能在 `parser.py`）。
- 禁止在 `main.py` 内写业务逻辑，业务逻辑只能在模块内。

## 3. 模块接口契约（并行开发硬约束）

### 3.1 Query Builder

- 输入：`SearchInput`
- 输出：`list[str]`
- 约束：
  - 返回数量 `3 <= n <= 5`
  - 每条 query 必须包含 `site:linkedin.com/in`

### 3.2 Acquisition

- 输入：`query: str, pages: int, page_size: int, delay_seconds: float`
- 输出：`list[SearchResult]`
- 约束：
  - 每个 `SearchResult` 必有 `title/link/query`
  - 网络错误由上层感知（抛异常，不吞错）

### 3.3 Parser & Filter

- 输入：`list[SearchResult]`
- 输出：过滤后 `list[SearchResult]`
- 约束：
  - 仅保留 `linkedin.com/in/`
  - 必须过滤 `/company/`, `/jobs/`, `/posts/`
  - URL 去重前先归一化（去尾斜杠）

### 3.4 Scorer

- 输入：`text: str, location_terms: list[str]`
- 输出：`tuple[int, list[str]]`（分数 + 命中词）
- 约束：
  - 评分规则仅从 `config.py` 读取
  - 命中词需去重且顺序稳定

### 3.5 Pipeline

- 输入：`SearchInput`
- 输出：`tuple[list[str], list[Candidate]]`
- 约束：
  - 去重 key：`profile_url`
  - 同一 URL 多条结果保留最高分
  - 候选人结果按 `score DESC`

### 3.6 Export

- 输入：`list[Candidate], output_path`
- 输出：`Path`
- 约束：
  - CSV 列顺序固定，必须与 `CSV_COLUMNS` 一致

## 4. 并行开发工作流建议

## 4.1 Workstream A：数据获取层

- 负责：`selenium_client.py`, `google_page.py`
- 不可改：`models.py` 字段定义
- 交付标准：
  - 支持分页抓取
  - HTML 结构变化时可快速修复选择器

## 4.2 Workstream B：规则处理层

- 负责：`query_builder.py`, `parser.py`, `scorer.py`
- 不可改：`pipeline.py` 编排签名
- 交付标准：
  - Query 满足 3-5 条策略
  - 过滤/打分规则可配置化（读 `config.py`）

## 4.3 Workstream C：编排与交付层

- 负责：`pipeline.py`, `exporter.py`, `main.py`, `README.md`
- 不可改：底层模块返回结构
- 交付标准：
  - 一条 CLI 命令可跑通全流程
  - 输出 CSV 可直接用于 recruiter 初筛

## 5. 质量门禁（DoD）

- 代码门禁：
  - 无重复逻辑块（特别是文本归一化、URL 处理、字段映射）
  - 模块职责单一，函数短小可测
- 测试门禁：
  - Query 生成测试通过
  - URL 过滤与评分测试通过
- 交付门禁：
  - `README` 可复现运行
  - 输出字段完整：`name/profile_url/title/snippet/score/matched_keywords/location_guess/source_query/timestamp`

## 6. 协作规则（避免并行冲突）

- 禁止直接修改他人负责模块的公共签名；若必须修改，先更新本文件接口契约。
- 新增配置项只放 `config.py`，禁止硬编码到业务函数。
- 所有结构化字段变更必须同时更新：
  - `models.py`
  - `exporter.py`
  - `tests/`
  - `README.md`（若影响使用方式）

## 7. 后续扩展预留

- V2 接入 SERP API：新增 `serp_client.py`，并在 `pipeline.py` 用策略模式注入 client。
- V3 语义匹配：新增 `matcher.py`，仅替换评分阶段，不改抓取/导出契约。
- V4 Dashboard：将 `main.py` 改为服务入口，但复用现有 pipeline。
