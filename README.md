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

运行产物：
- 最终 CSV：`outputs/candidates.csv`
- 中间态 CSV（未打分）：`outputs/middle/candidates.csv`
- 原始页面：`outputs/raw_pages/`
- 运行日志：`outputs/logs/<timestamp>.log`

### 2) 只打分（不重新搜索）

当你只改了 `score.yaml` 或 `score_dictionary/<job>.yaml`：

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
- `--job-title`：岗位名（映射到 `score_dictionary/<job>.yaml`）
- `--location`：目标地点

Query control:
- `--title-alias-mode off|core|broad`
- `--location-mode strict|expanded|country_only`
- `--location-expand-level 1|2|3`：仅 `expanded` 时生效
- `--search-args ...`：只参与搜索，不参与打分

Pipeline:
- `--rescore-middle-csv <path>`：跳过搜索，直接从 middle CSV 重评分
- `--output <path>`：最终 CSV 路径

Runtime:
- `--show-browser / --no-show-browser`
- `--pages-per-query`
- `--page-size`
- `--delay-seconds`
- `--timeout-seconds`
- `--blocked-cooldown-seconds`
- `--manual-antibot / --no-manual-antibot`：遇到 Google anti-bot 时等待手工过验证码
- `--manual-antibot-timeout-seconds`：手工处理最大等待秒数
- `--manual-antibot-poll-seconds`：手工处理等待轮询间隔
- `--debug`

## CSV Columns

最终 CSV 列顺序：
- `name`
- `score`
- `matched_keywords`
- `profile_url`
- `title`
- `snippet`
- `location_guess`
- `guess_yoe`
- `source_query`
- `timestamp`

中间态 CSV 列：
- `name`
- `profile_url`
- `title`
- `snippet`
- `location_guess`
- `guess_yoe`
- `source_query`
- `timestamp`

## Config Files

核心配置：
- `config.yaml`：运行默认参数（分页、延迟、路径、浏览器模式等）
- `score.yaml`：维度权重和 mode
- `score_dictionary/<job>.yaml`：岗位词典（query alias + scoring terms）

### `score.yaml` 示例

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
```

规则：
- `weights.<dim>` 支持 `int` 或 `list[int]`
- `list[int]` 仅用于该维度在 dictionary 中是 `dict` 子维度的情况
- `mode.<dim>`:
- `once`：该维度命中任意词只加一次该维度分
- `per_hit`：按命中次数累计
- `score_dictionary`、`weights`、`mode` 三者维度必须完全一致，否则报错停止

## `seniority` + `yoe` Token

`seniority` 支持关键词和 `yoe` token 混用（都基于 `title + snippet` 同一份文本）：

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

`yoe` token 语义：
- `yoe:0-2`：年限在 `0~2` 命中
- `yoe:3-7`：年限在 `3~7` 命中
- `yoe:8+`：年限 `>=8` 命中

计分规则（重点）：
- `guess_yoe` 只用于识别 `yoe:*`，不单独加分
- 同一 `sub_dim`（如 `mid`）内，关键词和 `yoe token` 只算一次命中（不会重复计分）
- `mode.seniority = once`：`seniority` 维度整体只取一次（命中子维度中的最佳分）
- `mode.seniority = per_hit`：按“命中的 sub_dim 数量”计分，不按证据数量计分

## score_dictionary 示例

文件命名：`--job-title sde` -> `score_dictionary/sde.yaml`

```yaml
title:
  - SDE
  - Software Development Engineer
  - Software Engineer

location:
  - Berlin
  - Germany
  - Deutschland

language:
  - English
  - Mandarin

seniority:
  junior:
    - Junior Software Engineer
    - yoe:0-2
  mid:
    - Software Engineer
    - SDE II
    - yoe:3-7
  senior:
    - Senior Software Engineer
    - Staff Software Engineer
    - yoe:8+

skills:
  - python
  - java
  - distributed systems
  - system design
```

可以新增自定义维度（例如 `dimA`），只要：
- `score_dictionary/<job>.yaml` 有 `dimA`
- `score.yaml.weights.dimA` 有分值
- `score.yaml.mode.dimA` 有模式
