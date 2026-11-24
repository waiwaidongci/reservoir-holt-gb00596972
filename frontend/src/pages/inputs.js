import {feedback, field} from '../components/common/fields.js';
import {panel} from '../components/common/panels.js';
import {table} from '../components/common/table.js';
import {handler} from '../hooks/action.js';
import {session} from '../stores/session.js';
import {workspace} from '../stores/workspace.js';
import {button, el, p} from '../utils/dom.js';
import {value} from '../utils/format.js';

export async function inputs(route, refresh) {
  const {spec, levels, baselines} = workspace;
  const error = feedback();
  const baselineOf = Object.fromEntries(baselines.map(item => [item.level, item.volume]));

  const levelForm = session.canWrite && el('form',{class:'fields',onSubmit:handler(button('新增档位',{type:'submit',class:'primary'}),error,async event=>{
    const data = new FormData(event.target);
    await workspace.addLevel({code:data.get('code'), rank:Number(data.get('rank'))});
    event.target.reset();
    await refresh();
  })}, field({key:'code',label:'档位编号',type:'string',max_length:40}),
    field({key:'rank',label:'液位排序（数字越小液位越低）',type:'int',min:1,max:1000}),
    button('新增档位',{type:'submit',class:'primary'}), error);

  const baselineForm = session.canWrite && el('form',{class:'fields',onSubmit:handler(button('保存空池基准',{type:'submit',class:'primary'}),error,async event=>{
    const data = new FormData(event.target);
    await workspace.saveBaseline({level:data.get('level'), volume:Number(data.get('volume'))});
    await refresh();
  })}, el('label',{class:'field'},el('span',{},'档位'),
      el('select',{name:'level',required:true}, levels.map(item=>el('option',{value:item.code},
        `${item.code}（排序 ${item.rank}）`)))),
    field({key:'volume',label:'空池基准库容（m³）',type:'number',min:0,max:1000000}),
    button('保存空池基准',{type:'submit',class:'primary'}), error);

  const levelTable = table([
    {key:'code',label:'档位编号'},
    {key:'rank',label:'液位排序'},
    {label:'空池基准库容（m³）',render:row=>value(baselineOf[row.code])},
  ], levels, {caption:'档位与空池基准', empty:'还没有档位，请先新增。'});

  return el('div',{class:'two-col'},
    el('div',{class:'wide-panel'}, panel('档位与空池基准',
      p('档位按液位从低到高排列；空池基准给出该档位库容的等式锚点，重复保存即更正。','subtle'),
      levelTable)),
    el('aside',{class:'sidebar-panel'},
      levelForm && panel('新增档位', levelForm),
      baselineForm && panel('空池基准', baselineForm),
      panel('口径说明', el('ul',{class:'method-list'}, spec.methodology.slice(0,2).map(text=>el('li',{},text))))));
}
