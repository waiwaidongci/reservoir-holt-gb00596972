import {request, saveFile} from '../api/http.js';
import {session} from './session.js';

const call = (path, body) => request(path, {token:session.token, body});
export const workspace = {
  spec: null,
  levels: [],
  baselines: [],
  experiments: [],
  runs: [],
  tables: [],
  async init() { this.spec = await request('/spec'); },
  async refresh() {
    [this.levels, this.baselines, this.experiments, this.runs, this.tables] = await Promise.all([
      call('/levels'), call('/baselines'), call('/experiments'), call('/runs'), call('/tables')]);
  },
  addLevel: data => call('/levels', data),
  saveBaseline: data => call('/baselines', data),
  submitBatch: data => call('/experiments/batch', data),
  importCsv: data => call('/experiments/csv', data),
  startRun: data => call('/runs', data),
  getRun: id => call(`/runs/${id}`),
  activeTable: () => call('/tables/active'),
  getTable: id => call(`/tables/${id}`),
  publish: data => call('/tables/publish', data),
  audit: () => call('/audit'),
  download: (path, filename) => saveFile(path, session.token, filename),
};
