"""排水试验校准库容表的解算引擎。

口径
----
设各档位按液位从低到高排列，变量 V_i 为档位 i 对应的库容。空池基准在部分档位
给出等式锚点 V_i = b_i；一次从高档 p 排到低档 q 的试验给出排水量区间::

    L_e <= V_p - V_q <= U_e

再加上库容随液位不降的结构约束::

    V_i <= V_{i+1}

全部约束都可以写成差分约束 x_u - x_v <= w，用最短路径（Bellman-Ford）求解：

* 出现负环即无可行解；
* 档位 i 在所有可行解中一致，当且仅当其上界（参照点 0 到 i 的最短路）与
  下界（i 到参照点 0 的最短路取负）重合，否则标记为待补测并给出可行区间；
* 无解时，取参与任一负环的试验作为候选，按基数递增搜索撤掉后能恢复可行的
  最少一组试验；每个候选组合都用一次独立的 Bellman-Ford 复验；
* 若撤掉全部试验后仍无解，则属于基准/单调性的结构性冲突，撤试验无法修复。
"""

from dataclasses import dataclass, field
from itertools import combinations

EPS = 1e-9
# 诊断搜索的可行性评估上限，防止极端输入下组合爆炸。
EVAL_BUDGET = 4000
MAX_GROUPS = 10


@dataclass(frozen=True)
class Level:
    code: str
    rank: int


@dataclass(frozen=True)
class Baseline:
    level: str
    volume: float


@dataclass(frozen=True)
class ExperimentInput:
    code: str
    from_level: str
    to_level: str
    drain_min: float
    drain_max: float


@dataclass
class _Edge:
    u: int
    v: int
    w: float
    source: tuple = field(default_factory=lambda: ('struct',))


def _bellman_ford(node_count, edges, source=None):
    """返回最短距离与前驱边。source=None 时等价于加入零权重超级源。"""
    inf = float('inf')
    dist = [0.0] * node_count if source is None else [inf] * node_count
    if source is not None:
        dist[source] = 0.0
    predecessor = [None] * node_count
    for _ in range(node_count - 1):
        changed = False
        for edge in edges:
            base = dist[edge.u]
            if base == inf:
                continue
            candidate = base + edge.w
            if candidate < dist[edge.v]:
                dist[edge.v] = candidate
                predecessor[edge.v] = edge
                changed = True
        if not changed:
            break
    relaxed = False
    for edge in edges:
        if dist[edge.u] != inf and dist[edge.u] + edge.w < dist[edge.v] - EPS:
            relaxed = True
            break
    return dist, predecessor, relaxed


def _shortest_paths(node_count, edges, source):
    dist, predecessor, _ = _bellman_ford(node_count, edges, source)
    return dist, predecessor


def _path_edges(predecessor, target):
    """沿前驱链取出一条最短路上的边。"""
    seen = set()
    chain = []
    node = target
    while predecessor[node] is not None and node not in seen:
        seen.add(node)
        edge = predecessor[node]
        chain.append(edge)
        node = edge.u
    return chain


def _is_feasible(node_count, edges, disabled):
    if not disabled:
        _, _, relaxed = _bellman_ford(node_count, edges)
        return not relaxed
    active = [edge for edge in edges if edge.source[0] != 'exp' or edge.source[1] not in disabled]
    _, _, relaxed = _bellman_ford(node_count, active)
    return not relaxed


def _all_experiment_codes(edges):
    return sorted({edge.source[1] for edge in edges if edge.source[0] == 'exp'})


def _tarjan_scc(node_count, adjacency):
    """迭代版 Tarjan，返回每个节点的 SCC 编号。"""
    index = 0
    indices = [-1] * node_count
    low = [0] * node_count
    stack = []
    on_stack = [False] * node_count
    component = [-1] * node_count
    component_count = 0

    for root in range(node_count):
        if indices[root] != -1:
            continue
        work = [(root, 0)]
        while work:
            node, cursor = work[-1]
            if cursor == 0:
                indices[node] = low[node] = index
                index += 1
                stack.append(node)
                on_stack[node] = True
            neighbors = adjacency[node]
            if cursor < len(neighbors):
                work[-1] = (node, cursor + 1)
                nxt = neighbors[cursor]
                if indices[nxt] == -1:
                    work.append((nxt, 0))
                elif on_stack[nxt]:
                    low[node] = min(low[node], indices[nxt])
            else:
                if low[node] == indices[node]:
                    while True:
                        member = stack.pop()
                        on_stack[member] = False
                        component[member] = component_count
                        if member == node:
                            break
                    component_count += 1
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[node])
    return component, component_count


