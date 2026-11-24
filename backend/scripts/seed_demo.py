import json

from sqlalchemy import func, select

from src.config.database import Session
from src.constants.enums import Role
from src.domain.demo import demo_baselines, demo_experiments, demo_levels
from src.models.calibration import Baseline, Experiment, LevelDef
from src.models.identity import User
from src.utils.security import hash_password


def seed():
    with Session.begin() as db:
        for role in Role:
            if not db.get(User, role.value):
                db.add(User(username=role.value, role=role,
                            password_hash=hash_password(f'{role.value}-demo-2611')))
        created_levels = created_experiments = created_baselines = 0
        for item in demo_levels():
            if not db.get(LevelDef, item.code):
                db.add(LevelDef(code=item.code, rank=item.rank, author='seed'))
                created_levels += 1
        for item in demo_baselines():
            if not db.scalar(select(Baseline).where(Baseline.level_code == item.level)):
                db.add(Baseline(level_code=item.level, volume=item.volume, author='seed'))
                created_baselines += 1
        for item in demo_experiments():
            if not db.scalar(select(Experiment).where(Experiment.code == item.code)):
                db.add(Experiment(code=item.code, from_level=item.from_level,
                                  to_level=item.to_level, drain_min=item.drain_min,
                                  drain_max=item.drain_max, note='演示数据',
                                  active=True, author='seed'))
                created_experiments += 1
        return {'users': db.scalar(select(func.count()).select_from(User)),
                'levels': db.scalar(select(func.count()).select_from(LevelDef)),
                'experiments': db.scalar(select(func.count()).select_from(Experiment)),
                'created_levels': created_levels,
                'created_baselines': created_baselines,
                'created_experiments': created_experiments}


if __name__ == '__main__':
    print(json.dumps(seed(), ensure_ascii=False))
