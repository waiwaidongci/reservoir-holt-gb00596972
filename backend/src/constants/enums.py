from enum import StrEnum


class Role(StrEnum):
    ADMIN = 'admin'
    ANALYST = 'analyst'
    VIEWER = 'viewer'


class RunStatus(StrEnum):
    FEASIBLE = 'feasible'
    INFEASIBLE = 'infeasible'


class LevelStatus(StrEnum):
    # 所有可行解都一致，可发布。
    CONFIRMED = 'confirmed'
    # 可行解不唯一，等待补测。
    PENDING = 'pending'
    # 约束冲突无解，需要先撤掉冲突试验。
    BLOCKED = 'blocked'
