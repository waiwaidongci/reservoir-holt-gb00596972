"""泵房排水试验的固定演示数据：一条可完整确认的校准链加一组冲突试验。"""

from src.domain.calibration import Baseline, ExperimentInput, Level

LEVELS = [Level('G1', 1), Level('G2', 2), Level('G3', 3),
          Level('G4', 4), Level('G5', 5), Level('G6', 6)]

BASELINES = [Baseline('G1', 0.0)]

# 真实库容（m³）：G1=0, G2=12, G3=30, G4=55, G5=85, G6=120。
# T01–T05 为逐档精确试验，T06/T07 为跨档试验，与逐档链完全一致，可确认全部档位。
# T08 与 T03+T04 矛盾，用于演示无解诊断，可在录入页停用后恢复可行。
EXPERIMENTS = [
    ExperimentInput('T01', 'G2', 'G1', 12.0, 12.0),
    ExperimentInput('T02', 'G3', 'G2', 18.0, 18.0),
    ExperimentInput('T03', 'G4', 'G3', 25.0, 25.0),
    ExperimentInput('T04', 'G5', 'G4', 30.0, 30.0),
    ExperimentInput('T05', 'G6', 'G5', 35.0, 35.0),
    ExperimentInput('T06', 'G6', 'G3', 90.0, 90.0),
    ExperimentInput('T07', 'G4', 'G1', 55.0, 55.0),
    ExperimentInput('T08', 'G5', 'G3', 60.0, 60.0),
]


def demo_levels():
    return list(LEVELS)


def demo_baselines():
    return list(BASELINES)


def demo_experiments():
    return list(EXPERIMENTS)
