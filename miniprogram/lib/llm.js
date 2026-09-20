const { time } = require('./format');
const CONSENT_VERSION = 'deepseek-v1';
const DISCLAIMER = 'AI 解读可能出错或缺少依据。它不会改变原识别结果，不是物种鉴定、饮用安全结论或官方水质评价。';
const STATES = { queued: '等待解读', running: '正在解读', succeeded: '解读完成', failed: '本轮未完成' };
function pending(turn) { return turn && ['queued', 'running'].includes(turn.status); }
function quotaView(quota) {
  if (!quota || !Number.isInteger(quota.remaining) || !Number.isInteger(quota.limit) || !Number.isInteger(quota.used) || !Number.isInteger(quota.reserved)) return null;
  return Object.assign({}, quota, { reset_label: time(quota.reset_at) });
}
function turnView(turn) {
  if (!turn || typeof turn.id !== 'string' || !turn.id || !STATES[turn.status]) throw new Error('AI 解读返回格式不正确，请刷新核对。');
  return Object.assign({}, turn, { status_label: STATES[turn.status], created_label: time(turn.created_at), finished_label: turn.finished_at ? time(turn.finished_at) : '', image_label: pending(turn) ? '图像使用情况待处理完成后确认' : turn.used_image ? '本轮使用了原图与文字结果' : '本轮仅使用文字结果与对话', answer: typeof turn.answer === 'string' ? turn.answer : '' });
}
function sessionView(session) {
  if (!session || typeof session.id !== 'string' || !session.id || !['recognition', 'assessment'].includes(session.kind)) throw new Error('AI 会话返回格式不正确，请刷新核对。');
  const context = session.context_summary;
  return Object.assign({}, session, { created_label: time(session.created_at), expires_label: time(session.expires_at), kind_label: session.kind === 'recognition' ? '花卉识别解读' : '河道观察解读', context_text: typeof context === 'string' ? context : context ? JSON.stringify(context, null, 2) : '原始结果摘要暂不可用。' });
}
function pageKey(path, endpoint) {
  if (typeof path !== 'string' || /[\s\\#]/.test(path)) throw new Error('AI 记录分页地址无效，请刷新重试。');
  const match = path.match(/^(?:https?:\/\/[^/?#]+)?(?:\/api\/v1\/)?(llm\/(?:sessions\/|sessions\/[^/?]+\/turns\/))(\?[^#]*)?$/);
  if (!match || match[1] !== endpoint) throw new Error('AI 记录分页地址无效，请刷新重试。');
  return match[1] + (match[2] || '');
}
function readPage(response, path, endpoint, seen) {
  if (!response || !Array.isArray(response.data)) throw new Error('AI 记录返回格式不正确，请重试。');
  const key = pageKey(path, endpoint), next = response.meta && response.meta.next;
  if (seen.has(key) || (next && (typeof next !== 'string' || seen.has(pageKey(next, endpoint)) || pageKey(next, endpoint) === key))) throw new Error('AI 记录分页重复，请刷新重试。');
  if (next !== undefined && next !== null && typeof next !== 'string') throw new Error('AI 记录分页格式不正确，请重试。');
  return { key, items: response.data, next: next || '' };
}
function requestId() {
  // Correlation/idempotency key only; never an authentication credential.
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (letter) => {
    const value = Math.floor(Math.random() * 16);
    return (letter === 'x' ? value : (value & 3) | 8).toString(16);
  });
}
function defaultQuestion(kind) { return kind === 'assessment' ? '请结合本次河道图像观察结果，解释候选、局限和可以继续观察的内容，不要据此判断真实水质。' : '请结合本次花卉识别结果，解释候选与不确定性，并给出可用于核对的观察要点。'; }
module.exports = { CONSENT_VERSION, DISCLAIMER, pending, quotaView, turnView, sessionView, pageKey, readPage, requestId, defaultQuestion };