def _negative_components(node_count, edges, dist):
    """在紧边/违例边构成的图上找含负环的 SCC，及 SCC 内部的边。"""
    adjacency = [[] for _ in range(node_count)]
    for edge in edges:
        if dist[edge.u] != float('inf') and dist[edge.u] + edge.w <= dist[edge.v] + EPS:
            adjacency[edge.u].append(edge.v)
    component, component_count = _tarjan_scc(node_count, adjacency)
    negative = set()
    internal = {cid: [] for cid in range(component_count)}
    for edge in edges:
        if component[edge.u] == -1 or component[edge.u] != component[edge.v]:
            continue
        internal[component[edge.u]].append(edge)
        if dist[edge.u] + edge.w < dist[edge.v] - EPS:
            negative.add(component[edge.u])
    return component, negative, internal


def _minimum_removals(node_count, edges, candidates):
    """按基数递增搜索撤掉后恢复可行的最少试验组，返回（组列表，是否触发预算兜底）。"""
    evals = 0
    groups = []
    ordered = sorted(candidates)
    for size in range(1, len(ordered) + 1):
        for combo in combinations(ordered, size):
            evals += 1
            if evals > EVAL_BUDGET:
                if groups:
                    return groups, True
                return _greedy_removal(node_count, edges, ordered), True
            if _is_feasible(node_count, edges, set(combo)):
                groups.append(list(combo))
                if len(groups) >= MAX_GROUPS:
                    return groups, False
        if groups:
            return groups, False
    return groups, False


def _greedy_removal(node_count, edges, candidates):
    """组合预算不足时的贪心兜底：每次优先撤掉能直接恢复可行的试验。"""
    remaining = set(candidates)
    chosen = []
    while remaining and not _is_feasible(node_count, edges, set(chosen)):
        best = None
        for code in sorted(remaining):
            if _is_feasible(node_count, edges, set(chosen) | {code}):
                best = code
                break
        if best is None:
            best = sorted(remaining)[0]
        chosen.append(best)
        remaining.discard(best)
    return [chosen] if _is_feasible(node_count, edges, set(chosen)) else []


def validate_inputs(levels, baselines, experiments):
    codes = [item.code for item in levels]
    if len(codes) != len(set(codes)):
        raise ValueError('档位编号不能重复')
    ranks = [item.rank for item in levels]
    if len(ranks) != len(set(ranks)):
        raise ValueError('档位排序不能重复')
    rank_of = {item.code: item.rank for item in levels}
    baseline_levels = set()
    for item in baselines:
        if item.level not in rank_of:
            raise ValueError(f'空池基准引用了未知档位 {item.level}')
        if item.volume < 0:
            raise ValueError('空池基准库容不能为负')
        baseline_levels.add(item.level)
    seen = set()
    for item in experiments:
        if item.code in seen:
            raise ValueError(f'试验编号 {item.code} 重复')
        seen.add(item.code)
        if item.from_level not in rank_of or item.to_level not in rank_of:
            raise ValueError(f'试验 {item.code} 引用了未知档位')
        if rank_of[item.from_level] <= rank_of[item.to_level]:
            raise ValueError(f'试验 {item.code} 必须从较高档位排到较低档位')
        if item.drain_min < 0 or item.drain_max < item.drain_min:
            raise ValueError(f'试验 {item.code} 的排水量区间不合法')
    return rank_of, baseline_levels


