from datetime import datetime
from sqlalchemy import JSON, Boolean, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
from src.utils.time import now


class LevelDef(Base):
    """液位档位定义，按 rank 从低到高。"""

    __tablename__ = 'level_defs'

    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    rank: Mapped[int] = mapped_column(unique=True)
    author: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=now)


class Baseline(Base):
    """空池基准：该档位在空池基准下的库容锚点。"""

    __tablename__ = 'baselines'
    __table_args__ = (UniqueConstraint('level_code'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    level_code: Mapped[str] = mapped_column(ForeignKey('level_defs.code'))
    volume: Mapped[float] = mapped_column(Float)
    author: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(default=now, onupdate=now)


class Experiment(Base):
    """一次排水试验，记录排水前后档位与排水量范围。active=False 表示已停用。"""

    __tablename__ = 'experiments'
    __table_args__ = (UniqueConstraint('code'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40))
    from_level: Mapped[str] = mapped_column(ForeignKey('level_defs.code'))
    to_level: Mapped[str] = mapped_column(ForeignKey('level_defs.code'))
    drain_min: Mapped[float] = mapped_column(Float)
    drain_max: Mapped[float] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(String(300))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    author: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=now)
    updated_at: Mapped[datetime] = mapped_column(default=now, onupdate=now)


class CalibrationRun(Base):
    """一次校准计算的输入快照与解算结果，输入不可变。"""

    __tablename__ = 'calibration_runs'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), index=True)
    input_snapshot: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    author: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=now)


class CalibrationTable(Base):
    """已发布的库容表版本，同一时刻只有一个 active 版本。"""

    __tablename__ = 'calibration_tables'

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(unique=True)
    run_id: Mapped[int] = mapped_column(ForeignKey('calibration_runs.id'))
    active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    author: Mapped[str] = mapped_column(String(64))
    activated_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=now)


class TableLevel(Base):
    """发布版本中每个档位的库容及采用的试验证据。"""

    __tablename__ = 'table_levels'
    __table_args__ = (UniqueConstraint('table_id', 'level_code'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey('calibration_tables.id'))
    level_code: Mapped[str] = mapped_column(String(40))
    rank: Mapped[int]
    volume: Mapped[float] = mapped_column(Float)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
