"""校准引擎的规则测试，使用标准库即可运行：python -I tests/test_calibration.py"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.domain.calibration import Baseline, ExperimentInput, Level, solve

LEVELS = [Level('G1', 1), Level('G2', 2), Level('G3', 3), Level('G4', 4)]


def exp(code, high, low, dmin, dmax=None):
    return ExperimentInput(code, high, low, dmin, dmax if dmax is not None else dmin)


class CalibrationTests(unittest.TestCase):
    def test_exact_chain_confirms_every_level(self):
        result = solve(LEVELS, [Baseline('G1', 0)], [
            exp('T1', 'G2', 'G1', 10), exp('T2', 'G3', 'G2', 15), exp('T3', 'G4', 'G3', 5)])
        self.assertTrue(result['feasible'])
        by_level = {row['level']: row for row in result['rows']}
        self.assertEqual([by_level[f'G{i}']['status'] for i in range(1, 5)], ['confirmed'] * 4)
        self.assertEqual([by_level[f'G{i}']['volume'] for i in range(1, 5)], [0, 10, 25, 30])

    def test_cross_level_experiment_constrains_passed_levels(self):
        result = solve(LEVELS, [Baseline('G1', 0)], [
            exp('T1', 'G4', 'G1', 30), exp('T2', 'G4', 'G3', 5), exp('T3', 'G2', 'G1', 10)])
        self.assertTrue(result['feasible'])
        by_level = {row['level']: row for row in result['rows']}
        self.assertEqual([by_level[f'G{i}']['volume'] for i in range(1, 5)], [0, 10, 25, 30])
        self.assertIn('T1', by_level['G3']['evidence'])

    def test_interval_leaves_intermediate_levels_pending(self):
        result = solve(LEVELS, [Baseline('G1', 0)], [exp('T1', 'G4', 'G1', 28, 32)])
        self.assertTrue(result['feasible'])
        by_level = {row['level']: row for row in result['rows']}
        self.assertEqual(by_level['G1']['status'], 'confirmed')
        self.assertEqual(by_level['G2']['status'], 'pending')
        self.assertEqual(by_level['G3']['status'], 'pending')
        self.assertEqual(by_level['G4']['status'], 'pending')
        self.assertEqual((by_level['G4']['min_volume'], by_level['G4']['max_volume']), (28, 32))
        self.assertEqual((by_level['G2']['min_volume'], by_level['G2']['max_volume']), (0, 32))
        self.assertEqual(result['confirmed_count'], 1)
        self.assertEqual(result['pending_count'], 3)

    def test_consistency_across_all_feasible_solutions(self):
        # 区间在所有可行解中恰好夹出同一个值时应判确认。
        result = solve([Level('G1', 1), Level('G2', 2), Level('G3', 3)],
                       [Baseline('G1', 0)],
                       [exp('T1', 'G3', 'G1', 20, 20), exp('T2', 'G3', 'G2', 10, 10)])
        by_level = {row['level']: row for row in result['rows']}
        self.assertEqual(by_level['G2']['status'], 'confirmed')
        self.assertEqual(by_level['G2']['volume'], 10)

    def test_infeasible_lists_minimum_single_removals(self):
        result = solve(LEVELS, [Baseline('G1', 0)], [
            exp('T1', 'G3', 'G1', 20), exp('T2', 'G2', 'G1', 15), exp('T3', 'G3', 'G2', 0, 2)])
        self.assertFalse(result['feasible'])
        diagnosis = result['diagnosis']
        self.assertFalse(diagnosis['structural'])
        self.assertEqual(sorted(diagnosis['removal_groups']), [['T1'], ['T2'], ['T3']])
        self.assertIn('T1', diagnosis['candidate_experiments'])
        self.assertTrue(all(row['status'] == 'blocked' for row in result['rows']))

    def test_structural_conflict_has_no_removal_group(self):
        result = solve([Level('G1', 1), Level('G2', 2)],
                       [Baseline('G1', 10), Baseline('G2', 5)], [])
        self.assertFalse(result['feasible'])
        diagnosis = result['diagnosis']
        self.assertTrue(diagnosis['structural'])
        self.assertEqual(diagnosis['removal_groups'], [])
        self.assertEqual(diagnosis['candidate_experiments'], [])

    def test_two_disjoint_cycles_require_two_removals(self):
        result = solve([Level('G1', 1), Level('G2', 2), Level('G3', 3)],
                       [Baseline('G1', 0)], [
                           exp('T1', 'G2', 'G1', 10), exp('T2', 'G2', 'G1', 12),
                           exp('T3', 'G3', 'G2', 5), exp('T4', 'G3', 'G1', 20)])
        self.assertFalse(result['feasible'])
        groups = result['diagnosis']['removal_groups']
        self.assertTrue(groups)
        self.assertEqual(min(len(group) for group in groups), 2)
        for group in groups:
            self.assertEqual(len(group), 2)
        self.assertIn(['T1', 'T4'], [sorted(group) for group in groups])

    def test_monotonicity_holds_in_every_solution(self):
        result = solve(LEVELS, [Baseline('G1', 100)], [exp('T1', 'G4', 'G1', 10, 12)])
        self.assertTrue(result['feasible'])
        by_level = {row['level']: row for row in result['rows']}
        self.assertEqual(by_level['G1']['volume'], 100)
        self.assertEqual(by_level['G4']['min_volume'], 110)
        self.assertEqual(by_level['G4']['max_volume'], 112)
        for row in result['rows'][1:]:
            self.assertEqual(row['status'], 'pending')
            self.assertGreaterEqual(row['min_volume'], 100)

    def test_baseline_anchors_any_level(self):
        result = solve(LEVELS, [Baseline('G3', 25)], [exp('T1', 'G4', 'G3', 5)])
        by_level = {row['level']: row for row in result['rows']}
        self.assertEqual(by_level['G3']['status'], 'confirmed')
        self.assertEqual(by_level['G4']['status'], 'confirmed')
        self.assertEqual(by_level['G4']['volume'], 30)
        self.assertEqual(by_level['G1']['status'], 'pending')

    def test_validation_rejects_bad_inputs(self):
        with self.assertRaises(ValueError):
            solve([Level('G1', 1), Level('G1', 2)], [], [])
        with self.assertRaises(ValueError):
            solve(LEVELS, [], [exp('T1', 'G1', 'G2', 10)])
        with self.assertRaises(ValueError):
            solve(LEVELS, [Baseline('G1', 0)], [exp('T1', 'G2', 'G1', 20, 10)])
        with self.assertRaises(ValueError):
            solve(LEVELS, [Baseline('G9', 0)], [])

    def test_removal_group_restores_feasibility(self):
        result = solve(LEVELS, [Baseline('G1', 0)], [
            exp('T1', 'G3', 'G1', 20), exp('T2', 'G2', 'G1', 15), exp('T3', 'G3', 'G2', 0, 2)])
        kept = [exp('T1', 'G3', 'G1', 20), exp('T2', 'G2', 'G1', 15)]
        repaired = solve(LEVELS, [Baseline('G1', 0)], kept)
        self.assertTrue(repaired['feasible'])
        by_level = {row['level']: row for row in repaired['rows']}
        self.assertEqual(by_level['G3']['volume'], 20)
        self.assertEqual(by_level['G2']['volume'], 15)

    def test_minimum_removal_searches_all_experiments(self):
        # 最小击中集的成员可能不在当前负环上，候选必须是全部试验，避免漏掉更小组。
        experiments = [
            exp('A', 'G2', 'G1', 10), exp('B', 'G2', 'G1', 12),
            exp('C', 'G3', 'G2', 5), exp('D', 'G3', 'G1', 20)]
        result = solve([Level('G1', 1), Level('G2', 2), Level('G3', 3)],
                       [Baseline('G1', 0)], experiments)
        self.assertFalse(result['feasible'])
        diagnosis = result['diagnosis']
        # 候选集覆盖全部试验，而不仅是某个负环上的试验。
        self.assertEqual(diagnosis['candidate_experiments'], ['A', 'B', 'C', 'D'])
        groups = diagnosis['removal_groups']
        self.assertTrue(groups)
        # 每个推荐组撤掉后都必须真正恢复可行。
        from src.domain.calibration import _Edge, _is_feasible
        index = {'G1': 1, 'G2': 2, 'G3': 3}
        edges = [_Edge(2, 1, 0.0, ('mono',)), _Edge(3, 2, 0.0, ('mono',)),
                 _Edge(0, 1, 0.0, ('base', 'G1')), _Edge(1, 0, 0.0, ('base', 'G1'))]
        for item in experiments:
            high, low = index[item.from_level], index[item.to_level]
            edges.append(_Edge(low, high, item.drain_max, ('exp', item.code)))
            edges.append(_Edge(high, low, -item.drain_min, ('exp', item.code)))
        for group in groups:
            self.assertTrue(_is_feasible(4, edges, set(group)))


if __name__ == '__main__':
    unittest.main(verbosity=2)
