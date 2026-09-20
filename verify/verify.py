#!/usr/bin/env python3
"""一次性验收服务。

对运行中的 Web 与 API 做端到端验收：
  1. API 与 Web 健康检查（含 Web 对 /api 的反向代理）；
  2. 固定可行用例：核对总代价、反射数、规范方案与必选/可选/从不选分类；
  3. 不可行用例：核对不可区分相对；
  4. 输入校验用例：非法输入必须返回 422；
  5. 随机用例：与脚本内独立的穷举参考实现交叉核对全部结果字段；
  6. 证据可复算：编码两两不同、逐对区分反射非空且确实区分、代价可重算。

全部通过以退出码 0 结束，否则以退出码 1 结束。
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from itertools import combinations

API_URL = os.environ.get("API_URL", "http://api:8000")
WEB_URL = os.environ.get("WEB_URL", "http://web")

passed = 0
failed = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"  [PASS] {name}", flush=True)
    else:
        failed += 1
        print(f"  [FAIL] {name} {detail}", flush=True)


def http_json(method: str, url: str, body: dict | None = None):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def http_text(url: str):
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return resp.status, resp.read().decode()
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def wait_ok(url: str, tries: int = 90) -> bool:
    for _ in range(tries):
        status, _ = http_json("GET", url)
        if status == 200:
            return True
        time.sleep(1)
    return False


# ---------------------------------------------------------------- 穷举参考实现

def brute_force(payload: dict) -> dict:
    """枚举全部反射子集，独立复算最优目标、规范方案与角色分类。"""
    phases = payload["phases"]
    reflections = payload["reflections"]
    occ = payload["occurrence"]
    n, m = len(phases), len(reflections)
    sig = {p: tuple(bool(occ[p][r["id"]]) for r in reflections) for p in phases}
    indist = sorted(
        (a, b) for a, b in combinations(phases, 2) if sig[a] == sig[b]
    )
    if indist:
        return {"status": "infeasible", "indist": indist}
    best = None
    sols = []
    for mask in range(1, 1 << m):
        sel = [i for i in range(m) if mask >> i & 1]
        cost = sum(reflections[i]["cost"] for i in sel)
        key = (cost, len(sel))
        if best is not None and key > best:
            continue
        proj = {tuple(sig[p][i] for i in sel) for p in phases}
        if len(proj) < n:
            continue
        if best is None or key < best:
            best, sols = key, [sel]
        elif key == best:
            sols.append(sel)
    canonical = min(tuple(sorted(reflections[i]["id"] for i in sel)) for sel in sols)
    roles = {}
    for i, r in enumerate(reflections):
        in_any = any(i in sel for sel in sols)
        in_all = all(i in sel for sel in sols)
        roles[r["id"]] = "mandatory" if in_all else ("optional" if in_any else "never")
    return {
        "status": "feasible",
        "cost": best[0],
        "count": best[1],
        "canonical": list(canonical),
        "roles": roles,
    }


def check_evidence(name: str, payload: dict, resp: dict) -> None:
    """核对响应中的证据字段可复算且自洽。"""
    phases = payload["phases"]
    reflections = payload["reflections"]
    occ = payload["occurrence"]
    cost_of = {r["id"]: r["cost"] for r in reflections}
    canon = resp["canonicalReflections"]

    check(f"{name}: 总代价可重算",
          sum(cost_of[r] for r in canon) == resp["totalCost"])
    check(f"{name}: 反射数一致", len(canon) == resp["reflectionCount"])
    check(f"{name}: 编码两两不同",
          len(set(resp["codes"].values())) == len(phases))
    ok_codes = True
    for p in phases:
        expect = "".join("1" if occ[p][r] else "0" for r in canon)
        if resp["codes"].get(p) != expect:
            ok_codes = False
    check(f"{name}: 编码与出现关系一致", ok_codes)

    ok_pairs = True
    seen_pairs = set()
    for ev in resp["pairs"]:
        seen_pairs.add((ev["a"], ev["b"]))
        if not ev["reflections"]:
            ok_pairs = False
            break
        for rid in ev["reflections"]:
            if rid not in canon or occ[ev["a"]][rid] == occ[ev["b"]][rid]:
                ok_pairs = False
                break
    expect_pairs = set(combinations(phases, 2))
    check(f"{name}: 逐对证据有效", ok_pairs)
    check(f"{name}: 逐对证据覆盖全部 {len(expect_pairs)} 对",
          seen_pairs == expect_pairs or seen_pairs == {(b, a) for a, b in expect_pairs})


# ---------------------------------------------------------------- 用例构造

def fixed_case() -> dict:
    present = {
        "R1": {"P1", "P2"},
        "R2": {"P1", "P3"},
        "R3": {"P2", "P3"},
        "R4": set(),
        "R5": {"P1", "P2", "P3"},
    }
    phases = ["P1", "P2", "P3", "P4"]
    rids = ["R1", "R2", "R3", "R4", "R5"]
    costs = [1, 4, 4, 1, 9]
    return {
        "phases": phases,
        "reflections": [{"id": r, "cost": c} for r, c in zip(rids, costs)],
        "occurrence": {p: {r: p in present[r] for r in rids} for p in phases},
    }


def random_case(seed: int, n: int, m: int, max_cost: int) -> dict:
    rng = random.Random(seed)
    phases = [f"Ph{i}" for i in range(n)]
    rids = [f"R{j:02d}" for j in range(m)]
    occ = {p: {r: rng.random() < 0.5 for r in rids} for p in phases}
    return {
        "phases": phases,
        "reflections": [{"id": r, "cost": rng.randint(1, max_cost)} for r in rids],
        "occurrence": occ,
    }


def infeasible_case() -> dict:
    return {
        "phases": ["A", "B", "C", "D"],
        "reflections": [{"id": "X1", "cost": 3}, {"id": "X2", "cost": 5}],
        "occurrence": {
            "A": {"X1": True, "X2": False},
            "B": {"X1": False, "X2": False},
            "C": {"X1": False, "X2": False},
            "D": {"X1": True, "X2": True},
        },
    }


def invalid_cases() -> list[tuple[str, dict]]:
    base = {
        "phases": ["A", "B"],
        "reflections": [{"id": "R1", "cost": 1}],
        "occurrence": {"A": {"R1": True}, "B": {"R1": False}},
    }

    def clone(**kw):
        c = json.loads(json.dumps(base))
        c.update(kw)
        return c

    many_phases = [f"P{i}" for i in range(19)]
    many_refl = [{"id": f"R{i}", "cost": 1} for i in range(49)]
    return [
        ("仅 1 个候选相", clone(phases=["A"], occurrence={"A": {"R1": True}})),
        ("19 个候选相", clone(phases=many_phases,
                              occurrence={p: {"R1": i % 2 == 0} for i, p in enumerate(many_phases)})),
        ("0 个反射", clone(reflections=[], occurrence={"A": {}, "B": {}})),
        ("49 个反射", clone(reflections=many_refl,
                            occurrence={p: {r["id"]: (i + k) % 2 == 0
                                            for k, r in enumerate(many_refl)}
                                        for i, p in enumerate(["A", "B"])})),
        ("候选相标识重复", clone(phases=["A", "A"], occurrence={"A": {"R1": True}})),
        ("反射标识重复", clone(reflections=[{"id": "R1", "cost": 1}, {"id": "R1", "cost": 2}],
                               occurrence={"A": {"R1": True}, "B": {"R1": False}})),
        ("代价为 0", clone(reflections=[{"id": "R1", "cost": 0}])),
        ("代价为负", clone(reflections=[{"id": "R1", "cost": -3}])),
        ("代价为小数", clone(reflections=[{"id": "R1", "cost": 1.5}])),
        ("代价为字符串", clone(reflections=[{"id": "R1", "cost": "5"}])),
        ("代价为布尔", clone(reflections=[{"id": "R1", "cost": True}])),
        ("空相标识", clone(phases=["", "B"], occurrence={"": {"R1": True}, "B": {"R1": False}})),
        ("缺少相的出现关系行", clone(occurrence={"A": {"R1": True}})),
        ("出现关系缺少反射", clone(occurrence={"A": {"R1": True}, "B": {}})),
        ("出现关系含未知相", clone(occurrence={"A": {"R1": True}, "B": {"R1": False},
                                               "Z": {"R1": True}})),
    ]


# ---------------------------------------------------------------- 主流程

def main() -> int:
    print(f"验收目标: API={API_URL} WEB={WEB_URL}", flush=True)

    print("[1/6] 健康检查", flush=True)
    check("API /api/health 就绪", wait_ok(f"{API_URL}/api/health"))
    status, body = http_json("GET", f"{API_URL}/api/health")
    check("API 健康响应内容", status == 200 and body.get("status") == "ok")
    web_ok = False
    for _ in range(90):
        status, text = http_text(f"{WEB_URL}/")
        if status == 200:
            web_ok = True
            break
        time.sleep(1)
    check("Web 页面可访问", web_ok)
    if web_ok:
        check("Web 返回单页应用 HTML", 'id="root"' in text and "<title>" in text)
    status, body = http_json("GET", f"{WEB_URL}/api/health")
    check("Web 反向代理 /api/health", status == 200 and isinstance(body, dict) and body.get("status") == "ok")

    print("[2/6] 固定可行用例（精确期望值）", flush=True)
    payload = fixed_case()
    status, resp = http_json("POST", f"{API_URL}/api/audit", payload)
    check("固定用例返回 200", status == 200, f"实际 {status}")
    if status == 200:
        check("状态 feasible", resp.get("status") == "feasible")
        check("总曝光代价 = 5", resp.get("totalCost") == 5, f"实际 {resp.get('totalCost')}")
        check("反射数 = 2", resp.get("reflectionCount") == 2)
        check("规范方案 = [R1, R2]", resp.get("canonicalReflections") == ["R1", "R2"],
              f"实际 {resp.get('canonicalReflections')}")
        check("角色分类正确",
              resp.get("classification") == {"R1": "mandatory", "R2": "optional",
                                             "R3": "optional", "R4": "never", "R5": "never"},
              f"实际 {resp.get('classification')}")
        check("编码正确", resp.get("codes") == {"P1": "11", "P2": "10", "P3": "01", "P4": "00"})
        check_evidence("固定用例", payload, resp)

    print("[3/6] 不可行用例", flush=True)
    payload = infeasible_case()
    status, resp = http_json("POST", f"{API_URL}/api/audit", payload)
    check("不可行用例返回 200", status == 200, f"实际 {status}")
    if status == 200:
        check("状态 infeasible", resp.get("status") == "infeasible")
        check("不可区分相对 = [B↔C]",
              resp.get("indistinguishablePairs") == [{"a": "B", "b": "C"}],
              f"实际 {resp.get('indistinguishablePairs')}")

    print("[4/6] 输入校验用例（均应返回 422）", flush=True)
    for name, bad in invalid_cases():
        status, _ = http_json("POST", f"{API_URL}/api/audit", bad)
        check(f"422: {name}", status == 422, f"实际 {status}")

    print("[5/6] 随机用例 vs 穷举参考", flush=True)
    for seed, n, m, mc in [(20260920, 7, 12, 9), (7, 9, 14, 20), (42, 6, 11, 5)]:
        payload = random_case(seed, n, m, mc)
        expect = brute_force(payload)
        status, resp = http_json("POST", f"{API_URL}/api/audit", payload)
        name = f"seed={seed} {n}相×{m}反射"
        check(f"{name}: 返回 200", status == 200, f"实际 {status}")
        if status != 200:
            continue
        if expect["status"] == "infeasible":
            check(f"{name}: 不可行且相对一致",
                  resp.get("status") == "infeasible"
                  and sorted((d["a"], d["b"]) for d in resp.get("indistinguishablePairs", [])) == expect["indist"],
                  f"实际 {resp.get('status')}")
        else:
            check(f"{name}: 最优代价/数量一致",
                  resp.get("status") == "feasible"
                  and resp.get("totalCost") == expect["cost"]
                  and resp.get("reflectionCount") == expect["count"],
                  f"期望 {(expect['cost'], expect['count'])} 实际 {(resp.get('totalCost'), resp.get('reflectionCount'))}")
            check(f"{name}: 规范方案一致",
                  resp.get("canonicalReflections") == expect["canonical"],
                  f"期望 {expect['canonical']} 实际 {resp.get('canonicalReflections')}")
            check(f"{name}: 角色分类一致",
                  resp.get("classification") == expect["roles"])
            if resp.get("status") == "feasible":
                check_evidence(name, payload, resp)

    print("[6/6] 汇总", flush=True)
    print(f"通过 {passed} 项，失败 {failed} 项", flush=True)
    if failed:
        print("验收未通过", flush=True)
        return 1
    print("验收全部通过", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