def solve(levels, baselines, experiments):
    """求解一次校准，返回可直接序列化的结果字典。"""
    rank_of, baseline_levels = validate_inputs(levels, baselines, experiments)
    ordered = sorted(levels, key=lambda item: item.rank)
    index = {item.code: idx + 1 for idx, item in enumerate(ordered)}
    node_count = len(ordered) + 1  # 0 号为库容参照点（V_0 = 0）
    edges = []

    for pos in range(1, len(ordered)):
        # V_{pos-1} <= V_pos  =>  V_{pos-1} - V_pos <= 0，边 pos -> pos-1
        edges.append(_Edge(pos + 1, pos, 0.0, ('mono',)))
    for item in baselines:
        node = index[item.level]
        edges.append(_Edge(0, node, item.volume, ('base', item.level)))
        edges.append(_Edge(node, 0, -item.volume, ('base', item.level)))
    for item in experiments:
        high, low = index[item.from_level], index[item.to_level]
        edges.append(_Edge(low, high, item.drain_max, ('exp', item.code)))
        edges.append(_Edge(high, low, -item.drain_min, ('exp', item.code)))

    dist, _, relaxed = _bellman_ford(node_count, edges)
    if relaxed:
        return _diagnose(node_count, edges, ordered, dist)

    upper, upper_pred = _shortest_paths(node_count, edges, 0)
    reverse_edges = [_Edge(edge.v, edge.u, edge.w, edge.source) for edge in edges]
    to_ref, ref_pred = _shortest_paths(node_count, reverse_edges, 0)

    rows = []
    for item in ordered:
        node = index[item.code]
        max_volume = upper[node]
        min_volume = None if to_ref[node] == float('inf') else -to_ref[node]
        evidence = set()
        for edge in _path_edges(upper_pred, node):
            if edge.source[0] == 'exp':
                evidence.add(edge.source[1])
        if min_volume is not None:
            for edge in _path_edges(ref_pred, node):
                if edge.source[0] == 'exp':
                    evidence.add(edge.source[1])
        anchored = item.code in baseline_levels
        if anchored:
            volume = next(b.volume for b in baselines if b.level == item.code)
            status = 'confirmed'
            min_volume = max_volume = volume
        elif min_volume is not None and max_volume != float('inf') and max_volume - min_volume <= EPS:
            volume = round((min_volume + max_volume) / 2, 6)
            status = 'confirmed'
        else:
            volume = None
            status = 'pending'
        rows.append({
            'level': item.code, 'rank': item.rank, 'status': status,
            'volume': volume,
            'min_volume': None if min_volume is None else round(min_volume, 6),
            'max_volume': None if max_volume == float('inf') else round(max_volume, 6),
            'anchored': anchored, 'evidence': sorted(evidence),
        })

    confirmed = [row for row in rows if row['status'] == 'confirmed']
    return {
        'feasible': True,
        'rows': rows,
        'confirmed_count': len(confirmed),
        'pending_count': len(rows) - len(confirmed),
        'experiment_count': len(experiments),
        'diagnosis': None,
    }


def _diagnose(node_count, edges, ordered, dist):
    component, negative, internal = _negative_components(node_count, edges, dist)
    level_by_index = {idx + 1: item.code for idx, item in enumerate(ordered)}
    all_codes = set(_all_experiment_codes(edges))

    # 结构性冲突：撤掉全部试验后仍无解，说明基准或单调性本身自相矛盾。
    structural = not _is_feasible(node_count, edges, set(all_codes))

    structural_components = []
    cycle_levels = set()
    for cid in negative:
        exp_codes = {edge.source[1] for edge in internal[cid] if edge.source[0] == 'exp'}
        for edge in internal[cid]:
            if edge.v != 0:
                cycle_levels.add(level_by_index[edge.v])
            if edge.u != 0:
                cycle_levels.add(level_by_index[edge.u])
        if not exp_codes:
            structural_components.append(sorted(
                level_by_index[node] for node in range(1, node_count) if component[node] == cid))

    diagnosis = {
        'negative_levels': sorted(cycle_levels,
                                  key=lambda code: next(item.rank for item in ordered if item.code == code)),
        'structural': structural,
        'structural_components': structural_components,
        'candidate_experiments': sorted(all_codes),
        'removal_groups': [],
        'budget_limited': False,
    }

    if structural:
        return _blocked_result(edges, ordered, diagnosis)

    # 最小击中集的成员可能不在当前负环上（环外试验可构成更小的撤试组），
    # 因此以全部试验为候选做基数递增搜索；EVAL_BUDGET 限制评估次数，超限走贪心兜底。
    groups, budget_limited = _minimum_removals(node_count, edges, all_codes)
    diagnosis['removal_groups'] = groups
    diagnosis['budget_limited'] = budget_limited
    return _blocked_result(edges, ordered, diagnosis)


def _blocked_result(edges, ordered, diagnosis):
    rows = [{
        'level': item.code, 'rank': item.rank, 'status': 'blocked',
        'volume': None, 'min_volume': None, 'max_volume': None,
        'anchored': False, 'evidence': [],
    } for item in ordered]
    return {
        'feasible': False,
        'rows': rows,
        'confirmed_count': 0,
        'pending_count': 0,
        'experiment_count': len(_all_experiment_codes(edges)),
        'diagnosis': diagnosis,
    }
