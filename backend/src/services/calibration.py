"""校准业务的事务编排：录入、解算、版本发布与原子切换。"""
import csv
import io

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.constants.enums import LevelStatus, RunStatus
from src.domain.calibration import (
    Baseline,
    ExperimentInput,
    Level,
    solve,
)
from src.domain.spec import SPEC
from src.models.calibration import (
    Baseline as BaselineModel,
    CalibrationRun,
    CalibrationTable,
    Experiment,
    LevelDef,
    TableLevel,
)
from src.services.audit import record
from src.utils.time import iso, now


# ---------- 读取与转换 ----------

def load_levels(db):
    return [Level(item.code, item.rank)
            for item in db.scalars(select(LevelDef).order_by(LevelDef.rank))]


def load_baselines(db):
    return [Baseline(item.level_code, item.volume)
            for item in db.scalars(select(BaselineModel).order_by(BaselineModel.id))]


def load_experiments(db, only_active=True, codes=None):
    query = select(Experiment).order_by(Experiment.id)
    if only_active:
        query = query.where(Experiment.active.is_(True))
    rows = list(db.scalars(query))
    if codes is not None:
        wanted = set(codes)
        rows = [item for item in rows if item.code in wanted]
    return [ExperimentInput(item.code, item.from_level, item.to_level,
                            item.drain_min, item.drain_max) for item in rows]


def level_view(item, baseline_volume=None):
    return {'code': item.code, 'rank': item.rank,
            'baseline_volume': baseline_volume,
            'created_at': iso(item.created_at)}


def experiment_view(item):
    return {'id': item.id, 'code': item.code, 'from_level': item.from_level,
            'to_level': item.to_level, 'drain_min': item.drain_min,
            'drain_max': item.drain_max, 'note': item.note,
            'active': item.active, 'author': item.author,
            'created_at': iso(item.created_at), 'updated_at': iso(item.updated_at)}


def baseline_view(item):
    return {'id': item.id, 'level': item.level_code, 'volume': item.volume,
            'author': item.author, 'updated_at': iso(item.updated_at)}


def run_view(item):
    return {'id': item.id, 'name': item.name, 'status': item.status,
            'author': item.author, 'created_at': iso(item.created_at),
            'result': item.result, 'input_snapshot': item.input_snapshot}


def table_view(item, levels=None):
    data = {'id': item.id, 'version': item.version, 'run_id': item.run_id,
            'active': item.active, 'author': item.author,
            'activated_at': iso(item.activated_at), 'created_at': iso(item.created_at)}
    if levels is not None:
        data['levels'] = [{'level': row.level_code, 'rank': row.rank,
                           'volume': row.volume, 'evidence': row.evidence}
                          for row in sorted(levels, key=lambda row: row.rank)]
    return data


# ---------- 档位与基准 ----------

def add_level(db, code, rank, actor):
    if db.get(LevelDef, code):
        raise ValueError(f'档位 {code} 已存在')
    if db.scalar(select(LevelDef).where(LevelDef.rank == rank)):
        raise ValueError(f'排序 {rank} 已被其他档位占用')
    item = LevelDef(code=code, rank=rank, author=actor)
    try:
        with db.begin_nested():
            db.add(item)
            db.flush()
    except IntegrityError:
        raise ValueError('档位编号或排序冲突') from None
    record(db, actor, 'level.created', code, rank=rank)
    return item


def upsert_baseline(db, level, volume, actor):
    if not db.get(LevelDef, level):
        raise ValueError(f'档位 {level} 不存在，无法录入空池基准')
    item = db.scalar(select(BaselineModel).where(BaselineModel.level_code == level))
    if item:
        old = item.volume
        item.volume = volume
        item.author = actor
        record(db, actor, 'baseline.corrected', level, old=old, new=volume)
    else:
        item = BaselineModel(level_code=level, volume=volume, author=actor)
        db.add(item)
        record(db, actor, 'baseline.created', level, volume=volume)
    return item


# ---------- 试验录入（含补测与更正的整单原子提交） ----------

def _validate_experiment_payload(db, payload, known_codes):
    levels = {item.code: item.rank for item in db.scalars(select(LevelDef))}
    if payload.code in known_codes:
        raise ValueError(f'本单内试验编号 {payload.code} 重复')
    if payload.from_level not in levels or payload.to_level not in levels:
        raise ValueError(f'试验 {payload.code} 引用了未定义的档位')
    if levels[payload.from_level] <= levels[payload.to_level]:
        raise ValueError(f'试验 {payload.code} 必须从较高档位排到较低档位')
    if payload.drain_max < payload.drain_min:
        raise ValueError(f'试验 {payload.code} 的最大排水量不能小于最小排水量')
    known_codes.add(payload.code)


