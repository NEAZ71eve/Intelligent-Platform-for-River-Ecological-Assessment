const test = require('node:test');
const assert = require('node:assert/strict');
const { capability, resultView } = require('../lib/recognition');
const { task } = require('../lib/format');

test('recognition capability supports detailed metadata and legacy disabled health', () => {
  assert.equal(capability({ features: { recognition: false } }).enabled, false);
  assert.equal(capability({ features: { recognition: true } }).enabled, true);
  const current = capability({ features: { recognition: true }, recognition: { enabled: true, model_name: 'Plant subset', model_version: '1.0', labels: [{ id: 'a', name: '类别甲' }], scope: '教学范围', threshold: .75 } });
  assert.equal(current.modelVersion, '1.0');
  assert.equal(current.labels[0].name, '类别甲');
  assert.equal(current.scope, '教学范围');
  assert.equal(capability({ features: { recognition: true }, recognition: { enabled: false } }).enabled, false);
});

test('a successful recognition preserves top three, model metadata and calibrated-language boundary', () => {
  const view = resultView({ decision: 'recognized', candidates: [
    { label: 'a', name: '类别甲', score: .81, content_id: 'article-id' },
    { label: 'b', name: '类别乙', score: .1 },
    { label: 'c', name: '类别丙', score: .05 },
    { label: 'd', name: '类别丁', score: .04 },
  ], threshold: .75, model: { name: 'Plant subset', version: '1.0' }, disclaimer: '教学模型，候选分数不是正确率。' });
  assert.equal(view.recognized, true);
  assert.equal(view.candidates.length, 3);
  assert.equal(view.candidates[0].score_label, '0.810');
  assert.equal(view.candidates[0].content_id, 'article-id');
  assert.equal(view.model_version, '1.0');
  assert.equal(view.threshold_label, '0.750');
  assert.equal(view.disclaimer, '教学模型，候选分数不是正确率。');
});

test('uncertain results never become a confident label even if one candidate is present', () => {
  const view = resultView({ decision: 'uncertain', candidates: [{ label: 'a', name: '类别甲', score: .4 }], threshold: .75 });
  assert.equal(view.recognized, false);
  assert.equal(view.heading, '暂时无法确认');
  assert.equal(view.candidates[0].name, '类别甲');
});

test('malformed or unsupported results do not fabricate scores or a recognition', () => {
  assert.equal(resultView(null), null);
  const view = resultView({ decision: 'recognized', candidates: [] });
  assert.equal(view.recognized, false);
  const invalid = resultView({ decision: 'uncertain', candidates: [{ label: 'a', score: NaN }, { label: 'b', score: null }, { label: 'c', score: 12 }] });
  assert.ok(invalid.candidates.every((candidate) => candidate.score_label === '—' && candidate.bar_width === '0'));
});

test('disabled-model failure has no result while succeeded uncertain stays a completed task', () => {
  const disabled = task({ status: 'failed', error_code: 'MODEL_NOT_CONFIGURED', result: { decision: 'recognized', candidates: [{ name: 'bad' }] } });
  assert.equal(disabled.result_view, null);
  assert.match(disabled.error_label, /未产生识别结论/);
  const uncertain = task({ status: 'succeeded', result: { decision: 'uncertain', candidates: [{ label: 'a', score: .2 }] } });
  assert.equal(uncertain.status_label, '处理完成');
  assert.equal(uncertain.result_view.heading, '暂时无法确认');
});

test('low-quality result explains that classification was not performed and shows no invented candidates', () => {
  const view = resultView({ decision: 'uncertain', reason: 'LOW_IMAGE_QUALITY', candidates: [], threshold: .75, model: { name: 'Flower prototype', version: '1.0' } });
  assert.equal(view.heading, '暂时无法确认');
  assert.match(view.explanation, /未进行类别判断/);
  assert.equal(view.candidates.length, 0);
  assert.equal(view.model_version, '1.0');
});

test('zero threshold is disclosed as candidate reference without promising low-score rejection', () => {
  const current = capability({ recognition: { enabled: true, threshold: 0 } });
  assert.match(current.thresholdNote, /未启用低分拒识/);
  const view = resultView({ decision: 'recognized', threshold: 0, candidates: [{ label: 'a', name: '类别甲', score: .21 }], model: { version: 'v1' } });
  assert.equal(view.heading, '候选参考：类别甲');
  assert.match(view.threshold_note, /未启用低分拒识/);
  const historical = resultView({ decision: 'uncertain', threshold: .8, candidates: [{ label: 'a', score: .5 }], model: { version: 'older' } });
  assert.match(historical.threshold_note, /低于分类分数阈值/);
  assert.doesNotMatch(historical.threshold_note, /未启用/);
});
