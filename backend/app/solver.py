"""精确求解：选择可区分所有候选晶相对的最小代价反射集。

一个反射 j 能区分相 (p, q)，当且仅当两相在该反射上的出现位不同（一个出现、
另一个不出现）。因此问题等价于带权集合覆盖：每个反射覆盖它所能区分的全部
"相-相对"，必须覆盖所有 C(n,2) 个相对。

目标按字典序最小化：
    1. 总曝光代价 sum(cost)
    2. 反射数 |S|
    3. 选中反射标识组成的有序序列（字符串字典序）

分类（在全部前两级同优方案上）：
    mandatory 必选：每个最优方案都包含
    optional  可选：有的最优方案包含、有的不包含
    never     从不选：没有任何最优方案包含

实现为单遍分支限界 + 状态记忆化：每次选择"当前可覆盖它的未选反射最少"的
未覆盖相对进行分支；下界用贪心构造的"互不可由同一反射覆盖"相对族（族内
每个相对需要不同的反射，故代价与数量下界均可采纳）。

关键：每个记忆状态除返回规范后缀外，还同时汇总"所有前两级同优后缀"中
被选反射列的并集与交集。根状态一次自底向上传播即可同时得到规范方案与
必选/可选/从不分类，无需对每个反射重复搜索，也不会枚举指数级全部方案。
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Sequence, Tuple

# 记忆状态记录：
#   (附加代价, 附加反射数, 规范标识后缀, 并集列掩码, 交集列掩码)
_Record = Tuple[int, int, Tuple[str, ...], int, int]


class SolveFailure(Exception):  # pragma: no cover - 仅用于理论上的内部异常
    pass


def _merge(cid: str, suffix: Tuple[str, ...]) -> Tuple[str, ...]:
    """把单个标识插入已排序的后缀元组。"""
    out: List[str] = []
    placed = False
    for x in suffix:
        if not placed and cid <= x:
            out.append(cid)
            placed = True
        out.append(x)
    if not placed:
        out.append(cid)
    return tuple(out)


class _Instance:
    def __init__(
        self,
        reflection_ids: Sequence[str],
        costs: Dict[str, int],
        cover: List[int],
        pair_index: Dict[Tuple[int, int], int],
    ) -> None:
        self.ids = list(reflection_ids)
        self.cost = [costs[r] for r in self.ids]
        self.cover = cover
        self.m = len(self.ids)
        self.pair_index = pair_index
        self.M = len(pair_index)
        self.all_pairs = (1 << self.M) - 1
        # pair -> 覆盖它的反射列
        self.pair_cols: List[List[int]] = [[] for _ in range(self.M)]
        for j, mask in enumerate(cover):
            mm = mask
            while mm:
                b = mm & -mm
                self.pair_cols[b.bit_length() - 1].append(j)
                mm ^= b
        # pair -> 与它"可能被同一反射同时覆盖"的所有相对（含自身）
        self.share: List[int] = [0] * self.M
        for mask in cover:
            mm = mask
            while mm:
                b = mm & -mm
                k = b.bit_length() - 1
                self.share[k] |= mask
                mm ^= b

    def lower_bound(self, uncovered: int) -> Tuple[int, int]:
        """可采纳的 (附加代价, 附加反射数) 下界。

        贪心取一个相对族：族中任意两个相对都不能由同一个反射同时覆盖
        （每选一个相对 p，就删掉与 p 共享某反射的全部相对）。族中每个
        相对都需要互不相同的选中反射，因此最小代价之和、族大小均为
        合法下界。按最小覆盖代价升序抽取以收紧代价下界。
        """
        min_cost: Dict[int, int] = {}
        order: List[int] = []
        pending = uncovered
        while pending:
            b = pending & -pending
            k = b.bit_length() - 1
            best: Optional[int] = None
            for c in self.pair_cols[k]:
                if best is None or self.cost[c] < best:
                    best = self.cost[c]
            min_cost[k] = best if best is not None else 1 << 30
            order.append(k)
            pending ^= b
        order.sort(key=lambda k: min_cost[k])
        remain = uncovered
        lb_cost = 0
        lb_count = 0
        for k in order:
            bit = 1 << k
            if remain & bit:
                lb_cost += min_cost[k]
                lb_count += 1
                remain &= ~self.share[k]
        return lb_cost, lb_count


class _Solver:
    def __init__(self, inst: _Instance) -> None:
        self.inst = inst
        self.nodes = 0
        self.memo: Dict[Tuple[int, int, int], Optional[_Record]] = {}

    def search(
        self,
        covered: int,
        budget_cost: int,
        budget_count: int,
    ) -> Optional[_Record]:
        """在附加代价 <= budget_cost、附加数 <= budget_count 的前提下，
        返回最优记录；无可行补全返回 None。"""
        if budget_cost < 0 or budget_count < 0:
            return None
        if covered == self.inst.all_pairs:
            return (0, 0, (), 0, 0)
        key = (covered, budget_cost, budget_count)
        if key in self.memo:
            return self.memo[key]
        self.nodes += 1

        uncovered = self.inst.all_pairs & ~covered
        lb_c, lb_n = self.inst.lower_bound(uncovered)
        if lb_c > budget_cost or lb_n > budget_count:
            self.memo[key] = None
            return None

        # 分支相对：可覆盖它的反射最少（最难满足）
        pivot_opts: Optional[List[int]] = None
        uu = uncovered
        while uu:
            b = uu & -uu
            k = b.bit_length() - 1
            opts = self.inst.pair_cols[k]
            if not opts:  # pragma: no cover - 全集可分时不会出现
                self.memo[key] = None
                return None
            if pivot_opts is None or len(opts) < len(pivot_opts):
                pivot_opts = opts
                if len(opts) == 1:
                    break
            uu ^= b
        assert pivot_opts is not None

        def order_key(c: int) -> Tuple[int, int, str]:
            new_bits = self.inst.cover[c] & uncovered
            return (self.inst.cost[c], -new_bits.bit_count(), self.inst.ids[c])

        best_level: Optional[Tuple[int, int]] = None
        best_ids: Optional[Tuple[str, ...]] = None
        best_union = 0
        best_inter = 0
        for c in sorted(pivot_opts, key=order_key):
            if self.inst.cost[c] > budget_cost or budget_count < 1:
                continue
            child = self.search(
                covered | self.inst.cover[c],
                budget_cost - self.inst.cost[c],
                budget_count - 1,
            )
            if child is None:
                continue
            cc, cn, cids, c_union, c_inter = child
            cand_level = (self.inst.cost[c] + cc, 1 + cn)
            cand_ids = _merge(self.inst.ids[c], cids)
            # 固定首选 c 时：所有同优后缀都含 c，共同部分为 c ∪ 子交集
            full_union = (1 << c) | c_union
            full_inter = (1 << c) | c_inter
            if best_level is None or cand_level < best_level:
                # 发现更优的前两级：旧家族全部丢弃
                best_level = cand_level
                best_ids = cand_ids
                best_union = full_union
                best_inter = full_inter
            elif cand_level == best_level:
                # 前两级同优：无论标识序列大小都计入分类家族
                best_union |= full_union
                best_inter &= full_inter
                if best_ids is None or cand_ids < best_ids:
                    best_ids = cand_ids

        if best_level is None or best_ids is None:
            self.memo[key] = None
            return None
        record = (best_level[0], best_level[1], best_ids, best_union, best_inter)
        self.memo[key] = record
        return record


def _greedy_cost(inst: _Instance) -> int:
    """构造一个可行覆盖，返回其代价作为初始上界（每步选单位代价新覆盖
    最多的反射）。"""
    covered = 0
    used = [False] * inst.m
    total_cost = 0
    while covered != inst.all_pairs:
        uncovered = inst.all_pairs & ~covered
        best_j = -1
        best_ratio: Optional[float] = None
        for j in range(inst.m):
            if used[j]:
                continue
            gain = (inst.cover[j] & uncovered).bit_count()
            if gain == 0:
                continue
            ratio = gain / inst.cost[j]
            if best_ratio is None or ratio > best_ratio:
                best_ratio, best_j = ratio, j
        if best_j < 0:  # pragma: no cover - 调用方已保证可区分
            raise SolveFailure("greedy reached an uncovered pair")
        used[best_j] = True
        covered |= inst.cover[best_j]
        total_cost += inst.cost[best_j]
    return total_cost


def solve_audit(
    phase_ids: Sequence[str],
    reflection_ids: Sequence[str],
    costs: Dict[str, int],
    occurrences: Dict[str, "frozenset[str]"],
) -> dict:
    """求解审计问题。

    返回结构：
      feasible=False  -> 含 indistinguishable_pairs
      feasible=True   -> 含规范方案、分类、逐对证据与统计信息
    """
    started = time.perf_counter()
    n = len(phase_ids)
    pair_list: List[Tuple[int, int]] = [
        (i, j) for i in range(n) for j in range(i + 1, n)
    ]
    pair_index = {(i, j): k for k, (i, j) in enumerate(pair_list)}

    cover: List[int] = []
    for rid in reflection_ids:
        mask = 0
        for k, (i, j) in enumerate(pair_list):
            if (rid in occurrences[phase_ids[i]]) != (rid in occurrences[phase_ids[j]]):
                mask |= 1 << k
        cover.append(mask)

    indistinguishable = [
        [phase_ids[i], phase_ids[j]]
        for k, (i, j) in enumerate(pair_list)
        if not any((cover[c] >> k) & 1 for c in range(len(cover)))
    ]

    matrix = [
        [rid in occurrences[pid] for rid in reflection_ids]
        for pid in phase_ids
    ]

    if indistinguishable:
        return {
            "feasible": False,
            "phase_ids": list(phase_ids),
            "reflection_ids": list(reflection_ids),
            "costs": {rid: costs[rid] for rid in reflection_ids},
            "matrix": matrix,
            "indistinguishable_pairs": indistinguishable,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        }

    inst = _Instance(reflection_ids, costs, cover, pair_index)
    g_cost = _greedy_cost(inst)
    # 代价预算取贪心可行解上界；计数预算放宽到 m——最小代价方案可能由
    # 更多便宜反射组成。
    solver = _Solver(inst)
    root = solver.search(0, g_cost, inst.m)
    assert root is not None, "all pairs coverable but solver found nothing"
    opt_cost, opt_count, opt_tuple, union_mask, inter_mask = root

    classification: Dict[str, str] = {}
    for j, rid in enumerate(inst.ids):
        bit = 1 << j
        in_all = bool(inter_mask & bit)
        in_some = bool(union_mask & bit)
        if in_all:
            classification[rid] = "mandatory"
        elif in_some:
            classification[rid] = "optional"
        else:
            classification[rid] = "never"

    selected = set(opt_tuple)
    pair_evidence: List[dict] = []
    for k, (i, j) in enumerate(pair_list):
        witnesses = [
            inst.ids[c]
            for c in range(inst.m)
            if inst.ids[c] in selected and (inst.cover[c] >> k) & 1
        ]
        pair_evidence.append(
            {
                "a": phase_ids[i],
                "b": phase_ids[j],
                "distinguished": True,
                "witnesses": witnesses,
            }
        )

    return {
        "feasible": True,
        "phase_ids": list(phase_ids),
        "reflection_ids": list(reflection_ids),
        "costs": {rid: costs[rid] for rid in reflection_ids},
        "matrix": matrix,
        "canonical_solution": list(opt_tuple),
        "total_cost": opt_cost,
        "reflection_count": opt_count,
        "classification": classification,
        "pair_evidence": pair_evidence,
        "indistinguishable_pairs": [],
        "search_nodes": solver.nodes,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }
