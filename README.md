# Hunter-Tools

Google X-Ray Candidate Sourcing Tool.

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
