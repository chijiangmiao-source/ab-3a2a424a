"""用穷举法对精确求解器做交叉校验。"""

from __future__ import annotations

import itertools
import random

from app.solver import run_audit


def brute_force(phases, reflection_ids, costs, occurrence):
    """枚举全部子集，返回 (最优(代价,数量), 规范方案, 角色, 不可区分相对)。"""
    n, m = len(phases), len(reflection_ids)
    sig = [tuple(occurrence[p][r] for r in range(m)) for p in range(n)]
    indist = [(phases[i], phases[j])
              for i in range(n) for j in range(i + 1, n) if sig[i] == sig[j]]
    if indist:
        return None, None, None, indist
    best = None
    sols = []
    for mask in range(1, 1 << m):
        sel = [r for r in range(m) if mask >> r & 1]
        cost = sum(costs[r] for r in sel)
        key = (cost, len(sel))
        if best is not None and key > best:
            continue
        proj = {tuple(sig[p][r] for r in sel) for p in range(n)}
        if len(proj) < n:
            continue
        if best is None or key < best:
            best, sols = key, [sel]
        elif key == best:
            sols.append(sel)
    canonical = min(tuple(sorted(reflection_ids[r] for r in sel)) for sel in sols)
    roles = {}
    for r in range(m):
        in_any = any(r in sel for sel in sols)
        in_all = all(r in sel for sel in sols)
        roles[reflection_ids[r]] = "mandatory" if in_all else ("optional" if in_any else "never")
    return best, list(canonical), roles, []


def cross_check(phases, reflection_ids, costs, occurrence):
    res = run_audit(phases, reflection_ids, costs, occurrence)
    best, canonical, roles, indist = brute_force(phases, reflection_ids, costs, occurrence)
    if indist:
        assert not res.feasible
        assert {(d["a"], d["b"]) for d in res.indistinguishable} == set(indist)
        return
    assert res.feasible
    assert (res.total_cost, res.reflection_count) == best
    assert res.canonical == canonical
    assert res.roles == roles
    # 证据可复算：编码互不相同，且每对区分反射非空、确实能区分该对
    assert len(set(res.codes.values())) == len(phases)
    canon = res.canonical
    for ev in res.pairs:
        assert ev["reflections"]
        ia, ib = phases.index(ev["a"]), phases.index(ev["b"])
        for rid in ev["reflections"]:
            r = reflection_ids.index(rid)
            assert occurrence[ia][r] != occurrence[ib][r]
        assert set(ev["reflections"]) <= set(canon)
    assert res.total_cost == sum(costs[reflection_ids.index(r)] for r in canon)
    assert res.reflection_count == len(canon)


def test_fixed_case_with_mandatory_and_never():
    phases = ["P1", "P2", "P3", "P4"]
    reflection_ids = ["R1", "R2", "R3", "R4", "R5"]
    costs = [1, 4, 4, 1, 9]
    present = {
        "R1": {"P1", "P2"},
        "R2": {"P1", "P3"},
        "R3": {"P2", "P3"},
        "R4": set(),
        "R5": {"P1", "P2", "P3"},
    }
    occurrence = [[p in present[r] for r in reflection_ids] for p in phases]
    res = run_audit(phases, reflection_ids, costs, occurrence)
    assert res.feasible
    assert (res.total_cost, res.reflection_count) == (5, 2)
    assert res.canonical == ["R1", "R2"]
    assert res.roles == {
        "R1": "mandatory", "R2": "optional", "R3": "optional",
        "R4": "never", "R5": "never",
    }
    assert res.codes == {"P1": "11", "P2": "10", "P3": "01", "P4": "00"}


def test_infeasible_reports_all_identical_pairs():
    phases = ["A", "B", "C", "D"]
    reflection_ids = ["X1", "X2"]
    costs = [3, 5]
    occurrence = [
        [True, False],   # A: 10
        [False, False],  # B: 00
        [False, False],  # C: 00
        [True, True],    # D: 11
    ]
    res = run_audit(phases, reflection_ids, costs, occurrence)
    assert not res.feasible
    assert {(d["a"], d["b"]) for d in res.indistinguishable} == {("B", "C")}


def test_random_small_instances_against_brute_force():
    rng = random.Random(20260920)
    for trial in range(60):
        n = rng.randint(2, 8)
        m = rng.randint(1, 12)
        phases = [f"P{i}" for i in range(n)]
        reflection_ids = [f"R{j}" for j in range(m)]
        costs = [rng.randint(1, 9) for _ in range(m)]
        occurrence = [[rng.random() < 0.5 for _ in range(m)] for _ in range(n)]
        cross_check(phases, reflection_ids, costs, occurrence)


def test_larger_structured_instance():
    # 9 个相、14 个反射：二进制编码 + 噪声反射，验证规模内可解且与穷举一致
    rng = random.Random(7)
    n, m = 9, 14
    phases = [f"Ph{i}" for i in range(n)]
    reflection_ids = [f"Ref{j:02d}" for j in range(m)]
    costs = [rng.randint(1, 20) for _ in range(m)]
    occurrence = []
    for p in range(n):
        row = [bool((p >> b) & 1) for b in range(4)]  # 4 位二进制码保证可区分
        row += [rng.random() < 0.5 for _ in range(m - 4)]
        occurrence.append(row)
    cross_check(phases, reflection_ids, costs, occurrence)
