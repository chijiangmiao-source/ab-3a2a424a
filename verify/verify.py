"""一次性验收服务：对 Web 与 API 做端到端验收，完成后自行退出。

退出码：0 全部通过；1 存在失败项。

验收内容：
  1. API /health
  2. Web 根页面与经 nginx 代理的 /api/health、/api/sample
  3. /api/audit 成功算例：用本文件内独立实现的穷举器核对
     规范方案（总代价、反射数、标识序列）与必选/可选/从不选分类
  4. /api/audit 不可分算例：核对不可区分相对
  5. 输入校验（422）：重复标识、非正代价、越界数量
  6. 最大规模（18 相 48 反射）可在时限内返回且方案自洽
"""

from __future__ import annotations

import itertools
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request

API = os.environ.get("AUDIT_API_URL", "http://api:8000")
WEB = os.environ.get("AUDIT_WEB_URL", "http://web:80")
TIMEOUT = 30

failures: list[str] = []
checks = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global checks
    checks += 1
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" -- {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(name + (f": {detail}" if detail else ""))


def get(url: str, allow_error: bool = False):
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        if allow_error:
            return e.code, e.read().decode()
        raise


def post(url: str, body: dict, allow_error: bool = False):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if allow_error:
            return e.code, json.loads(e.read().decode())
        raise


def brute_optimal(phases, reflections, costs, occ):
    """独立于后端的穷举参考实现。返回 (cost,count,ids_tuple,classification)
    或 None（不可分）。"""
    pairs = [(a, b) for a, b in itertools.combinations(range(len(phases)), 2)]
    feasible = []
    for bits in range(1, 1 << len(reflections)):
        chosen = [reflections[j] for j in range(len(reflections)) if bits >> j & 1]
        covers_all = True
        for a, b in pairs:
            if not any(
                (r in occ[phases[a]]) != (r in occ[phases[b]]) for r in chosen
            ):
                covers_all = False
                break
        if covers_all:
            feasible.append(
                (
                    sum(costs[r] for r in chosen),
                    len(chosen),
                    tuple(sorted(chosen)),
                    set(chosen),
                )
            )
    if not feasible:
        return None
    best_cost = min(f[0] for f in feasible)
    best_count = min(f[1] for f in feasible if f[0] == best_cost)
    opt = [f for f in feasible if f[0] == best_cost and f[1] == best_count]
    canonical = min(f[2] for f in opt)
    classification = {}
    for r in reflections:
        in_some = any(r in f[3] for f in opt)
        in_all = all(r in f[3] for f in opt)
        classification[r] = (
            "mandatory" if in_all else "never" if not in_some else "optional"
        )
    return best_cost, best_count, canonical, classification


def make_body(phases, reflections, costs, occ_rows):
    return {
        "phases": [{"id": p} for p in phases],
        "reflections": [{"id": r, "cost": costs[r]} for r in reflections],
        "occurrences": {p: [r for r, on in zip(reflections, row) if on] for p, row in zip(phases, occ_rows)},
    }


