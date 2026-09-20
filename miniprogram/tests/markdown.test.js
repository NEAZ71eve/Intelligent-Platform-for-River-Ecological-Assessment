const test = require('node:test');
const assert = require('node:assert/strict');
const { renderMarkdown, MAX_CHARACTERS, MAX_NODES } = require('../lib/markdown');
function flatten(nodes) { return nodes.flatMap((node) => [node].concat(node.children ? flatten(node.children) : [])); }
function textOf(nodes) { return flatten(nodes).filter((node) => node.type === 'text').map((node) => node.text).join(''); }

test('model Markdown renders headings, emphasis, nested ordered lists, quotes, code and aligned tables', () => {
  const nodes = renderMarkdown('# 花朵观察\n\n**候选** 与 *局限*，~~旧结论~~。\n下一行 `pH < 7`\n\n3. 先看花瓣\n   - 再看叶片\n4. 核对资料\n\n> 这不是物种鉴定。\n\n```js\nif (a < b) call();\n```\n\n| 指标 | 描述 |\n| :--- | ---: |\n| pH | 模拟 |');
  const all = flatten(nodes), names = all.map((node) => node.name);
  for (const name of ['h1', 'strong', 'em', 's', 'br', 'code', 'ol', 'ul', 'li', 'blockquote', 'pre', 'table', 'th', 'td']) assert.ok(names.includes(name), name);
  assert.equal(all.find((node) => node.name === 'ol').attrs.start, '3');
  assert.ok(all.some((node) => node.name === 'th' && node.attrs.style.includes('text-align:right')));
  assert.ok(textOf(nodes).includes('if (a < b) call();'));
  assert.ok(!textOf(nodes).includes('**候选**'));
});

test('untrusted model HTML, links, images and attributes never create scripts or network nodes', () => {
  const nodes = renderMarkdown('<script>alert(1)</script>\n\n<img src="https://tracker.invalid/pixel" onerror="bad()">\n\n![外部图片](https://tracker.invalid/image)\n\n[来源](https://example.org) [危险](javascript:alert(1))');
  const all = flatten(nodes);
  for (const node of all) {
    assert.ok(!['script', 'img', 'iframe', 'a'].includes(node.name));
    assert.ok(!Object.keys(node.attrs || {}).some((key) => /^(?:on|src|href)/i.test(key)));
  }
  assert.ok(textOf(nodes).includes('<script>alert(1)</script>'));
  assert.ok(textOf(nodes).includes('[图片：外部图片]'));
  assert.ok(textOf(nodes).includes('来源'));
});

test('incomplete and oversized model responses remain bounded and readable', () => {
  assert.deepEqual(renderMarkdown(null), []);
  assert.ok(textOf(renderMarkdown('**尚未闭合')).includes('尚未闭合'));
  const text = textOf(renderMarkdown('绿'.repeat(MAX_CHARACTERS + 100)));
  assert.ok(text.length < MAX_CHARACTERS + 100);
  assert.match(text, /内容较长/);
  assert.ok(textOf(renderMarkdown('> '.repeat(10000) + '内容')).length <= MAX_CHARACTERS + 100);
  for (const source of ['`x` '.repeat(2047), '```\nx\n```\n\n'.repeat(1800), '![图](https://example.org/img) '.repeat(5000)]) {
    assert.ok(flatten(renderMarkdown(source)).length <= MAX_NODES, 'all child text nodes count toward the node budget');
  }
});

test('Markdown component replaces old answer nodes when its content changes', () => {
  let definition; const previous = global.Component;
  try { global.Component = (value) => { definition = value; }; require('../components/markdown-view/index'); }
  finally { global.Component = previous; }
  const component = { data: { content: '**第一条**' }, setData(value) { Object.assign(this.data, value); } };
  definition.lifetimes.attached.call(component);
  assert.ok(flatten(component.data.nodes).some((node) => node.name === 'strong'));
  definition.properties.content.observer.call(component, '# 第二条');
  assert.equal(textOf(component.data.nodes), '第二条');
  definition.properties.content.observer.call(component, '');
  assert.deepEqual(component.data.nodes, []);
});
