# 同步辐射粉末衍射 · 相区分审计台

同步辐射粉末衍射复核中，多个候选晶相往往只在少数反射上有无差异，逐相挑峰会重复曝光，还可能留下无法区分的候选。本系统把"选哪些诊断反射"建模为精确优化问题：用户在 React 页面编辑候选相、诊断反射、预期出现关系与曝光代价，通过 FastAPI 接口启动审计，系统精确选出能区分**每一对**候选相的反射集。

## 优化目标（依次裁决）

1. **最小化总曝光代价**（所选反射代价之和）；
2. 在最小代价下**最小化反射数量**；
3. 前两级仍并列时，按**反射标识排序序列的字典序最小者**确定规范方案（确定性、可复算）。

同时标出每个反射在**全部前两级同优方案**中的角色：

| 角色 | 含义 |
| --- | --- |
| 必选（mandatory） | 出现在所有同优方案中 |
| 可选（optional） | 出现在部分同优方案中 |
| 从不选（never） | 不出现在任何同优方案中 |

若全集仍不能区分所有候选相，接口返回不可区分相对，页面保留输入并展示这些相对；成功时页面以矩阵高亮规范方案与分类，并给出每相在规范方案上的出现位编码与逐对区分证据，代价与证据均可复算。

## 输入约束

- 候选相 2–18 个，反射 1–48 个；
- 相标识、反射标识各自唯一且非空；
- 曝光代价为正整数（严格校验，拒绝 0、负数、小数、字符串、布尔）；
- 出现关系矩阵必须完整覆盖所有 相×反射；
- 两相被区分 ⟺ 存在某个所选反射，使两相在其上的出现位不同。

## 快速开始（Docker）

```bash
docker compose up --build
```

- Web 页面：<http://localhost:8080>
- API 文档（Swagger UI）：<http://localhost:8000/docs>
- 健康检查：`GET /api/health`

宿主机端口可通过环境变量或 `.env` 配置（见 `.env.example`）：

```bash
WEB_PORT=9000 API_PORT=9001 docker compose up --build
```

### 一次性验收服务 verify

`verify` 是一次性服务：等待 web/api 健康后执行端到端验收（健康检查、固定用例精确期望值、不可行用例、15 组 422 校验用例、多组随机用例与穷举参考实现交叉核对、证据可复算性），完成后自行退出并以退出码报告结果（0 通过 / 1 失败）。

```bash
# 随整体启动跑一次验收后自动退出
docker compose up --build

# CI 模式：以 verify 的退出码作为命令退出码，验收结束即整体停止
docker compose up --build --abort-on-container-exit --exit-code-from verify

# 服务已在运行时单独重跑验收
docker compose run --rm verify
```

## API

### `GET /api/health`

返回 `{"status": "ok"}`。

### `POST /api/audit`

请求体：

```json
{
  "phases": ["P1", "P2", "P3", "P4"],
  "reflections": [{"id": "R1", "cost": 1}, {"id": "R2", "cost": 4}],
  "occurrence": {
    "P1": {"R1": true,  "R2": true},
    "P2": {"R1": true,  "R2": false},
    "P3": {"R1": false, "R2": true},
    "P4": {"R1": false, "R2": false}
  }
}
```

可行时响应（`200`）：

```json
{
  "status": "feasible",
  "totalCost": 5,
  "reflectionCount": 2,
  "canonicalReflections": ["R1", "R2"],
  "classification": {"R1": "mandatory", "R2": "optional"},
  "codes": {"P1": "11", "P2": "10", "P3": "01", "P4": "00"},
  "pairs": [{"a": "P1", "b": "P2", "reflections": ["R2"]}],
  "indistinguishablePairs": [],
  "stats": {"nodes": 38, "decisionCalls": 14, "elapsedMs": 0.3}
}
```

不可行时响应（`200`）：`status = "infeasible"` 且 `indistinguishablePairs` 列出全集下出现位完全相同的相对。输入非法时返回 `422` 及逐条错误信息。

## 求解方法

把至多 C(18,2)=153 个"候选相对"视为待覆盖元素，每个反射覆盖其出现位不同的相对，问题化为**精确最小权集合覆盖**：

- 以"是否存在代价 ≤ C 且数量 ≤ K 的可行覆盖"的决策型分支限界为核心，配合贪心初始上界与对代价、数量的二分搜索求出前两级最优值；
- 下界：未覆盖对数 / 单反射最大覆盖数，与 ⌈log₂(最大等价类大小)⌉ 取强；代价下界取剩余最便宜的 k 个反射之和；
- 规范方案：按标识升序"能选则选"，逐步以决策问题判定，可证明得到排序标识序列字典序最小的最优解；
- 角色分类：对每个反射分别求解"强制包含 / 强制排除"后是否仍可达前两级最优，无需枚举全部方案即可判定必选 / 可选 / 从不选。

正确性由 `backend/tests/` 中与独立穷举实现交叉核对的测试保证（含随机用例）。

## 本地开发

```bash
# 后端（Python 3.11+）
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
pytest                      # 求解器单元测试（穷举交叉核对）
uvicorn app.main:app --reload --port 8000

# 前端（Node 20+）
cd frontend
npm ci
npm run dev                 # 开发服务器已配置 /api 代理到 :8000
```

## 项目结构

```
├── docker-compose.yml      # web / api / verify 三服务编排，含健康检查与可配置端口
├── .env.example            # WEB_PORT / API_PORT 配置样例
├── backend/
│   ├── Dockerfile          # FastAPI + uvicorn 镜像
│   ├── app/
│   │   ├── main.py         # 路由：/api/health、/api/audit
│   │   ├── schemas.py      # 请求/响应模型与输入校验
│   │   └── solver.py       # 精确分支限界求解器
│   └── tests/test_solver.py
├── frontend/
│   ├── Dockerfile          # 多阶段：vite 构建 → nginx 托管
│   ├── nginx.conf          # 静态资源 + /api 反向代理
│   └── src/                # React 单页应用（编辑器 / 矩阵 / 结果视图）
└── verify/
    └── verify.py           # 一次性验收服务（stdlib，退出码报告结果）
```
