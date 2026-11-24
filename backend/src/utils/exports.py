import csv

from src.config.settings import ARTIFACTS


def safe_cell(value):
    if isinstance(value, str) and (value.lstrip().startswith(('=', '+', '-', '@'))
                                   or value.startswith(('\t', '\r', '\n'))):
        return "'" + value
    return value


def write_table_report(table, levels):
    """按版本导出库容表及每个档位采用的试验证据。"""
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    name = f'calibration-table-v{table.version}.csv'
    path = ARTIFACTS / name
    staging = path.with_suffix('.tmp')
    with staging.open('w', encoding='utf-8-sig', newline='') as output:
        writer = csv.writer(output)
        writer.writerow([safe_cell(f'库容表版本 v{table.version}')])
        writer.writerow([safe_cell(f'来源计算 #{table.run_id}'),
                         safe_cell(f'生效时间 {table.activated_at or "未生效"}'),
                         safe_cell(f'发布人 {table.author}')])
        writer.writerow([])
        writer.writerow([safe_cell('档位'), safe_cell('液位排序'),
                         safe_cell('库容（m³）'), safe_cell('采用试验')])
        for row in sorted(levels, key=lambda item: item.rank):
            writer.writerow([safe_cell(row.level_code), row.rank, row.volume,
                             safe_cell('、'.join(row.evidence))])
    staging.replace(path)
    return name
