# 同步辐射粉末衍射复核 · 全栈审计台

在 React 页面编辑候选晶相、诊断反射、预期出现关系与曝光代价，经真实 FastAPI
接口精确选择**能区分每对候选相的反射集**：依次最小化总曝光代价、反射数，
再按反射标识序列裁决规范方案；并标出在全部前两级（代价、数量）同优方案中
**必选 / 可选 / 从不选**的反射。

## 判定规则

- 一次输入含 **2–18 个候选相**与 **1–48 个反射**，相、反射标识各自唯一，
  曝光代价为正整数。
- 两相仅当在某个所选反射上的**出现位不同**（一相出现、另一相不出现）时，
  才算被该反射区分。
- 若全部反射仍不能区分所有候选对，接口返回 200 与不可区分相对列表，
  页面保留输入并展示这些相对。

## 优化目标（字典序）

1. 选中反射的总曝光代价最小；
2. 总代价打平时，反射数最少；
3. 前两级都打平时，取选中反射标识排序序列字典序最小的规范方案。

分类在**所有前两级同优方案**上统计（标识序列仅用于选规范代表，不影响分类）：

| 分类 | 含义 |
| --- | --- |
| 必选 mandatory | 每个前两级同优方案都包含 |
| 可选 optional | 部分同优方案包含、部分不包含 |
| 从不选 never | 没有任何同优方案包含 |

求解器（`backend/app/solver.py`）为带权集合覆盖的精确分支限界 + 记忆化 DP，
单遍搜索同时传播全部同优后缀的选中列并集/交集，无需枚举指数级全部方案；
已用 2000+ 组随机算例与独立穷举器逐案核对。

## 目录结构

```
backend/          FastAPI（/api/audit、/api/health、/api/sample）+ 精确求解器
web/              React + Vite 前端，nginx 镜像内同源代理 /api
verify/           一次性验收服务（独立穷举交叉核对，退出码报告结果）
docker-compose.yml
```

## 启动（Docker Compose）

```bash
cp .env.example .env        # 可选：调整宿主机端口
docker compose up -d --build
```

- Web：http://localhost:${WEB_HOST_PORT:-8080}
- API：http://localhost:${API_HOST_PORT:-8000} （健康检查 `/health`、`/api/health`）

宿主机端口可通过环境变量配置，例如：

```bash
WEB_HOST_PORT=9090 API_HOST_PORT=9000 docker compose up -d
```

Web 与 API 容器均带 HEALTHCHECK；Web 依赖 API 健康后才启动。

## 一次性验收服务 verify

`verify` 服务启动后执行端到端验收，**完成后自行退出**，并以退出码报告：
`0` 全部通过，`1` 存在失败项。

```bash
docker compose up --build verify
# 查看退出码：
docker compose ps verify        # Exited (0)
docker inspect audit-verify --format '{{.State.ExitCode}}'
```

验收内容：API/Web 健康与代理、固定与 12 组随机算例对独立穷举器的规范方案与
三分类核对、不可区分相对、5 类 422 校验、18×48 最大规模 10 秒内自洽
（代价复算、逐对区分、必选列均在规范方案内）。

## 接口示例

`POST /api/audit`

```json
{
  "phases": [{"id": "Quartz"}, {"id": "Cristobalite"}],
  "reflections": [{"id": "R1", "cost": 2}, {"id": "R2", "cost": 3}],
  "occurrences": {"Quartz": ["R1", "R2"], "Cristobalite": ["R2"]}
}
```

成功响应含 `canonical_solution`、`total_cost`、`reflection_count`、
`classification`、`pair_evidence`（每对相对的见证反射）、矩阵与搜索统计；
不可分时 `feasible=false` 且 `indistinguishable_pairs` 列出全部不可区分相对。

## 本地开发（无 Docker）

```bash
# 后端
python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.txt
( cd backend && uvicorn app.main:app --reload --port 8000 )

# 前端（vite.config.js 已将 /api 代理到 127.0.0.1:8000）
cd web && npm install && npm run dev
```
