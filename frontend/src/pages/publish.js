import {feedback, field} from '../components/common/fields.js';
import {empty, panel, pill} from '../components/common/panels.js';
import {table} from '../components/common/table.js';
import {RUN_STATUS} from '../constants/enums.js';
import {handler} from '../hooks/action.js';
import {session} from '../stores/session.js';
import {workspace} from '../stores/workspace.js';
import {button, el, link, p} from '../utils/dom.js';
import {date, value} from '../utils/format.js';

export async function publishPage(route, refresh) {
  const {runs, tables} = workspace;
  const error = feedback();
  const active = tables.find(item=>item.active);
  const activeDetail = active ? await workspace.getTable(active.id) : null;
  const publishable = runs.filter(item=>item.status === 'feasible'
    && item.result.pending_count === 0);

  const publishForm = session.canReview && el('form',{class:'fields',onSubmit:handler(button('算齐后一次性切换',{type:'submit',class:'primary'}),error,async event=>{
    event.preventDefault();
    const data = new FormData(event.target);
    const runId = Number(data.get('run_id'));
    if (!runId) throw new Error('请选择一次全部确认的计算');
    await workspace.publish({run_id:runId, note:data.get('note') || ''});
    await refresh();
  })}, el('label',{class:'field'},el('span',{},'选择可发布计算'),
      el('select',{name:'run_id',required:true},
        el('option',{value:''}, publishable.length ? '请选择' : '暂无算齐的计算'),
        ...publishable.map(item=>el('option',{value:item.id}, `#${item.id} ${item.name}`)))),
    field({key:'note',label:'发布说明',type:'string',required:false,max_length:300}),
    p('发布在单事务内完成：新版本生效的同时旧版本整体下线；有待补测或无解的计算无法发布，旧表不会被顶回去。','subtle'),
    button('算齐后一次性切换',{type:'submit',class:'primary','data-testid':'publish'}), error);

  const activePanel = activeDetail ? panel(`当前生效：库容表 v${activeDetail.version}`,
    p(`来源计算 #${activeDetail.run_id} · 发布人 ${activeDetail.author} · 生效时间 ${date(activeDetail.activated_at)}`,'filename'),
    table([
      {key:'level',label:'档位'},
      {key:'rank',label:'液位排序'},
      {key:'volume',label:'库容（m³）',render:row=>value(row.volume)},
      {label:'采用试验',render:row=>row.evidence.length ? row.evidence.join('、') : '空池基准'},
    ], activeDetail.levels, {caption:'当前生效库容表'}),
    link('打开机电交班报告','#delivery',{class:'quiet'}))
    : panel('当前生效库容表', empty('还没有发布过库容表。算齐全部档位后在此一次性切换。'));

  const versionList = table([
    {label:'版本',render:row=>row.active ? pill(`v${row.version}（生效中）`,'feasible') : `v${row.version}`},
    {key:'run_id',label:'来源计算'},
    {key:'author',label:'发布人'},
    {label:'生效时间',render:row=>date(row.activated_at)},
    {label:'详情',render:row=>link('查看',`#delivery/${row.id}`)},
  ], tables, {caption:'历史版本', empty:'暂无历史版本。'});

  const runStatus = table([
    {label:'计算',render:row=>link(row.name,`#runs/${row.id}`)},
    {label:'状态',render:row=>pill(RUN_STATUS[row.status] || row.status, row.status)},
    {label:'待补测档数',render:row=>value(row.result.pending_count)},
    {label:'可否发布',render:row=>row.status === 'feasible' && row.result.pending_count === 0
      ? pill('可发布','feasible') : pill('不可发布','blocked')},
  ], runs, {caption:'各次计算的发布门槛', empty:'还没有计算记录。'});

  return el('div',{class:'two-col'},
    el('div',{class:'wide-panel'}, activePanel, panel('版本历史', versionList)),
    el('aside',{class:'sidebar-panel'},
      publishForm || p('仅复核主管可以发布库容表。','empty'),
      panel('发布门槛', runStatus)));
}
