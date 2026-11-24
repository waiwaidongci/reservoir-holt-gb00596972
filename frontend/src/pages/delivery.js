import {feedback} from '../components/common/fields.js';
import {panel, pill} from '../components/common/panels.js';
import {table} from '../components/common/table.js';
import {handler} from '../hooks/action.js';
import {workspace} from '../stores/workspace.js';
import {button, el, link, p} from '../utils/dom.js';
import {date, value} from '../utils/format.js';

export async function deliveryPage(route, refresh) {
  const {spec, tables} = workspace;
  const message = feedback();
  const tableId = route.id || tables.find(item=>item.active)?.id;
  const detail = tableId ? await workspace.getTable(tableId) : null;

  const picker = el('label',{class:'field run-picker'},el('span',{},'切换库容表版本'),
    el('select',{onChange:event=>{location.hash=`#delivery/${event.target.value}`;}},
      tables.map(item=>el('option',{value:item.id, selected:detail && item.id === detail.id},
        `v${item.version}${item.active ? '（生效中）' : ''}`))));

  const download = button('下载交班 CSV',{class:'quiet'});
  download.addEventListener('click', handler(download, message,
    () => workspace.download(`/tables/${detail.id}/export`, `库容表-v${detail.version}.csv`)));
  const content = detail ? el('div',{},
      panel(`库容表 v${detail.version}`,
        pill(detail.active ? '生效中' : '历史版本', detail.active ? 'feasible' : 'blocked'),
        p(`来源计算 #${detail.run_id} · 发布人 ${detail.author} · 生效时间 ${date(detail.activated_at)} · 创建于 ${date(detail.created_at)}`,'filename'),
        picker,
        table([
          {key:'level',label:'档位'},
          {key:'rank',label:'液位排序'},
          {key:'volume',label:'库容（m³）',render:row=>value(row.volume)},
          {label:'采用的试验',render:row=>row.evidence.length ? row.evidence.join('、') : '空池基准（无试验证据）'},
        ], detail.levels, {caption:`库容表 v${detail.version}`}),
        download))
    : panel(spec.pages[5], p('还没有已发布的库容表。','empty'),
        link('前往发布','#publish',{class:'quiet'}));

  const versions = table([
    {label:'版本',render:row=>row.active ? pill(`v${row.version}（生效中）`,'feasible') : `v${row.version}`},
    {key:'run_id',label:'来源计算'},
    {label:'生效时间',render:row=>date(row.activated_at)},
    {label:'操作',render:row=>link('查看',`#delivery/${row.id}`)},
  ], tables, {caption:'版本清单', empty:'发布后在此交班查阅。'});

  return el('div',{class:'two-col'},
    el('div',{class:'wide-panel'}, content),
    el('aside',{class:'sidebar-panel'}, panel('交班说明',
      p('交班时以生效版本为准，每个档位都能回溯到采用的试验编号；历史版本保留可查，不再生效。','subtle'),
      versions)));
}
