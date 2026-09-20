"""精确求解诊断反射审计问题。

问题：给定 n 个候选相（2..18）与 m 个诊断反射（1..48，代价为正整数），
每个反射把候选相分成"预期出现 / 预期不出现"两类。一对相被某个反射
区分，当且仅当它们在该反射上的出现位不同。需要选出一个反射集，使
任意两相至少被一个所选反射区分，并依次：

  1. 最小化总曝光代价（所选反射代价之和）；
  2. 在最小代价下最小化反射数量；
  3. 在前两级仍并列时，按反射标识排序后的序列取字典序最小者，
     作为规范方案。

同时给出每个反射在"全部前两级同优方案"中的角色：
  mandatory —— 出现在所有同优方案中（必选）；
  optional  —— 出现在部分同优方案中（可选）；
  never     —— 不出现在任何同优方案中（从不选）。

实现：以"候选相对"为元素的精确集合覆盖。n <= 18 时至多 153 对，
用 Python 大整数作位掩码；通过带截断的决策型分支限界完成：
  - 上界：贪心解 + 对代价/数量分别二分；
  - 下界：未覆盖对数 / 单反射最大覆盖数，与 ceil(log2(最大等价类大小))
    取强；代价下界取剩余最便宜的 k 个反射之和；
  - 规范方案：按标识升序"能选则选"的贪心，逐步用决策问题判定，
    可证明得到排序标识序列字典序最小的最优解；
  - 角色分类：对每个反射分别求解"强制包含 / 强制排除"后是否仍可达
    到前两级最优，从而判定必选 / 可选 / 从不选，无需枚举全部方案。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


class SolverTimeoutError(RuntimeError):
    """分支限界节点数超过预算（防御性限制，正常规模不会触发）。"""


@dataclass
class AuditResult:
    feasible: bool
    total_cost: int = 0
    reflection_count: int = 0
    canonical: list[str] = field(default_factory=list)
    roles: dict[str, str] = field(default_factory=dict)  # id -> mandatory|optional|never
    codes: dict[str, str] = field(default_factory=dict)  # phase -> 规范方案上的出现位串
    pairs: list[dict] = field(default_factory=list)      # 逐对区分证据
    indistinguishable: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


def _ceil_log2(x: int) -> int:
    k = 0
    while (1 << k) < x:
        k += 1
    return k


class _Engine:
    """在一组候选反射索引上回答"是否存在代价<=C 且数量<=K 的可行覆盖"。"""

    def __init__(self, covers: list[int], costs: list[int], universe: int,
                 phase_masks1: list[int], n_phases: int, pairs: list[tuple[int, int]]):
        self.covers = covers            # covers[i]: 反射 i 能区分的"相对"位掩码
        self.costs = costs
        self.universe = universe        # 全部相对的位掩码
        self.phase_masks1 = phase_masks1  # phase_masks1[i]: 在反射 i 上出现位为 1 的相集合
        self.all_phases = (1 << n_phases) - 1
        self.n = n_phases
        self.pairs = pairs
        self.nodes = 0
        self.calls = 0
        self.node_limit = 2_000_000

    def _classes_from_covered(self, covered: int) -> tuple:
        """由已覆盖的相对集合还原等价类划分。

        两相等价 当且仅当 它们之间的相对尚未被覆盖（出现位完全相同），
        该关系具有传递性，因此对"未覆盖相对"图做并查集即得等价类。
        """
        parent = list(range(self.n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        uncovered = self.universe & ~covered
        for k, (i, j) in enumerate(self.pairs):
            if uncovered >> k & 1:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj
        groups: dict[int, int] = {}
        for p in range(self.n):
            r = find(p)
            groups[r] = groups.get(r, 0) | (1 << p)
        return tuple(groups.values())

    def decision(self, idxs: list[int], max_cost: int, max_count: int,
                 forced: tuple[int, ...] = ()) -> list[int] | None:
        """在 forced 已入选的前提下，从 idxs 中补选，返回一个可行解或 None。"""
        if max_cost < 0 or max_count < 0:
            return None
        self.calls += 1
        covers, costs = self.covers, self.costs

        pre_covered = 0
        for i in forced:
            pre_covered |= covers[i]
        target = self.universe & ~pre_covered
        if target == 0:
            return []

        or_all = 0
        for i in idxs:
            or_all |= covers[i]
        if (or_all & target) != target:
            return None

        # 分支顺序：代价升序，同代价按覆盖量降序，再按原始下标，保证确定性。
        order = sorted(idxs, key=lambda i: (costs[i], -covers[i].bit_count(), i))
        m = len(order)
        oc = [covers[i] for i in order]
        ocost = [costs[i] for i in order]
        om1 = [self.phase_masks1[i] for i in order]
        oidx = order

        suffix_or = [0] * (m + 1)
        for p in range(m - 1, -1, -1):
            suffix_or[p] = suffix_or[p + 1] | oc[p]

        def search(pos: int, unc: int, classes: tuple, cost: int, count: int,
                   chosen: list[int]) -> list[int] | None:
            self.nodes += 1
            if self.nodes > self.node_limit:
                raise SolverTimeoutError("求解节点数超限")
            if unc == 0:
                return chosen
            if pos == m or count == max_count:
                return None
            if (suffix_or[pos] & unc) != unc:
                return None
            # 下界 1：未覆盖对数 / 剩余单反射最大覆盖数
            maxcov = 0
            for p in range(pos, m):
                c = (oc[p] & unc).bit_count()
                if c > maxcov:
                    maxcov = c
            k = -(-unc.bit_count() // maxcov)
            # 下界 2：每个反射至多把每个等价类一分为二
            maxclass = 0
            for cmask in classes:
                b = cmask.bit_count()
                if b > maxclass:
                    maxclass = b
            kc = _ceil_log2(maxclass)
            if kc > k:
                k = kc
            if count + k > max_count:
                return None
            # 代价下界：剩余最便宜的 k 个（ocost 沿 order 单调不降）
            if cost + sum(ocost[pos:pos + k]) > max_cost:
                return None

            cov_i = oc[pos]
            if cov_i & unc:
                cost_i = ocost[pos]
                if cost + cost_i <= max_cost:
                    # 包含 order[pos]：更新未覆盖对掩码并细分等价类
                    m1 = om1[pos]
                    m0 = self.all_phases ^ m1
                    new_classes = []
                    for cmask in classes:
                        a = cmask & m0
                        b = cmask & m1
                        if a and b:
                            new_classes.append(a)
                            new_classes.append(b)
                        else:
                            new_classes.append(a if a else b)
                    r = search(pos + 1, unc & ~cov_i, tuple(new_classes),
                               cost + cost_i, count + 1, chosen + [oidx[pos]])
                    if r is not None:
                        return r
            # 排除 order[pos]
            return search(pos + 1, unc, classes, cost, count, chosen)

        return search(0, target, self._classes_from_covered(pre_covered), 0, 0, [])


def _greedy(engine: _Engine, idxs: list[int]) -> list[int]:
    """贪心可行解，为二分提供上界。"""
    uncovered = engine.universe
    chosen: list[int] = []
    available = list(idxs)
    while uncovered:
        best_i, best_key = None, None
        for i in available:
            gain = (engine.covers[i] & uncovered).bit_count()
            if gain == 0:
                continue
            key = (gain, -engine.costs[i])
            if best_key is None or key > best_key:
                best_key, best_i = key, i
        if best_i is None:
            break
        chosen.append(best_i)
        available.remove(best_i)
        uncovered &= ~engine.covers[best_i]
    return chosen


def run_audit(phases: list[str], reflection_ids: list[str], costs: list[int],
              occurrence: list[list[bool]]) -> AuditResult:
    """主入口。

    occurrence[p][r] 为 True 表示相 p 在反射 r 上预期出现。
    """
    t0 = time.perf_counter()
    n, m = len(phases), len(reflection_ids)

    # 相对编号与每个反射的覆盖位掩码
    pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
    universe = (1 << len(pairs)) - 1
    covers = [0] * m
    phase_masks1 = [0] * m
    for r in range(m):
        mask = 0
        pm = 0
        for p in range(n):
            if occurrence[p][r]:
                pm |= 1 << p
        phase_masks1[r] = pm
        for k, (i, j) in enumerate(pairs):
            if occurrence[i][r] != occurrence[j][r]:
                mask |= 1 << k
        covers[r] = mask

    # 可行性：全反射集仍无法区分的相对（全签名相同的相对）
    sig = [0] * n
    for r in range(m):
        for p in range(n):
            if occurrence[p][r]:
                sig[p] |= 1 << r
    indistinguishable = []
    for i, j in pairs:
        if sig[i] == sig[j]:
            indistinguishable.append({"a": phases[i], "b": phases[j]})
    if indistinguishable:
        return AuditResult(
            feasible=False,
            indistinguishable=indistinguishable,
            stats={"elapsedMs": round((time.perf_counter() - t0) * 1000, 3)},
        )

    engine = _Engine(covers, costs, universe, phase_masks1, n, pairs)
    all_idxs = list(range(m))

    # 第一级：最小总代价（贪心给上界，二分下压）
    greedy_sol = _greedy(engine, all_idxs)
    hi = sum(costs[i] for i in greedy_sol)
    lo = 0
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if engine.decision(all_idxs, mid, m) is None:
            lo = mid
        else:
            hi = mid
    best_cost = hi

    # 第二级：最小代价下的最少反射数
    sol = engine.decision(all_idxs, best_cost, m)
    hi = len(sol)
    lo = 0
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if engine.decision(all_idxs, best_cost, mid) is None:
            lo = mid
        else:
            hi = mid
    best_count = hi

    # 第三级：规范方案——按标识升序"能选则选"，得到排序标识序列字典序最小者
    chosen: list[int] = []
    remaining = list(all_idxs)
    spent = 0
    for i in sorted(all_idxs, key=lambda x: reflection_ids[x]):
        rest = [j for j in remaining if j != i]
        if engine.decision(rest, best_cost - spent - costs[i],
                           best_count - len(chosen) - 1,
                           forced=tuple(chosen) + (i,)) is not None:
            chosen.append(i)
            spent += costs[i]
        remaining.remove(i)
    canonical_ids = sorted(reflection_ids[i] for i in chosen)

    # 角色分类：强制包含 / 强制排除后是否仍可达前两级最优
    roles: dict[str, str] = {}
    for i in all_idxs:
        rest = [j for j in all_idxs if j != i]
        included_ok = engine.decision(rest, best_cost - costs[i], best_count - 1,
                                      forced=(i,)) is not None
        if not included_ok:
            roles[reflection_ids[i]] = "never"
        else:
            excluded_ok = engine.decision(rest, best_cost, best_count) is not None
            roles[reflection_ids[i]] = "optional" if excluded_ok else "mandatory"

    # 规范方案上的出现位编码与逐对区分证据
    canon_sorted = sorted(chosen, key=lambda x: reflection_ids[x])
    codes = {}
    for p in range(n):
        codes[phases[p]] = "".join("1" if occurrence[p][r] else "0" for r in canon_sorted)
    pair_evidence = []
    for i, j in pairs:
        diff = [reflection_ids[r] for r in canon_sorted if occurrence[i][r] != occurrence[j][r]]
        pair_evidence.append({"a": phases[i], "b": phases[j], "reflections": diff})

    stats = {
        "nodes": engine.nodes,
        "decisionCalls": engine.calls,
        "elapsedMs": round((time.perf_counter() - t0) * 1000, 3),
    }
    return AuditResult(
        feasible=True,
        total_cost=best_cost,
        reflection_count=best_count,
        canonical=canonical_ids,
        roles=roles,
        codes=codes,
        pairs=pair_evidence,
        stats=stats,
    )
