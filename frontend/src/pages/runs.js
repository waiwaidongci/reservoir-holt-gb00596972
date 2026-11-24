import {feedback, field} from '../components/common/fields.js';
import {empty, panel, pill} from '../components/common/panels.js';
import {table} from '../components/common/table.js';
import {LEVEL_STATUS, RUN_STATUS} from '../constants/enums.js';
import {handler} from '../hooks/action.js';
import {session} from '../stores/session.js';
import {workspace} from '../stores/workspace.js';
import {button, el, link, p} from '../utils/dom.js';
import {date, value} from '../utils/format.js';

function resultPanel(run) {
  const result = run.result;
  if (run.status === 'infeasible') {
    const diagnosis = result.diagnosis;
    const groups = diagnosis.removal_groups.length
      ? table([{label:'最少冲突组（撤掉任一组即恢复可行）',
                render:row=>el('span',{class:'tag-row'},
                  row.group.map(code=>pill(code,'blocked')))}],
              diagnosis.removal_groups.map(group=>({group})), {caption:'最少冲突组', pageSize:5})
      : p('冲突只涉及空池基准或单调性结构，停用试验无法修复，请检查基准数据。','feedback');
    return panel(run.name,
      pill(RUN_STATUS.infeasible,'infeasible'),
      p('当前约束出现负环，没有任何库容组合能同时满足，全部档位标记为冲突阻塞。','intro-copy'),
      panel('无解诊断',
        p(`涉及档位：${diagnosis.negative_levels.join('、') || '—'}`,'subtle'),
        diagnosis.structural && p('检测到结构性冲突（基准或单调性自相矛盾），撤试验无法修复，请核对空池基准。','feedback'),
        groups,
        diagnosis.budget_limited && p('组合规模较大，已按贪心给出建议组，可在试验页停用后重新解算。','subtle')));
  }

  const rows = result.rows;
  return panel(run.name,
    pill(RUN_STATUS.feasible,'feasible'),
    p(`已确认 ${result.confirmed_count} 档，待补测 ${result.pending_count} 档。只有全部确认才能发布库容表。`,'intro-copy'),
    table([
      {key:'level',label:'档位'},
      {label:'状态',render:row=>pill(LEVEL_STATUS[row.status], row.status)},
      {label:'库容（m³）',render:row=>row.status === 'confirmed' ? value(row.volume) : '待补测'},
      {label:'可行区间（m³）',render:row=>row.status === 'confirmed'
        ? value(row.volume)
        : `${value(row.min_volume)} ~ ${value(row.max_volume)}`},
      {label:'采用试验',render:row=>row.evidence.length ? row.evidence.join('、') : '—'},
    ], rows, {caption:'各档解算结果'}));
}

export async function runPage(route, refresh) {
  const {spec, runs, experiments} = workspace;
  const error = feedback();
  const id = route.id || runs[0]?.id;
  const selected = id ? await workspace.getRun(id) : null;

  const activeExperiments = experiments.filter(item=>item.active);
  const startForm = session.canWrite && el('form',{class:'fields',onSubmit:handler(button('发起校准计算',{type:'submit',class:'primary'}),error,async event=>{
    event.preventDefault();
    const data = new FormData(event.target);
    const run = await workspace.startRun({name:data.get('name') || `校准 ${new Date().toLocaleString('zh-CN')}`,
                                          experiment_codes:[]});
    location.hash = `#runs/${run.id}`;
  })}, field({key:'name',label:'计算名称',type:'string',required:false,max_length:120},
      `样本${spec.run}`),
    p(`将使用当前全部 ${activeExperiments.length} 条启用试验与全部空池基准，输入在计算时固化为快照。`,'subtle'),
    button('发起校准计算',{type:'submit',class:'primary','data-testid':'start-run'}), error);

  const runList = table([
    {label:'计算',render:item=>link(item.name,`#runs/${item.id}`)},
    {label:'状态',render:item=>pill(RUN_STATUS[item.status] || item.status, item.status)},
    {label:'确认/待补测',render:item=>`${item.result.confirmed_count} / ${item.result.pending_count}`},
    {label:'时间',render:item=>date(item.created_at)},
  ], runs, {caption:'计算记录', empty:'发起首次校准计算后在此显示。'});

  return el('div',{class:'two-col'},
    el('div',{class:'wide-panel'},
      selected ? resultPanel(selected) : panel(spec.pages[3], empty('还没有可查看的计算。','#experiments','先录入试验'))),
    el('aside',{class:'sidebar-panel'},
      startForm && panel(spec.run, startForm),
      panel('计算记录', runList),
      panel('解算口径', el('ul',{class:'method-list'}, spec.methodology.slice(2).map(text=>el('li',{},text))))));
}
