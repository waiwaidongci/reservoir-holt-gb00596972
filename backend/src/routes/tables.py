from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from src.config.database import connection
from src.config.settings import ARTIFACTS
from src.constants.enums import Role
from src.controllers.auth import allow, current
from src.models.calibration import CalibrationTable
from src.schemas.requests import ActivateRequest
from src.services import calibration as service
from src.services.audit import record
from src.utils.exports import write_table_report

router = APIRouter(prefix='/tables')


@router.get('')
def index(db: Session = Depends(connection), actor=Depends(current)):
    return [service.table_view(item) for item in service.list_tables(db)]


@router.get('/active')
def active(db: Session = Depends(connection), actor=Depends(current)):
    table, rows = service.active_table(db)
    if not table:
        return None
    return service.table_view(table, rows)


@router.get('/{table_id}')
def detail(table_id: int, db: Session = Depends(connection), actor=Depends(current)):
    table = db.get(CalibrationTable, table_id)
    if not table:
        raise HTTPException(404, '找不到该库容表版本')
    return service.table_view(table, service.table_levels(db, table_id))


@router.post('/publish', status_code=201)
def publish(body: ActivateRequest, db: Session = Depends(connection),
            actor=Depends(allow(Role.ADMIN))):
    # 先在同一事务内算齐并生成完整版本，再一次性切换；半成品无法顶掉当前生效表。
    table = service.publish_table(db, body.run_id, actor.username)
    activated = service.activate_table(db, table.id, actor.username)
    if body.note:
        record(db, actor.username, 'table.publish_note', table.id, note=body.note)
    db.commit()
    return service.table_view(activated, service.table_levels(db, activated.id))


@router.get('/{table_id}/export')
def export(table_id: int, db: Session = Depends(connection), actor=Depends(current)):
    table = db.get(CalibrationTable, table_id)
    if not table:
        raise HTTPException(404, '找不到该库容表版本')
    rows = service.table_levels(db, table_id)
    name = write_table_report(table, rows)
    path = ARTIFACTS / name
    if not path.is_file():
        raise HTTPException(410, '导出文件已不可用，请重新下载')
    return FileResponse(path, media_type='text/csv',
                        filename=f'库容表-v{table.version}.csv')
