from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.config.database import connection
from src.constants.enums import Role
from src.controllers.auth import allow, current
from src.models.calibration import CalibrationRun
from src.schemas.requests import RunCreate
from src.services import calibration as service

router = APIRouter(prefix='/runs')


@router.get('')
def index(db: Session = Depends(connection), actor=Depends(current)):
    return [service.run_view(item) for item in service.list_runs(db)]


@router.post('', status_code=201)
def create(body: RunCreate, db: Session = Depends(connection),
           actor=Depends(allow(Role.ADMIN, Role.ANALYST))):
    item = service.create_run(db, body.name, actor.username,
                              body.experiment_codes or None)
    db.commit()
    return service.run_view(item)


@router.get('/{run_id}')
def detail(run_id: int, db: Session = Depends(connection), actor=Depends(current)):
    item = db.get(CalibrationRun, run_id)
    if not item:
        raise HTTPException(404, '找不到该次校准计算')
    return service.run_view(item)
