import {RUN_STATUS} from '../constants/enums.js';
import {panel, metrics, pill, empty} from '../components/common/panels.js';
import {table} from '../components/common/table.js';
import {session} from '../stores/session.js';
import {workspace} from '../stores/workspace.js';
import {el, h, link, p} from '../utils/dom.js';
import {date} from '../utils/format.js';

export async function overview() {
  const {spec, levels, experiments, runs, tables} = workspace;
  const latest = runs[0];
  const activeTable = tables.find(item => item.active);
  const feed = session.canReview ? await workspace.audit() : [];
  const activeCount = experiments.filter(item => item.active).length;
  const latestRun = latest?.result;
  const metricItems = [
    {label:'档位数量', value:levels.length},
    {label:'启用试验', value:activeCount},
    {label:'校准计算', value:runs.length},
    {label:'生效库容表', value:activeTable ? `v${activeTable.version}` : '未发布'},
  ];
  return el('div', {class:'overview'},
    el('div', {class:'overview-main'},
      el('section', {class:'hero'}, p(spec.organization,'eyeline'), h(2,spec.subtitle), p(spec.workflow,'intro-copy'),
        el('div',{class:'actions'}, link(spec.pages[1], '#inputs', {class:'primary'}), link(spec.pages[2], '#experiments',{class:'quiet'}))),
      panel('业务处理步骤', el('ol', {class:'work-steps'}, spec.steps.map(text => el('li', {}, text)))),
      feed.length && panel('最近审计事件',table([
        {key:'actor',label:'操作者'}, {key:'event',label:'动作'}, {key:'target',label:'关联记录'},
        {label:'时间',render:row=>date(row.created_at)},
      ],feed.slice(0,8),{caption:'最近审计事件'}))),
    el('aside', {class:'sidebar-panel'},
      panel('校准概况', metrics(metricItems)),
      panel('最近计算', latest ? el('div',{class:'activity'},link(latest.name,`#runs/${latest.id}`),
        pill(RUN_STATUS[latest.status] || latest.status, latest.status),
        latestRun && p(`已确认 ${latestRun.confirmed_count} 档 · 待补测 ${latestRun.pending_count} 档`,'subtle'),
        p(date(latest.created_at),'subtle'))
        : empty('录入试验后发起首次校准计算。','#runs','前往解算')),
      panel('现场问题', el('ul',{class:'method-list'}, spec.pains.map(text => el('li',{},text))))));
}
