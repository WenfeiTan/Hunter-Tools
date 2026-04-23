# Hunter-Tools

Google X-Ray Candidate Sourcing Tool

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

或参数式：

```bash
hunter-tools \
  --job-title sde \
  --location Frankfurt \
  --yoe 3 \
  --title-alias-mode core \
  --location-mode expanded \
  --search-args "backend" "distributed systems" \
  --pages-per-query 2 \
  --page-size 20 \
  --output outputs/candidates.csv \
  --debug
```

执行结果会产出：
- 最终打分 CSV：`outputs/candidates.csv`
- 中间态 CSV（未打分）：`outputs/middle/candidates.csv`
- 原始页面：`outputs/raw_pages/`
- 运行日志：`outputs/logs/<timestamp>.log`

### 2) 只打分（不重新搜索）

当你只改了 `score.yaml` 或 `score_dictionary/<job>.yaml`，可直接重评分：

```bash
hunter-tools \
  --job-title sde \
  --location Frankfurt \
  --yoe 3 \
  --rescore-middle-csv outputs/middle/candidates.csv \
  --output outputs/candidates_rescored.csv \
  --debug
```

## Key CLI Options

Required:
- `--job-title`：岗位名（用于匹配 `score_dictionary/<job>.yaml`）
- `--location`：目标地点
- `--yoe`：年限（用于 banded 维度，如 seniority）

Query control:
- `--title-alias-mode off|core|broad`
- `--location-mode strict|expanded|country_only`
- `--search-args ...`：只参与搜索，不参与打分

Pipeline:
- `--rescore-middle-csv <path>`：跳过搜索，直接从 middle CSV 重评分
- `--output <path>`：输出最终 CSV

Runtime:
- `--show-browser / --no-show-browser`
- `--pages-per-query`
- `--page-size`
- `--delay-seconds`
- `--timeout-seconds`
- `--blocked-cooldown-seconds`
- `--debug`

## Config Management

项目有 3 份核心配置：

1. `config.yaml`：运行默认参数（分页、延迟、路径、浏览器模式等）
2. `score.yaml`：每个维度的分值和打分模式
3. `score_dictionary/<job>.yaml`：岗位维度词典（同时用于 query alias + scoring terms）

### config.yaml example

```yaml
job_title: sde
location: Frankfurt
yoe: 3

title_alias_mode: core
location_mode: expanded
search_args: []

pages_per_query: 2
page_size: 20
output: outputs/candidates.csv

delay_seconds: 1.5
timeout_seconds: 25.0
blocked_cooldown_seconds: 25.0
jitter_ratio: 0.35
show_browser: true
fail_fast: false
raw_output_dir: outputs/raw_pages
middle: true
middle_output_dir: outputs/middle
debug: false
```

### score.yaml example

```yaml
weights:
  title: 3
  location: 2
  language: 2
  seniority: [1, 2, 3]
  skills: 1
mode:
  title: once
  location: once
  language: per_hit
  seniority: once
  skills: once
```

规则说明：
- `weights.<dim>` 支持：
  - `int`
  - `list[int]`（仅当该维度在 dictionary 中是子维度 dict 时）
- `mode.<dim>` 支持：
  - `once`：该维度命中任意词只加一次
  - `per_hit`：按命中次数累计
- `score_dictionary`、`weights`、`mode` 三者维度必须完全一致，否则停止打分并报错

## score_dictionary Management

文件命名规则：
- 使用 `job_title` slug 后的文件名
- 示例：`--job-title sde` -> `score_dictionary/sde.yaml`

### score_dictionary/sde.yaml example

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
    - Associate Software Engineer
  mid:
    - Software Engineer
    - SDE II
  senior:
    - Senior Software Engineer
    - Staff Software Engineer

skills:
  - python
  - java
  - distributed systems
  - system design
```

你也可以新增自定义维度（例如 `dimA`），只要：
- `score_dictionary/<job>.yaml` 有 `dimA`
- `score.yaml.weights.dimA` 有分值
- `score.yaml.mode.dimA` 有模式

