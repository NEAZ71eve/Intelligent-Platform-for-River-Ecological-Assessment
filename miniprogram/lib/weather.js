const { time, value } = require('./format');

function section(raw) {
  const item = raw || {};
  const status = item.status || 'unavailable';
  return Object.assign({}, item, {
    status, available: Boolean(item.data), stale: status === 'stale',
    status_label: status === 'stale' ? '历史缓存 · 更新暂不可用' : status === 'unavailable' ? '暂不可用' : '近期更新',
    fetched_label: item.fetched_at ? time(item.fetched_at) : '',
    expires_label: item.expires_at ? time(item.expires_at) : '',
    attribution: (Array.isArray(item.attributions) ? item.attributions : []).join('；'),
    sources: (item.refer && Array.isArray(item.refer.sources) ? item.refer.sources : []).join('；'),
  });
}

function weatherView(summary) {
  const weather = section(summary.weather), air = section(summary.air), alerts = section(summary.alerts);
  const w = weather.data || {}, a = air.data || {};
  weather.temp_label = value(w.temperature, w.temperature_unit || '°C');
  weather.humidity_label = value(w.humidity_percent, '%');
  weather.condition_label = w.condition || '天气情况暂无';
  air.aqi_label = value(a.aqi_display === undefined || a.aqi_display === '' ? a.aqi : a.aqi_display);
  air.pollutants = (a.pollutants || []).map((item) => Object.assign({}, item, { value_label: value(item.value, item.unit ? ' ' + item.unit : '') }));
  alerts.empty = alerts.status === 'empty' && Boolean(alerts.data && alerts.data.zero_result);
  alerts.items = ((alerts.data || {}).items || []).map((item) => Object.assign({}, item, {
    issued_label: time(item.issued_at), effective_label: time(item.effective_at), expires_label: time(item.expires_at),
    message_label: ({ cancel: '已取消', update: '更新公告', alert: '预警公告' })[String(item.message_type || '').toLowerCase()] || item.message_type || '预警公告',
  }));
  return { weather, air, alerts };
}
module.exports = { weatherView };