def main() -> int:
    # 1. API 健康
    try:
        st, body = get(f"{API}/health")
        check("api /health 200 ok", st == 200 and json.loads(body)["status"] == "ok")
    except Exception as e:  # noqa: BLE001
        check("api /health 200 ok", False, repr(e))
        print("API 不可达，终止后续验收。")
        return finish(1)

    # 2. Web 页面与代理
    try:
        st, html = get(f"{WEB}/")
        check("web / 返回页面", st == 200 and "审计台" in html and 'id="root"' in html)
        st, body = get(f"{WEB}/api/health")
        check("web 经 nginx 代理 /api/health", st == 200 and json.loads(body)["status"] == "ok")
        st, body = get(f"{WEB}/api/sample")
        sample = json.loads(body)
        check("web 代理 /api/sample 结构", st == 200 and len(sample["phases"]) >= 2)
    except Exception as e:  # noqa: BLE001
        check("web 页面/代理", False, repr(e))

    # 3. 穷举交叉核对（固定 + 随机算例）
    random.seed(20260921)
    case_no = 0
    fixed = [
        # 手工算例：A/B/C
        (["A", "B", "C"], ["r1", "r2", "r3"],
         {"r1": 1, "r2": 2, "r3": 1},
         [[1, 1, 0], [0, 1, 0], [0, 0, 1]]),
    ]
    for phases, reflections, costs, rows in fixed:
        case_no += 1
        occ = {p: set(r for r, on in zip(reflections, row) if on) for p, row in zip(phases, rows)}
        expect = brute_optimal(phases, reflections, costs, occ)
        st, res = post(f"{API}/api/audit", make_body(phases, reflections, costs, rows))
        ok = (
            st == 200
            and res["feasible"]
            and (res["total_cost"], res["reflection_count"], tuple(res["canonical_solution"]))
            == expect[:3]
            and res["classification"] == expect[3]
        )
        # 逐对证据自洽
        if ok:
            idx = {r: j for j, r in enumerate(reflections)}
            for e in res["pair_evidence"]:
                ai, bi = phases.index(e["a"]), phases.index(e["b"])
                wit = [r for r in res["canonical_solution"] if rows[ai][idx[r]] != rows[bi][idx[r]]]
                ok = ok and sorted(wit) == sorted(e["witnesses"]) and len(wit) > 0
        check(f"固定算例 {case_no} 与穷举一致", bool(ok),
              f"got {res.get('total_cost')},{res.get('reflection_count')},{res.get('canonical_solution')} expect {expect[:3]}")

    for t in range(12):
        n = random.randint(2, 5)
        m = random.randint(1, 7)
        phases = [f"P{i}" for i in range(n)]
        reflections = [f"h{t:02d}" for t in range(m)]
        costs = {r: random.randint(1, 9) for r in reflections}
        rows = [[random.random() < 0.5 for _ in reflections] for _ in phases]
        occ = {p: set(r for r, on in zip(reflections, row) if on) for p, row in zip(phases, rows)}
        expect = brute_optimal(phases, reflections, costs, occ)
        st, res = post(f"{API}/api/audit", make_body(phases, reflections, costs, rows))
        if expect is None:
            exp_pairs = sorted(
                tuple(sorted((phases[a], phases[b])))
                for a, b in itertools.combinations(range(n), 2)
                if rows[a] == rows[b]
            )
            got_pairs = sorted(tuple(sorted(p)) for p in res["indistinguishable_pairs"])
            check(f"随机算例 {t} 正确报告不可分", st == 200 and not res["feasible"] and got_pairs == exp_pairs,
                  f"{got_pairs} != {exp_pairs}")
        else:
            ok = (
                st == 200
                and res["feasible"]
                and (res["total_cost"], res["reflection_count"], tuple(res["canonical_solution"]))
                == expect[:3]
                and res["classification"] == expect[3]
            )
            check(f"随机算例 {t} 与穷举一致", bool(ok),
                  f"got {(res.get('total_cost'), res.get('reflection_count'), res.get('canonical_solution'))} expect {expect[:3]}")

    # 4. 显式不可分算例
    body = make_body(["X", "Y"], ["q1"], {"q1": 3}, [[1], [1]])
    st, res = post(f"{API}/api/audit", body)
    check("显式不可分算例", st == 200 and not res["feasible"] and res["indistinguishable_pairs"] == [["X", "Y"]])

    # 5. 校验错误
    st, _ = post(f"{API}/api/audit",
                 {"phases": [{"id": "A"}, {"id": "A"}],
                  "reflections": [{"id": "r", "cost": 1}], "occurrences": {}}, allow_error=True)
    check("重复相标识返回 422", st == 422)

    st, _ = post(f"{API}/api/audit",
                 {"phases": [{"id": "A"}, {"id": "B"}],
                  "reflections": [{"id": "r", "cost": 0}], "occurrences": {}}, allow_error=True)
    check("非正代价返回 422", st == 422)

    too_many = {"phases": [{"id": f"P{i}"} for i in range(19)],
                "reflections": [{"id": "r", "cost": 1}], "occurrences": {}}
    st, _ = post(f"{API}/api/audit", too_many, allow_error=True)
    check("19 个相返回 422", st == 422)

    too_many_r = {"phases": [{"id": "A"}, {"id": "B"}],
                  "reflections": [{"id": f"r{i}", "cost": 1} for i in range(49)],
                  "occurrences": {}}
    st, _ = post(f"{API}/api/audit", too_many_r, allow_error=True)
    check("49 个反射返回 422", st == 422)

    st, _ = post(f"{API}/api/audit",
                 {"phases": [{"id": "A"}, {"id": "B"}],
                  "reflections": [{"id": "r", "cost": 1}],
                  "occurrences": {"A": ["nope"]}}, allow_error=True)
    check("出现表引用未知反射返回 422", st == 422)

    # 6. 最大规模与自洽性
    random.seed(42)
    n, m = 18, 48
    phases = [f"Phase-{i:02d}" for i in range(n)]
    reflections = [f"hkl-{j:02d}" for j in range(m)]
    costs = {r: random.randint(1, 1000) for r in reflections}
    rows = [[random.random() < 0.3 for _ in reflections] for _ in phases]
    t0 = time.time()
    st, res = post(f"{API}/api/audit", make_body(phases, reflections, costs, rows))
    dt = time.time() - t0
    ok_size = st == 200 and res["feasible"] and dt < 10
    if ok_size:
        chosen = set(res["canonical_solution"])
        cost_ok = sum(costs[r] for r in chosen) == res["total_cost"]
        all_distinct = all(
            any(rows[a][j] != rows[b][j] for j, r in enumerate(reflections) if r in chosen)
            for a, b in itertools.combinations(range(n), 2)
        )
        cls_ok = set(res["classification"]) == set(reflections) and all(
            v in ("mandatory", "optional", "never") for v in res["classification"].values()
        )
        mand = {r for r, v in res["classification"].items() if v == "mandatory"}
        mand_in_sol = mand <= chosen
        ok_size = cost_ok and all_distinct and cls_ok and mand_in_sol
    check(f"18x48 最大规模 10s 内自洽（实测 {dt:.2f}s）", bool(ok_size))

    return finish(0)


def finish(code: int) -> int:
    print(f"\n验收完成：{checks} 项，失败 {len(failures)} 项。")
    if failures:
        for f in failures:
            print("  - " + f)
        return 1
    print("全部通过。")
    return code


if __name__ == "__main__":
    sys.exit(main())
