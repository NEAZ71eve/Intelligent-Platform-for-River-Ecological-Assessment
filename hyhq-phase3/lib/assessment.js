const { time, message } = require('./format');

/** 评估大类中文名与展示色（检测框 / 问题清单共用）。 */
const CATEGORIES = {
  floating_debris: { name: '水面漂浮物', color: '#3a7d44' },
  bloom_blackwater: { name: '水华黑臭水体', color: '#4a6fa5' },
  outfall_discharge: { name: '排污口污水直排', color: '#c0392b' },
  bank_problem: { name: '岸带环境问题', color: '#d68910' },
};
const STATES = { queued: '等待处理', running: '评估中', succeeded: '评估完成', failed: '评估失败' };
const ERROR_LABELS = {
  MODEL_NOT_CONFIGURED: '评估模型当前未启用，本次未产生评估结论。',
  INFERENCE_TIMEOUT: '评估超时，服务端已停止本次任务，未产生结论。',
  LOW_IMAGE_QUALITY: '图片质量不足，本次未进行评估。请上传尺寸足够、主体清晰的照片。',
  LOW_CONFIDENCE: '未检出足够可信的生态问题目标，本次按"未发现问题"展示。',
  QUEUE_FULL: '等待处理的图片较多，请稍后重试。',
};

function category(name) { return CATEGORIES[name] || { name: name || '未知类别', color: '#8a8a8a' }; }

function areaLabel(ratio) {
  const value = typeof ratio === 'number' && Number.isFinite(ratio) ? ratio : 0;
  return (value * 100).toFixed(1) + '%';
}

/** 把 detections 聚合为问题清单：[{key,label,color,count,area_label}]，按数量倒序。 */
function issueList(detections) {
  const stat = {};
  (Array.isArray(detections) ? detections : []).forEach((item) => {
    if (!item || typeof item !== 'object') return;
    const key = item.eval_category || 'unknown';
    const entry = stat[key] = stat[key] || { count: 0, area_ratio: 0 };
    entry.count += 1;
    entry.area_ratio += Number(item.area_ratio) || 0;
  });
  return Object.keys(stat).map((key) => {
    const cat = category(key);
    return { key, label: cat.name, color: cat.color, count: stat[key].count, area_ratio: stat[key].area_ratio, area_label: areaLabel(stat[key].area_ratio) };
  }).sort((a, b) => b.count - a.count);
}

/** AssessmentJob 响应 → 任务行/状态视图（列表与结果页共用）。 */
function assessmentTask(item) {
  if (!item || typeof item !== 'object') return { status: 'failed', status_label: '评估失败' };
  return Object.assign({}, item, {
    status_label: STATES[item.status] || item.status || '状态未知',
    created_label: time(item.created_at),
    error_label: ERROR_LABELS[item.error_code] || item.message || item.error_message || '',
    sub_label: item.status === 'succeeded' && item.grade ? '生态等级 ' + item.grade + ' · ' + item.score + ' 分' : (ERROR_LABELS[item.error_code] || item.message || ''),
  });
}

/** 成功任务 → 结果视图：等级徽章 + 问题清单 + 原因 + 检测框（像素坐标，绘制时按原图尺寸换算）。 */
function resultView(job) {
  if (!job || job.status !== 'succeeded') return null;
  const grade = job.grade || '—';
  const score = typeof job.score === 'number' && Number.isFinite(job.score) ? job.score : null;
  const gradeKey = { '优': 'excellent', '良': 'good', '中': 'fair', '差': 'poor' }[grade] || 'unknown';
  const gradeDesc = {
    excellent: '画面内未检出明显生态问题，或问题极少。',
    good: '检出少量生态问题，建议关注并记录。',
    fair: '检出较明显生态问题，建议安排复核与处置。',
    poor: '检出严重生态问题，建议尽快上报处置。',
    unknown: '等级未知，请查看问题清单。',
  }[gradeKey];
  const boxes = (Array.isArray(job.detections) ? job.detections : []).filter((d) => d && typeof d === 'object'
    && [d.x1, d.y1, d.x2, d.y2].every((v) => typeof v === 'number' && Number.isFinite(v)))
    .map((d) => ({
      x1: d.x1, y1: d.y1, x2: d.x2, y2: d.y2,
      label: d.label || category(d.eval_category).name,
      conf_label: typeof d.conf === 'number' && Number.isFinite(d.conf) ? (d.conf * 100).toFixed(0) + '%' : '—',
      color: category(d.eval_category).color,
    }));
  return {
    grade, score, grade_key: gradeKey, grade_desc: gradeDesc,
    score_label: score === null ? '—' : String(score),
    issues: issueList(job.detections),
    causes: (Array.isArray(job.causes) ? job.causes : []).filter((c) => c && c.text).map((c) => c.text),
    boxes,
    rule_version: job.rule_version || '—',
    duration_label: typeof job.duration_ms === 'number' && Number.isFinite(job.duration_ms) ? (job.duration_ms / 1000).toFixed(1) + 's' : '—',
    disclaimer: job.disclaimer || '平台演示评分，非官方水质评价。',
  };
}

/** 观测指标行 → 展示行（标注模拟来源）。 */
function metricView(item) {
  if (!item || typeof item !== 'object') return null;
  const value = typeof item.value === 'number' && Number.isFinite(item.value) ? item.value : null;
  return {
    name: item.metric_name || item.metric_code || '指标',
    value_label: value === null ? '—' : String(value),
    unit: item.unit || '',
    observed_label: time(item.observed_at),
    simulated: item.is_simulated === true || item.source_type === 'simulation',
  };
}

module.exports = { CATEGORIES, ERROR_LABELS, assessmentTask, resultView, metricView, issueList, category, areaLabel };
