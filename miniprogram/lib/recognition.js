function thresholdNote(threshold) {
  if (threshold === 0) return '当前版本未启用低分拒识。图片质量合格时会在支持类别中给出候选，范围外对象也可能得到高分；结果仅供观察参考。';
  if (typeof threshold === 'number' && Number.isFinite(threshold) && threshold > 0 && threshold <= 1) return '低于分类分数阈值时显示“暂时无法确认”；此规则不能保证排除范围外对象。';
  return '服务端未提供有效分类阈值，请仅将候选作为观察参考。';
}

function capability(health) {
  const details = health && health.recognition || {};
  const enabled = details.enabled === true || (details.enabled === undefined && health && health.features && health.features.recognition === true);
  return {
    enabled: Boolean(enabled),
    scope: details.scope || (enabled ? '识别范围以当前启用模型的覆盖类别为限。' : '当前没有启用图像识别模型。'),
    labels: (Array.isArray(details.labels) ? details.labels : []).filter((label) => label && typeof label === 'object').map((label) => ({ id: label.id || label.label || label.name, name: label.name || label.label || label.id })),
    modelName: details.model_name || '',
    modelVersion: details.model_version || '',
    threshold: details.threshold,
    thresholdNote: thresholdNote(details.threshold),
  };
}

/** Scores are model outputs, not calibrated probabilities of correctness. */
function resultView(result) {
  if (!result || typeof result !== 'object') return null;
  const candidates = (Array.isArray(result.candidates) ? result.candidates : []).filter((candidate) => candidate && typeof candidate === 'object').slice(0, 3).map((candidate, index) => {
    const valid = typeof candidate.score === 'number' && Number.isFinite(candidate.score) && candidate.score >= 0 && candidate.score <= 1;
    return Object.assign({}, candidate, {
      rank: index + 1,
      name: candidate.name || candidate.label || '未命名类别',
      score_label: valid ? candidate.score.toFixed(3) : '—',
      bar_width: valid ? (candidate.score * 100).toFixed(1) : '0',
    });
  });
  const recognized = result.decision === 'recognized' && candidates.length > 0 && candidates[0].score_label !== '—';
  const lowQuality = result.reason === 'LOW_IMAGE_QUALITY';
  return {
    recognized,
    reason: result.reason || '',
    decision: recognized ? 'recognized' : 'uncertain',
    heading: recognized ? (result.threshold === 0 ? '候选参考：' : '识别结果：') + candidates[0].name : '暂时无法确认',
    explanation: recognized ? '模型从支持类别中给出的候选，可结合科普资料进一步核对；未验证校园实拍与范围外对象。' : lowQuality ? '图片质量不足，本次未进行类别判断。请上传尺寸足够、主体清晰的照片。' : '这张照片不足以给出确定结果。请对准单个主体重新拍摄，或确认对象属于支持类别。',
    candidates,
    threshold_label: typeof result.threshold === 'number' && Number.isFinite(result.threshold) ? result.threshold.toFixed(3) : '未提供',
    threshold_note: thresholdNote(result.threshold),
    model_name: result.model && result.model.name || '未提供模型名称',
    model_version: result.model && result.model.version || '未提供版本',
    disclaimer: result.disclaimer || '候选分数未经校准，不代表判断正确的概率；覆盖类别之外的对象可能被误识别。',
  };
}
module.exports = { capability, resultView };
