"""API 端到端测试：内存 SQLite + TestClient，python -I tests/test_api.py"""
import os
import tempfile
import unittest
from pathlib import Path

os.environ['DATABASE_URL'] = f"sqlite:///{Path(tempfile.mkdtemp()) / 'api.db'}"
os.environ['JWT_SECRET'] = 'test-secret'
os.environ['SEED_DEMO'] = 'false'
os.environ['ARTIFACT_DIR'] = tempfile.mkdtemp()

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from src.config.database import Base, engine
from src.main import app
from src.models.identity import User
from src.utils.security import hash_password
import src.models.calibration  # noqa: F401  注册表模型

Base.metadata.create_all(engine)
from src.config.database import Session
with Session.begin() as db:
    for role, password in [('admin', 'admin-demo-2611'), ('analyst', 'analyst-demo-2611'),
                           ('viewer', 'viewer-demo-2611')]:
        db.add(User(username=role, role=role, password_hash=hash_password(password)))

client = TestClient(app)


def login(username, password):
    response = client.post('/auth/login', json={'username': username, 'password': password})
    assert response.status_code == 200, response.text
    return response.json()['token']


def headers(token):
    return {'Authorization': f'Bearer {token}'}

LEVELS = [{'code': f'G{i}', 'rank': i} for i in range(1, 7)]
EXPERIMENTS = [
    {'code': 'T01', 'from_level': 'G2', 'to_level': 'G1', 'drain_min': 12, 'drain_max': 12},
    {'code': 'T02', 'from_level': 'G3', 'to_level': 'G2', 'drain_min': 18, 'drain_max': 18},
    {'code': 'T03', 'from_level': 'G4', 'to_level': 'G3', 'drain_min': 25, 'drain_max': 25},
    {'code': 'T04', 'from_level': 'G5', 'to_level': 'G4', 'drain_min': 30, 'drain_max': 30},
    {'code': 'T05', 'from_level': 'G6', 'to_level': 'G5', 'drain_min': 35, 'drain_max': 35},
    {'code': 'T06', 'from_level': 'G6', 'to_level': 'G3', 'drain_min': 90, 'drain_max': 90},
    {'code': 'T08', 'from_level': 'G5', 'to_level': 'G3', 'drain_min': 60, 'drain_max': 60},
]


class ApiWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin = login('admin', 'admin-demo-2611')
        cls.analyst = login('analyst', 'analyst-demo-2611')
        cls.viewer = login('viewer', 'viewer-demo-2611')
        cls.run_id = None

    def test_01_spec_and_auth(self):
        spec = client.get('/spec').json()
        self.assertEqual(len(spec['pages']), 6)
        me = client.get('/auth/me', headers=headers(self.analyst)).json()
        self.assertEqual(me['role'], 'analyst')
        denied = client.post('/auth/login', json={'username': 'admin', 'password': 'wrong'})
        self.assertEqual(denied.status_code, 401)

    def test_02_viewer_cannot_write(self):
        response = client.post('/levels', headers=headers(self.viewer),
                               json={'code': 'X1', 'rank': 1})
        self.assertEqual(response.status_code, 403)

    def test_03_setup_levels_and_baseline(self):
        for item in LEVELS:
            response = client.post('/levels', headers=headers(self.analyst), json=item)
            self.assertEqual(response.status_code, 201, response.text)
        duplicate = client.post('/levels', headers=headers(self.analyst),
                                json={'code': 'G1', 'rank': 9})
        self.assertEqual(duplicate.status_code, 422)
        response = client.post('/baselines', headers=headers(self.analyst),
                               json={'level': 'G1', 'volume': 0})
        self.assertEqual(response.status_code, 201)
        # 更正基准应成功更新而不是重复插入。
        response = client.post('/baselines', headers=headers(self.analyst),
                               json={'level': 'G1', 'volume': 0.0})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(client.get('/baselines', headers=headers(self.analyst)).json()), 1)

    def test_04_batch_atomic_rollback(self):
        payload = {
            'experiments': [
                {'code': 'B1', 'from_level': 'G2', 'to_level': 'G1', 'drain_min': 5, 'drain_max': 5},
                {'code': 'B2', 'from_level': 'G1', 'to_level': 'G2', 'drain_min': 5, 'drain_max': 5},
            ],
        }
        response = client.post('/experiments/batch', headers=headers(self.analyst), json=payload)
        self.assertEqual(response.status_code, 422)
        codes = {item['code'] for item in client.get('/experiments', headers=headers(self.analyst)).json()}
        self.assertNotIn('B1', codes)
        self.assertNotIn('B2', codes)

    def test_05_submit_chain_with_conflict(self):
        response = client.post('/experiments/batch', headers=headers(self.analyst),
                               json={'experiments': EXPERIMENTS})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(len(response.json()['created']), 7)

    def test_06_csv_import_and_template(self):
        template = client.get('/template', headers=headers(self.viewer))
        self.assertEqual(template.status_code, 200)
        self.assertIn('试验编号', template.text)
        csv_text = '试验编号,排水前档位,排水后档位,最小排水量（m³）,最大排水量（m³）,备注\nT07,G4,G1,55,55,跨档\n'
        response = client.post('/experiments/csv', headers=headers(self.analyst),
                               json={'csv_text': csv_text})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()['rows'], 1)

    def test_07_run_infeasible_diagnosis(self):
        response = client.post('/runs', headers=headers(self.analyst),
                               json={'name': '含冲突的首次解算'})
        self.assertEqual(response.status_code, 201, response.text)
        run = response.json()
        self.assertEqual(run['status'], 'infeasible')
        diagnosis = run['result']['diagnosis']
        self.assertFalse(diagnosis['structural'])
        self.assertIn(['T08'], diagnosis['removal_groups'])

    def test_08_publish_blocked_while_infeasible(self):
        run_id = client.get('/runs', headers=headers(self.analyst)).json()[0]['id']
        response = client.post('/tables/publish', headers=headers(self.admin),
                               json={'run_id': run_id})
        self.assertEqual(response.status_code, 422)

    def test_09_disable_conflict_then_confirm_all(self):
        response = client.post('/experiments/batch', headers=headers(self.analyst),
                               json={'disable_codes': ['T08']})
        self.assertEqual(response.status_code, 201)
        response = client.post('/runs', headers=headers(self.analyst),
                               json={'name': '撤冲突后解算'})
        self.assertEqual(response.status_code, 201)
        run = response.json()
        self.assertEqual(run['status'], 'feasible')
        self.assertEqual(run['result']['confirmed_count'], 6)
        self.assertEqual(run['result']['pending_count'], 0)
        by_level = {row['level']: row for row in run['result']['rows']}
        self.assertEqual([by_level[f'G{i}']['volume'] for i in range(1, 7)],
                         [0, 12, 30, 55, 85, 120])
        type(self).run_id = run['id']

    def test_10_analyst_cannot_publish(self):
        response = client.post('/tables/publish', headers=headers(self.analyst),
                               json={'run_id': self.run_id})
        self.assertEqual(response.status_code, 403)

    def test_11_publish_and_atomic_switch(self):
        response = client.post('/tables/publish', headers=headers(self.admin),
                               json={'run_id': self.run_id, 'note': '首版发布'})
        self.assertEqual(response.status_code, 201, response.text)
        table = response.json()
        self.assertTrue(table['active'])
        self.assertEqual(table['version'], 1)
        self.assertEqual(len(table['levels']), 6)
        # 交班页读取的生效表。
        active = client.get('/tables/active', headers=headers(self.viewer)).json()
        self.assertEqual(active['version'], 1)
        g6 = next(row for row in active['levels'] if row['level'] == 'G6')
        self.assertEqual(g6['volume'], 120)
        self.assertIn('T05', g6['evidence'])

        # 发布第二版，旧版本必须整体下线而不是被半成品顶回。
        # 停用 T02/T03/T06 后 G3 失去全部锚点，必然有待补测档位。
        response = client.post('/experiments/batch', headers=headers(self.analyst),
                               json={'disable_codes': ['T02', 'T03', 'T06']})
        self.assertEqual(response.status_code, 201)
        pending_run = client.post('/runs', headers=headers(self.analyst),
                                  json={'name': '缺锚点的待补测解算'}).json()
        self.assertEqual(pending_run['status'], 'feasible')
        self.assertGreater(pending_run['result']['pending_count'], 0)
        blocked = client.post('/tables/publish', headers=headers(self.admin),
                              json={'run_id': pending_run['id']})
        self.assertEqual(blocked.status_code, 422)
        active = client.get('/tables/active', headers=headers(self.viewer)).json()
        self.assertEqual(active['version'], 1)

        # 恢复三条试验后再发布 v2，v1 应被原子替换。
        client.post('/experiments/batch', headers=headers(self.analyst),
                    json={'experiments': [item for item in EXPERIMENTS
                                          if item['code'] in ('T02', 'T03', 'T06')]})
        run2 = client.post('/runs', headers=headers(self.analyst),
                           json={'name': '第二版解算'}).json()
        table2 = client.post('/tables/publish', headers=headers(self.admin),
                             json={'run_id': run2['id']}).json()
        self.assertEqual(table2['version'], 2)
        self.assertTrue(table2['active'])
        versions = client.get('/tables', headers=headers(self.viewer)).json()
        self.assertEqual([item['version'] for item in versions], [2, 1])
        old = next(item for item in versions if item['version'] == 1)
        self.assertFalse(old['active'])

    def test_12_export_report(self):
        active = client.get('/tables/active', headers=headers(self.viewer)).json()
        response = client.get(f"/tables/{active['id']}/export", headers=headers(self.viewer))
        self.assertEqual(response.status_code, 200)
        self.assertIn('库容表版本 v2', response.text)
        self.assertIn('T05', response.text)

    def test_13_audit_trail(self):
        events = client.get('/audit', headers=headers(self.admin)).json()
        names = {item['event'] for item in events}
        self.assertIn('table.activated', names)
        self.assertIn('batch.submitted', names)
        self.assertIn('calibration.infeasible', names)

    def test_14_pending_levels_show_intervals(self):
        # 用试验子集解算：仅有宽区间试验时，中间档位必须待补测并给出可行区间，
        # 通过 experiment_codes 指定子集，不改动全局启用状态。
        client.post('/experiments/batch', headers=headers(self.analyst),
                    json={'experiments': [{'code': 'T09', 'from_level': 'G6',
                                           'to_level': 'G1', 'drain_min': 100, 'drain_max': 140}]})
        run = client.post('/runs', headers=headers(self.analyst),
                          json={'name': '宽区间待补测',
                                'experiment_codes': ['T09']}).json()
        self.assertEqual(run['status'], 'feasible')
        by_level = {row['level']: row for row in run['result']['rows']}
        self.assertEqual(by_level['G3']['status'], 'pending')
        self.assertIsNone(by_level['G3']['volume'])
        self.assertIsNotNone(by_level['G3']['min_volume'])
        self.assertIsNotNone(by_level['G3']['max_volume'])
        self.assertEqual(by_level['G6']['status'], 'pending')
        self.assertEqual((by_level['G6']['min_volume'], by_level['G6']['max_volume']), (100, 140))


if __name__ == '__main__':
    unittest.main(verbosity=2)
