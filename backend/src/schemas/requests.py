from pydantic import BaseModel, ConfigDict, Field


class Request(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')


class Credentials(Request):
    username: str = Field(min_length=1, max=64)
    password: str = Field(min_length=1, max=128)


class LevelCreate(Request):
    code: str = Field(min_length=1, max=40)
    rank: int = Field(ge=1, le=1000)


class BaselineSubmit(Request):
    level: str = Field(min_length=1, max=40)
    volume: float = Field(ge=0, le=1_000_000)


class ExperimentSubmit(Request):
    code: str = Field(min_length=1, max=40)
    from_level: str = Field(min_length=1, max=40)
    to_level: str = Field(min_length=1, max=40)
    drain_min: float = Field(ge=0, le=1_000_000)
    drain_max: float = Field(ge=0, le=1_000_000)
    note: str = Field(default='', max_length=300)


class BatchSubmit(Request):
    """一次提交里同时带上新增/更正的试验、基准与要停用的试验，整单原子处理。"""

    experiments: list[ExperimentSubmit] = Field(default_factory=list, max_length=200)
    baselines: list[BaselineSubmit] = Field(default_factory=list, max_length=200)
    disable_codes: list[str] = Field(default_factory=list, max_length=200)
    run_name: str = Field(default='', max_length=120)


class RunCreate(Request):
    name: str = Field(min_length=1, max_length=120)
    # 允许指定参与计算的试验；空列表表示使用全部启用试验。
    experiment_codes: list[str] = Field(default_factory=list, max_length=200)


class ActivateRequest(Request):
    run_id: int = Field(gt=0)
    note: str = Field(default='', max_length=300)
