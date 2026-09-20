const CATEGORY_NAMES = { plants: '植物知识', water: '水资源保护', green: '绿色生活', travel: '生态智游' };
const PLANT_NAMES = { daisy: '雏菊类花卉', dandelion: '蒲公英类花卉', roses: '蔷薇属花卉', sunflowers: '向日葵类花卉', tulips: '郁金香类花卉' };
function tagName(value, kind, supplied) {
  const names = kind === 'category' ? CATEGORY_NAMES : PLANT_NAMES;
  return names[value] || supplied || value;
}
function contentView(item) {
  return Object.assign({}, item, {
    category_name: tagName(item.category, 'category'),
    plant_name: item.plant_label ? tagName(item.plant_label, 'plant') : '',
  });
}
function routeView(item) {
  return Object.assign({}, item, {
    public_stop_count: Number.isInteger(item.stop_count) && item.stop_count >= 0 ? item.stop_count : null,
  });
}
function choices(items, kind, selected) {
  const result = [{ value: '', name: kind === 'category' ? '全部分类' : '全部植物标签' }];
  (items || []).forEach((item) => {
    if (item && typeof item.value === 'string' && item.value && !result.some((entry) => entry.value === item.value)) {
      result.push({ value: item.value, name: tagName(item.value, kind, item.name), count: item.count });
    }
  });
  if (selected && !result.some((item) => item.value === selected)) result.push({ value: selected, name: tagName(selected, kind) });
  return result;
}
function pageData(response, requestedPath, seen) {
  if (!response || !Array.isArray(response.data)) throw new Error('列表返回格式不正确，请稍后重试。');
  const next = response.meta && response.meta.next || '';
  if (next && (typeof next !== 'string' || next === requestedPath || seen.has(next))) throw new Error('列表分页异常，请刷新后重试。');
  return { items: response.data, next };
}
function appendUnique(previous, items) {
  const ids = new Set(previous.map((item) => item.id));
  return previous.concat(items.filter((item) => { if (ids.has(item.id)) return false; ids.add(item.id); return true; }));
}
module.exports = { tagName, contentView, routeView, choices, pageData, appendUnique };
