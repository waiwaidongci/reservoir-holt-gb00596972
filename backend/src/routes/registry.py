from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config.database import connection
from src.constants.enums import Role
from src.controllers.auth import allow, current
from src.domain.spec import SPEC
from src.models.calibration import Baseline as BaselineModel, Experiment, LevelDef
from src.schemas.requests import BaselineSubmit, BatchSubmit, LevelCreate
from src.services import calibration as service
from src.services.audit import record

router = APIRouter()


@router.get('/spec')
def spec():
    return SPEC


@router.get('/template')
def sample(actor=Depends(current)):
    filename = quote(SPEC['sample_name'])
    return Response(service.csv_template(), media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f"attachment; filename*=UTF-8''{filename}"})


@router.get('/levels')
def levels(db: Session = Depends(connection), actor=Depends(current)):
    baseline_map = {item.level_code: item.volume
                    for item in db.scalars(select(BaselineModel))}
    return [service.level_view(item, baseline_map.get(item.code))
            for item in db.scalars(select(LevelDef).order_by(LevelDef.rank))]


@router.post('/levels', status_code=201)
def add_level(body: LevelCreate, db: Session = Depends(connection),
              actor=Depends(allow(Role.ADMIN, Role.ANALYST))):
    item = service.add_level(db, body.code, body.rank, actor.username)
    db.commit()
    return service.level_view(item)


@router.get('/baselines')
def baselines(db: Session = Depends(connection), actor=Depends(current)):
    return [service.baseline_view(item)
            for item in db.scalars(select(BaselineModel).order_by(BaselineModel.id))]


@router.post('/baselines', status_code=201)
def save_baseline(body: BaselineSubmit, db: Session = Depends(connection),
                  actor=Depends(allow(Role.ADMIN, Role.ANALYST))):
    item = service.upsert_baseline(db, body.level, body.volume, actor.username)
    db.commit()
    return service.baseline_view(item)


@router.get('/experiments')
def experiments(active: bool | None = None, db: Session = Depends(connection),
                actor=Depends(current)):
    query = select(Experiment).order_by(Experiment.id)
    if active is not None:
        query = query.where(Experiment.active.is_(active))
    return [service.experiment_view(item) for item in db.scalars(query)]


@router.post('/experiments/batch', status_code=201)
def batch(body: BatchSubmit, db: Session = Depends(connection),
          actor=Depends(allow(Role.ADMIN, Role.ANALYST))):
    """补测和更正同时提交时整单原子处理：任一内容不合法则整单不收。"""
    if not body.experiments and not body.baselines and not body.disable_codes:
        raise ValueError('请至少填写一条试验、基准或停用项')
    summary = service.submit_batch(db, body, actor.username)
    db.commit()
    return summary


@router.post('/experiments/csv', status_code=201)
def import_csv(body: dict, db: Session = Depends(connection),
               actor=Depends(allow(Role.ADMIN, Role.ANALYST))):
    text = body.get('csv_text')
    if not isinstance(text, str) or not text.strip():
        raise ValueError('csv_text 不能为空')
    rows = service.parse_experiment_csv(text)
    from src.schemas.requests import ExperimentSubmit
    payload = BatchSubmit(experiments=[ExperimentSubmit(**row) for row in rows])
    summary = service.submit_batch(db, payload, actor.username)
    record(db, actor.username, 'experiment.csv_imported', 'experiments', rows=len(rows))
    db.commit()
    return {**summary, 'rows': len(rows)}
