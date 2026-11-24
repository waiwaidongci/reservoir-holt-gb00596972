export const pages = ['overview', 'inputs', 'experiments', 'runs', 'publish', 'delivery'];

export function route() {
  const [page, id, offset] = location.hash.slice(1).split('/');
  return {page:pages.includes(page) ? page : 'overview', id:Number(id) || null, offset:Math.max(0, Number(offset) || 0)};
}
