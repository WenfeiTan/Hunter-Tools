# Hunter-Tools

Google X-Ray Candidate Sourcing Tool.

## New User Guide

如果你是 0 基础 Python 用户，建议先看这份图文指南：

- [0 基础 Step-by-Step 指南：用 Hunter-Tools 找法兰克福 HRBP](docs/zero-to-hrbp-frankfurt-guide.md)

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Usage Guide

### 1) 搜索 + 打分（完整流程）

推荐交互式：

```bash
hunter-tools --interactive
```

也可以直接写 `config.yaml` 后运行：

```yaml
job_title: HRBP
location: Frankfurt
title_alias_mode: core
location_mode: expanded
location_expand_level: 2
search_args:
  - Mandarin
  - employee relations
pages_per_query: 2
page_size: 10
output: outputs/candidates_config.csv
show_browser: true
manual_antibot: true
```

```bash
hunter-tools --config
```

`--config` 会跳过交互式提问，直接使用 `config.yaml` 里的配置。注意 `job_title` 和 `location` 必须写在 `config.yaml` 顶层，key 名必须完全匹配。

参数式：

```bash
hunter-tools \
  --job-title sde \
  --location Frankfurt \
  --title-alias-mode core \
  --location-mode expanded \
  --search-args "backend" "distributed systems" \
  --pages-per-query 2 \
  --page-size 20 \
  --output outputs/candidates.csv \
  --debug
```

### 2) 只打分（不重新搜索）

```bash
hunter-tools \
  --job-title sde \
  --location Frankfurt \
  --rescore-middle-csv outputs/middle/candidates.csv \
  --output outputs/candidates_rescored.csv \
  --debug
```

## Key CLI Options

Required:
- `--job-title`
- `--location`

Query control:
- `--title-alias-mode off|core|broad`
- `--location-mode strict|expanded|country_only`
- `--location-expand-level 1|2|3`
- `--search-args ...`（只参与搜索）

Runtime:
- `--show-browser / --no-show-browser`
- `--pages-per-query`
- `--page-size`
- `--delay-seconds`
- `--timeout-seconds`
- `--blocked-cooldown-seconds`
- `--manual-antibot / --no-manual-antibot`
- `--manual-antibot-timeout-seconds`
- `--manual-antibot-poll-seconds`
- `--debug`

## Outputs

运行可能产出：
- 最终 CSV：`outputs/candidates.csv`
- 强筛 CSV（仅当 `score_filter.yaml.filter` 存在任意 `true`）：基于 `--output` 自动生成 `_filter` 路径
  - 示例：`outputs/candidates.csv` -> `outputs/candidates_filter.csv`
- 中间态 CSV（未打分）：`outputs/middle/candidates.csv`
- 原始页面：`outputs/raw_pages/`
- 运行日志：`outputs/logs/<timestamp>.log`

最终 CSV 列顺序：
- `name`
- `score`
- `location_guess`
- `yoe_guess`
- `matched_keywords`
- `profile_url`
- `title`
- `snippet`
- `source_query`
- `timestamp`

## Config Files

- `config.yaml`：运行默认参数
- `score_filter.yaml`：打分 + 强筛配置
- `score_dictionary/<job>.yaml`：岗位词典

### `config.yaml` 示例

```yaml
job_title: HRBP
location: Frankfurt

title_alias_mode: core
location_mode: expanded
location_expand_level: 2
search_args: []

pages_per_query: 2
page_size: 10
output: outputs/candidates_config.csv

delay_seconds: 4
timeout_seconds: 25.0
blocked_cooldown_seconds: 25.0
jitter_ratio: 0.35
show_browser: true
fail_fast: false
raw_output_dir: outputs/raw_pages
manual_antibot: true
manual_antibot_timeout_seconds: 180.0
manual_antibot_poll_seconds: 2.0
debug: false
```

使用配置文件运行：

```bash
hunter-tools --config
```

常见坑：
- 必填项是 `job_title` 和 `location`，不是 `jobtitle`、`loation` 或其他拼写。
- `search_args` 只参与搜索 query，不参与打分；打分词典在 `score_dictionary/<job>.yaml`。
- 想调整强筛维度，改 `score_filter.yaml` 里的 `filter`。

### `score_filter.yaml` 示例

```yaml
weights:
  title: 3
  location: 2
  language: 2
  seniority: [3, 2, 1]
  skills: 1
  industry: 1
mode:
  title: once
  location: once
  language: per_hit
  seniority: once
  skills: once
  industry: once
filter:
  location: true
  seniority: true
```

规则：
- `weights/mode` 维度必须和 `score_dictionary/<job>.yaml` 完全一致
- `filter` 里值为 `true` 的维度会参与强筛
- 强筛条件是 AND：候选人必须在所有启用维度都有命中，才会进入 `*_filter.csv`
- 若 `filter` 缺失或没有任何 `true`，不会生成强筛 CSV

## Seniority + yoe Token

`seniority` 支持关键词和 `yoe` token 混用：

```yaml
seniority:
  junior:
    - Junior Software Engineer
    - yoe:0-2
  mid:
    - Software Engineer
    - yoe:3-7
  senior:
    - Senior Software Engineer
    - yoe:8+
```

语义：
- `yoe:0-2` -> 0 到 2 年
- `yoe:3-7` -> 3 到 7 年
- `yoe:8+` -> 8 年及以上

计分行为：
- `yoe_guess` 从 `title + snippet` 提取，仅作为 seniority 证据，不单独加分
- 同一 `seniority` 子维度内，关键词 + yoe token 同时命中只算一次子维度命中
- `mode.seniority = once`：seniority 维度取一次
- `mode.seniority = per_hit`：按命中的 seniority 子维度数量累计