def upsert_experiment(db, payload, actor):
    existing = db.scalar(select(Experiment).where(Experiment.code == payload.code).with_for_update())
    if existing:
        before = {'from_level': existing.from_level, 'to_level': existing.to_level,
                  'drain_min': existing.drain_min, 'drain_max': existing.drain_max}
        existing.from_level = payload.from_level
        existing.to_level = payload.to_level
        existing.drain_min = payload.drain_min
        existing.drain_max = payload.drain_max
        existing.note = payload.note
        existing.active = True
        existing.author = actor
        record(db, actor, 'experiment.corrected', payload.code, before=before,
               after={'from_level': payload.from_level, 'to_level': payload.to_level,
                      'drain_min': payload.drain_min, 'drain_max': payload.drain_max})
        return existing, False
    item = Experiment(code=payload.code, from_level=payload.from_level,
                      to_level=payload.to_level, drain_min=payload.drain_min,
                      drain_max=payload.drain_max, note=payload.note,
                      active=True, author=actor)
    db.add(item)
    record(db, actor, 'experiment.created', payload.code,
           drain=[payload.drain_min, payload.drain_max])
    return item, True


def submit_batch(db, payload, actor):
    """补测和更正同时提交时整单处理：任一校验失败全部回滚。"""
    known = set(db.scalars(select(Experiment.code)))
    seen = set()
    created, corrected = [], []
    for experiment in payload.experiments:
        _validate_experiment_payload(db, experiment, seen)
        item, was_created = upsert_experiment(db, experiment, actor)
        (created if was_created else corrected).append(item.code)
    for baseline in payload.baselines:
        upsert_baseline(db, baseline.level, baseline.volume, actor)
    disabled = []
    for code in payload.disable_codes:
        item = db.scalar(select(Experiment).where(Experiment.code == code).with_for_update())
        if not item:
            raise ValueError(f'要停用的试验 {code} 不存在')
        if item.active:
            item.active = False
            disabled.append(code)
            record(db, actor, 'experiment.disabled', code)
    record(db, actor, 'batch.submitted', 'experiments',
           created=created, corrected=corrected, disabled=disabled,
           baselines=[item.level for item in payload.baselines])
    return {'created': sorted(created), 'corrected': sorted(corrected),
            'disabled': sorted(disabled)}


def _parse_cell(field, raw, line_num):
    value = raw.strip() if isinstance(raw, str) else raw
    if not value:
        if field.get('required', True):
            raise ValueError(f"{field['label']}不能为空")
        return ''
    try:
        if field['type'] == 'number':
            parsed = float(value)
        else:
            parsed = value
            if len(parsed) > field.get('max_length', 300):
                raise ValueError(f"{field['label']}超长")
    except (TypeError, ValueError):
        raise ValueError(f"{field['label']}格式不正确") from None
    if field['type'] == 'number':
        if 'min' in field and parsed < field['min']:
            raise ValueError(f"{field['label']}最小为 {field['min']}")
        if 'max' in field and parsed > field['max']:
            raise ValueError(f"{field['label']}最大为 {field['max']}")
    return parsed


def parse_experiment_csv(text):
    reader = csv.DictReader(io.StringIO(text.removeprefix('\ufeff'), newline=''), strict=True)
    fields = SPEC['csv_fields']
    label_to_key = {field['label']: field['key'] for field in fields}
    headers = reader.fieldnames or []
    if not set(headers) <= set(label_to_key) or len(headers) != len(set(headers)):
        raise ValueError('CSV 表头与字段说明不符，请下载模板检查列名')
    rows = []
    try:
        for raw in reader:
            if len(rows) >= 5000:
                raise ValueError('一次最多导入 5000 条试验')
            if None in raw:
                raise ValueError('工作表的列数与表头不一致')
            normalized = {label_to_key[header]: value for header, value in raw.items()}
            rows.append({field['key']: _parse_cell(field, normalized.get(field['key']), reader.line_num)
                         for field in fields})
    except csv.Error:
        raise ValueError(f'CSV 第 {reader.line_num} 行附近格式不正确') from None
    if not rows:
        raise ValueError('CSV 至少需要一条有效试验')
    return rows


def csv_template():
    fields = SPEC['csv_fields']
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer)
    writer.writerow([field['label'] for field in fields])
    key_order = [field['key'] for field in fields]
    for item in demo_experiment_rows():
        writer.writerow([item.get(key, '') for key in key_order])
    return '\ufeff' + buffer.getvalue()


