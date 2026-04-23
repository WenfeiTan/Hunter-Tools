# PRD：Google X-Ray Candidate Sourcing Tool（HRBP Demo）

---

## 1. 项目目标（Objective）

构建一个基于 **Google X-Ray Search** 的候选人搜寻工具（MVP版本），实现：

* 批量生成搜索 query
* 获取 LinkedIn profile 链接（通过 Google）
* 解析搜索结果
* 基于关键词进行打分排序
* 输出候选人列表（CSV）

**目标用途：**

* 验证该方法在 HRBP 招聘场景下是否有效
* 提供 recruiter 初筛候选人线索（lead list）

---

## 2. 功能模块拆解（Modules）

### 2.1 Query Builder

#### 输入参数

| 参数        | 类型           | 说明                 |
| --------- | ------------ | ------------------ |
| job_title | string       | 岗位名称（如 HRBP）       |
| location  | string       | 地点（如 Frankfurt）    |
| yoe       | int          | 年限（用于推断 seniority） |
| args      | list[string] | 自定义关键词             |

---

### HRBP 词库设计（V1）

#### 1）Title 同义词

```python
HRBP_TITLES = [
    "HRBP",
    "HR Business Partner",
    "Human Resources Business Partner",
    "People Partner",
    "HR Manager",
    "Senior HR Manager",
    "HR Lead",
    "HR Director"
]
```

---

#### 2）Location 扩展（示例：德国）

```python
LOCATION_EXPANSION = {
    "Frankfurt": ["Frankfurt", "Germany", "Deutschland"],
    "Berlin": ["Berlin", "Germany"],
    "Munich": ["Munich", "Germany"]
}
```

---

#### 3）语言关键词

```python
LANGUAGE_KEYWORDS = [
    "Mandarin",
    "Chinese",
    "Cantonese"
]
```

---

#### 4）HRBP 核心技能关键词

```python
HRBP_SKILLS = [
    "employee relations",
    "talent management",
    "organizational development",
    "performance management",
    "labor law",
    "recruitment",
    "compensation and benefits",
    "HR strategy"
]
```

---

#### 5）Seniority 映射（基于 yoe）

```python
def map_seniority(yoe):
    if yoe <= 3:
        return ["HR Specialist", "HR Generalist"]
    elif yoe <= 7:
        return ["HR Manager", "HRBP"]
    else:
        return ["Senior HRBP", "HR Director", "Head of HR"]
```

---

### Query 生成逻辑

模板：

```text
site:linkedin.com/in (TITLE) (LOCATION) (KEYWORDS)
```

示例：

```text
site:linkedin.com/in ("HR Business Partner" OR "HRBP")
("Frankfurt" OR "Germany")
("Mandarin" OR "Chinese")
("employee relations" OR "talent management")
```

---

### Query 输出（建议 3-5 条）

* 主 query（严格匹配）
* 宽松 query（提高 recall）
* 不同 title 组合 query

---

## 2.2 Search Result Acquisition

### 方案：Google X-Ray（免费）

#### 方法：

使用 Python 抓取 Google 搜索结果页面：

技术栈：

* requests
* BeautifulSoup

#### 请求示例：

```python
https://www.google.com/search?q=QUERY&num=10
```

---

### 注意事项：

* 添加 headers（模拟浏览器）
* 控制频率（避免 captcha）
* 每个 query 抓前 2 页（~20条）

---

### 输出数据结构：

```json
{
  "title": "...",
  "link": "...",
  "snippet": "...",
  "query": "..."
}
```

---

## 2.3 Result Parsing & Filtering

### 1）URL 过滤

仅保留：

```text
linkedin.com/in/
```

过滤掉：

* /company/
* /jobs/
* /posts/

---

### 2）字段解析

从 title/snippet 提取：

| 字段             | 规则          |
| -------------- | ----------- |
| name           | title 前半部分  |
| role           | title 中职位部分 |
| location_guess | snippet中提取  |
| keywords_hit   | 命中的关键词      |

---

### 3）打分机制（Scoring）

简单规则评分：

```python
score = 0

# Title match
if "hr business partner" in text: score += 3

# Location
if "frankfurt" in text: score += 2

# Language
if "mandarin" in text or "chinese" in text: score += 2

# Skills
for skill in HRBP_SKILLS:
    if skill in text:
        score += 1
```

---

### 输出字段：

| 字段               | 说明          |
| ---------------- | ----------- |
| name             | 候选人姓名       |
| profile_url      | LinkedIn 链接 |
| title            | 搜索标题        |
| snippet          | 摘要          |
| score            | 匹配分         |
| matched_keywords | 命中关键词       |
| source_query     | 来源 query    |

---

## 2.4 Storage & Export

### 输出格式：CSV

字段设计：

```text
name,
profile_url,
title,
snippet,
score,
matched_keywords,
location_guess,
source_query,
timestamp
```

---

### 示例输出：

```csv
Jane Doe,https://linkedin.com/in/xxx,Senior HRBP,...,8,"Mandarin, employee relations",Frankfurt,...
```

---

## 3. 执行流程（End-to-End Flow）

1. 输入招聘需求
2. Query Builder 生成 3-5 条搜索语句
3. 对每条 query 抓取 Google 结果
4. 解析 title/link/snippet
5. 过滤非 LinkedIn profile
6. 去重 URL
7. 关键词打分
8. 排序候选人
9. 导出 CSV

---

## 4. MVP 范围

### 必做：

* Query Builder（HRBP only）
* Google 搜索抓取（前 20 条）
* URL 过滤
* 简单打分
* CSV 输出

---

## 5. 成功标准（Success Metrics）

* 每次运行输出 ≥ 50 条候选人链接
* LinkedIn profile 占比 ≥ 60%
* 高分候选人（score ≥ 6）可人工验证相关性

---

## 6. 后续优化方向（Future Roadmap）

### V2

* 接入 SERP API
* 更稳定抓取

### V3

* 使用 Sentence-BERT 做 JD matching

### V4

* 构建 recruiter dashboard

---

## 7. 一句话总结

本项目通过 Google X-Ray 搜索替代直接爬取 LinkedIn，实现低成本、低风险的候选人发现，并通过规则打分提高 recruiter 初筛效率。

---
