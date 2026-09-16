function list(envelope) { return Array.isArray(envelope && envelope.data) ? envelope.data : []; }
function time(value) {
  if (!value) return '暂无时间';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '时间未知';
  const china = new Date(date.getTime() + 8 * 3600000);
  const two = (num) => String(num).padStart(2, '0');
  return `${china.getUTCFullYear()}-${two(china.getUTCMonth() + 1)}-${two(china.getUTCDate())} ${two(china.getUTCHours())}:${two(china.getUTCMinutes())} UTC+8`;
}
function value(input, suffix) { return input === null || input === undefined ? '—' : `${input}${suffix || ''}`; }
function message(error) { return error && error.message || '操作未完成，请重试'; }
function task(item) {
  const states = { queued: '等待处理', running: '处理中', succeeded: '处理完成', failed: '处理失败' };
  return Object.assign({}, item, {
    status_label: states[item.status] || item.status,
    created_label: time(item.created_at),
    error_label: item.error_code === 'MODEL_NOT_CONFIGURED' ? '真实模型尚未配置（M3），本次未产生识别结论。' : (item.message || item.error_message || ''),
  });
}
module.exports = { list, time, value, message, task };