def demo_experiment_rows():
    from src.domain.demo import demo_experiments
    return [{'code': item.code, 'from_level': item.from_level, 'to_level': item.to_level,
             'drain_min': item.drain_min, 'drain_max': item.drain_max, 'note': ''}
            for item in demo_experiments()]


# ---------- 解算 ----------

def _snapshot(db, experiment_codes=None):
    levels = load_levels(db)
    if not levels:
        raise ValueError('请先在档位页维护液位档位')
    baselines = load_baselines(db)
    experiments = load_experiments(db, codes=experiment_codes)
    if experiment_codes is not None:
        found = {item.code for item in experiments}
        missing = sorted(set(experiment_codes) - found)
        if missing:
            raise ValueError(f'试验不存在或已停用：{"、".join(missing)}')
    if not experiments:
        raise ValueError('至少需要一条启用的排水试验才能解算')
    return levels, baselines, experiments


def create_run(db, name, actor, experiment_codes=None):
    levels, baselines, experiments = _snapshot(db, experiment_codes)
    result = solve(levels, baselines, experiments)
    snapshot = {
        'levels': [{'code': item.code, 'rank': item.rank} for item in levels],
        'baselines': [{'level': item.level, 'volume': item.volume} for item in baselines],
        'experiments': [{'code': item.code, 'from_level': item.from_level,
                         'to_level': item.to_level, 'drain_min': item.drain_min,
                         'drain_max': item.drain_max} for item in experiments],
    }
    status = RunStatus.FEASIBLE if result['feasible'] else RunStatus.INFEASIBLE
    item = CalibrationRun(name=name, status=status, input_snapshot=snapshot,
                          result=result, author=actor)
    db.add(item)
    db.flush()
    record(db, actor, f'calibration.{status}', item.id,
           confirmed=result.get('confirmed_count'), pending=result.get('pending_count'))
    return item


def list_runs(db):
    return list(db.scalars(select(CalibrationRun).order_by(CalibrationRun.id.desc()).limit(100)))


# ---------- 库容表版本与一次性切换 ----------

def publish_table(db, run_id, actor):
    run = db.get(CalibrationRun, run_id, with_for_update=True)
    if not run:
        raise ValueError('找不到该次校准计算')
    if run.status != RunStatus.FEASIBLE:
        raise ValueError('无解的计算不能发布库容表，请先按诊断处理冲突试验')
    rows = run.result['rows']
    if any(row['status'] != LevelStatus.CONFIRMED for row in rows):
        pending = [row['level'] for row in rows if row['status'] != LevelStatus.CONFIRMED]
        raise ValueError(f'仍有待补测档位，不能发布：{"、".join(pending)}')

    next_version = (db.scalar(select(CalibrationTable.version).order_by(
        CalibrationTable.version.desc()).limit(1)) or 0) + 1
    table = CalibrationTable(version=next_version, run_id=run.id, active=False,
                             author=actor, activated_at=None)
    db.add(table)
    db.flush()
    for row in rows:
        db.add(TableLevel(table_id=table.id, level_code=row['level'], rank=row['rank'],
                          volume=row['volume'], evidence=row['evidence']))
    record(db, actor, 'table.drafted', table.id, version=next_version, run_id=run.id)
    return table


def activate_table(db, table_id, actor):
    """单事务内把目标版本置为生效、旧生效版本整体下线，杜绝半成品顶回旧表。"""
    target = db.get(CalibrationTable, table_id, with_for_update=True)
    if not target:
        raise ValueError('找不到该库容表版本')
    current = db.scalars(select(CalibrationTable).where(CalibrationTable.active.is_(True))
                         .with_for_update()).all()
    for item in current:
        if item.id == target.id:
            continue
        item.active = False
    target.active = True
    target.activated_at = now()
    record(db, actor, 'table.activated', target.id,
           version=target.version, replaced=[item.version for item in current if item.id != target.id])
    return target


def active_table(db):
    table = db.scalar(select(CalibrationTable).where(CalibrationTable.active.is_(True))
                      .order_by(CalibrationTable.id.desc()))
    if not table:
        return None, []
    levels = list(db.scalars(select(TableLevel).where(TableLevel.table_id == table.id)))
    return table, levels


def list_tables(db):
    return list(db.scalars(select(CalibrationTable).order_by(CalibrationTable.id.desc()).limit(50)))


def table_levels(db, table_id):
    return list(db.scalars(select(TableLevel).where(TableLevel.table_id == table_id)
                           .order_by(TableLevel.rank)))
