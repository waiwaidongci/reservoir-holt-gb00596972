import {feedback} from '../components/common/fields.js';
import {panel, pill} from '../components/common/panels.js';
import {table} from '../components/common/table.js';
import {handler} from '../hooks/action.js';
import {session} from '../stores/session.js';
import {workspace} from '../stores/workspace.js';
import {button, el, p} from '../utils/dom.js';
import {date, value} from '../utils/format.js';

const ROW_COUNT = 4;

function experimentRow(levels, index) {
  const levelOptions = selected => levels.map(item =>
    el('option',{value:item.code, selected:item.code === selected || undefined}, `${item.code}（${item.rank}）`));
  return el('tr',{},
    el('td',{}, el('input',{name:`code_${index}`,placeholder:'如 T09',maxlength:40,'aria-label':'试验编号'})),
    el('td',{}, el('select',{name:`from_${index}`,'aria-label':'排水前档位'}, el('option',{value:''},'—'), ...levelOptions())),
    el('td',{}, el('select',{name:`to_${index}`,'aria-label':'排水后档位'}, el('option',{value:''},'—'), ...levelOptions())),
    el('td',{}, el('input',{name:`min_${index}`,type:'number',min:0,step:'any',placeholder:'最小排水量','aria-label':'最小排水量'})),
    el('td',{}, el('input',{name:`max_${index}`,type:'number',min:0,step:'any',placeholder:'最大排水量','aria-label':'最大排水量'})),
    el('td',{}, el('input',{name:`note_${index}`,maxlength:300,placeholder:'备注（可空）','aria-label':'备注'})));
}

function collectRows(form, levels) {
  const data = new FormData(form);
  const rows = [];
  for (let i = 0; i < ROW_COUNT; i += 1) {
    const code = (data.get(`code_${i}`) || '').trim();
    if (!code) continue;
    const fromLevel = data.get(`from_${i}`);
    const toLevel = data.get(`to_${i}`);
    const minText = data.get(`min_${i}`);
    const maxText = data.get(`max_${i}`);
    if (!fromLevel || !toLevel) throw new Error(`第 ${i + 1} 行请选择排水前后档位`);
    const drainMin = Number(minText);
    const drainMax = Number(maxText);
    if (!Number.isFinite(drainMin) || !Number.isFinite(drainMax)) throw new Error(`第 ${i + 1} 行排水量必须是数字`);
    rows.push({code, from_level:fromLevel, to_level:toLevel, drain_min:drainMin,
               drain_max:drainMax, note:(data.get(`note_${i}`) || '').trim()});
  }
  if (!rows.length) throw new Error('请至少填写一行试验');
  return rows;
}

export async function experimentsPage(route, refresh) {
  const {spec, levels, experiments} = workspace;
  const error = feedback();
  const grid = el('table',{}, el('thead',{}, el('tr',{},
    ['试验编号','排水前档位','排水后档位','最小排水量（m³）','最大排水量（m³）','备注'].map(label=>el('th',{scope:'col'},label)))),
    el('tbody',{}, Array.from({length:ROW_COUNT},(_,i)=>experimentRow(levels,i))));

  const submit = button('整单提交（补测与更正一起收）',{type:'submit',class:'primary'});
  const form = session.canWrite && el('form',{class:'fields',onSubmit:handler(submit,error,async event=>{
    const payload = {experiments: collectRows(event.target, levels), baselines: [], disable_codes: []};
    const summary = await workspace.submitBatch(payload);
    event.target.reset();
    error.textContent = `已收录：新增 ${summary.created.length} 条、更正 ${summary.corrected.length} 条`;
    await refresh();
  })}, grid, p('同一编号再次提交即更正原记录；整单任一内容不合法会全部退回，不会只收一半。','subtle'), submit, error);

  const fileInput = el('input',{type:'file',name:'source',accept:'.csv,text/csv'});
  const csvForm = session.canWrite && el('form',{class:'fields',onSubmit:handler(button('导入 CSV',{type:'submit',class:'quiet'}),error,async event=>{
    event.preventDefault();
    const data = new FormData(event.target);
    const file = data.get('source');
    if (!file?.size) throw new Error('请选择一个 CSV 文件');
    if (file.size > 2_000_000) throw new Error('CSV 最多 2 MB');
    const result = await workspace.importCsv({csv_text: await file.text()});
    error.textContent = `CSV 导入 ${result.rows} 条，新增 ${result.created.length} 条、更正 ${result.corrected.length} 条`;
    await refresh();
  })}, el('label',{class:'field'},el('span',{},'试验 CSV'),fileInput),
    button('下载模板',{type:'button',class:'quiet',onClick:()=>workspace.download('/template',spec.sample_name)}),
    button('导入 CSV',{type:'submit',class:'quiet'}));

  const disableInput = el('input',{name:'codes',placeholder:'多个编号用逗号分隔，如 T08、T09','aria-label':'要停用的试验编号'});
  const disableForm = session.canWrite && el('form',{class:'fields',onSubmit:handler(button('停用试验',{type:'submit',class:'quiet'}),error,async event=>{
    event.preventDefault();
    const data = new FormData(event.target);
    const codes = (data.get('codes') || '').split(/[，,、\s]+/).map(item=>item.trim()).filter(Boolean);
    if (!codes.length) throw new Error('请填写要停用的试验编号');
    const summary = await workspace.submitBatch({experiments:[], baselines:[], disable_codes:codes});
    error.textContent = `已停用：${summary.disabled.join('、') || '无（原本就未启用）'}`;
    event.target.reset();
    await refresh();
  })}, el('label',{class:'field'},el('span',{},'停用冲突试验'),disableInput),
    p('停用不删除历史，解算时自动排除；诊断给出的最少冲突组可直接填到这里。','subtle'),
    button('停用试验',{type:'submit',class:'quiet'}));

  const history = table([
    {key:'code',label:'试验编号'},
    {key:'from_level',label:'排水前'},
    {key:'to_level',label:'排水后'},
    {label:'排水量范围（m³）',render:row=>`${value(row.drain_min)} ~ ${value(row.drain_max)}`},
    {key:'note',label:'备注'},
    {label:'状态',render:row=>row.active ? pill('启用中','feasible') : pill('已停用','blocked')},
    {label:'更新时间',render:row=>date(row.updated_at)},
  ], experiments, {caption:'试验台账', empty:'还没有试验记录。'});

  return el('div',{class:'two-col'},
    el('div',{class:'wide-panel'}, panel('排水试验台账', history)),
    el('aside',{class:'sidebar-panel'},
      form && panel('试验录入', form),
      csvForm && panel('批量导入', csvForm),
      disableForm && panel('停用处理', disableForm)));
}
