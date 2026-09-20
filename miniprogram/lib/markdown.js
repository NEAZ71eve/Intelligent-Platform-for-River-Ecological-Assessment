const MarkdownIt = require('../vendor/markdown-it/index');

// Parse Markdown locally. Model output never becomes executable HTML, an image
// request or navigation: only the fixed rich-text node names/styles below leave
// this adapter. In particular, remote Markdown images are rendered as alt text.
const parser = new MarkdownIt({ html: false, breaks: true, linkify: false, typographer: false, maxNesting: 20 });
const MAX_CHARACTERS = 24000;
const MAX_NODES = 4096;
const STYLES = {
  p: 'margin:0 0 12px;line-height:1.85;',
  h1: 'font-size:21px;font-weight:700;line-height:1.5;margin:18px 0 12px;color:#244f3d;',
  h2: 'font-size:19px;font-weight:700;line-height:1.5;margin:16px 0 10px;color:#244f3d;',
  h3: 'font-size:17px;font-weight:700;line-height:1.6;margin:14px 0 8px;color:#244f3d;',
  h4: 'font-size:16px;font-weight:700;margin:12px 0 8px;',
  h5: 'font-size:15px;font-weight:700;margin:12px 0 8px;',
  h6: 'font-size:14px;font-weight:700;margin:12px 0 8px;',
  strong: 'font-weight:700;color:#244f3d;', em: 'font-style:italic;', s: 'text-decoration:line-through;',
  code: 'font-family:monospace;font-size:13px;background:#edf1e8;border-radius:4px;padding:2px 4px;white-space:pre-wrap;word-break:break-all;',
  pre: 'font-family:monospace;font-size:13px;line-height:1.7;background:#edf1e8;padding:12px;border-radius:8px;margin:12px 0;white-space:pre-wrap;word-break:break-all;',
  blockquote: 'border-left:3px solid #9aaf8c;background:#f4f6ef;padding:10px 12px;margin:12px 0;color:#637260;',
  ul: 'padding-left:24px;margin:8px 0 14px;list-style-type:disc;',
  ol: 'padding-left:26px;margin:8px 0 14px;list-style-type:decimal;',
  li: 'margin:5px 0;line-height:1.85;',
  table: 'border-collapse:collapse;width:100%;font-size:13px;table-layout:fixed;margin:12px 0;',
  th: 'padding:8px 6px;border:1px solid #dce5d6;background:#edf2e8;font-weight:700;word-break:break-all;text-align:left;',
  td: 'padding:8px 6px;border:1px solid #dce5d6;word-break:break-all;',
  hr: 'border:0;border-top:1px solid #dce5d6;margin:16px 0;',
};
const TAGS = new Set(Object.keys(STYLES).concat(['thead', 'tbody', 'tr', 'br', 'span']));
const LINK_STYLE = 'color:#326d57;text-decoration:underline;word-break:break-all;';
function plain(text) { return { type: 'text', text }; }
function element(name, children = [], style = '') {
  return { name, attrs: style || STYLES[name] ? { style: style || STYLES[name] } : {}, children };
}

function renderMarkdown(value) {
  const text = typeof value === 'string' ? value : '';
  if (!text) return [];
  const truncated = text.length > MAX_CHARACTERS;
  let source = text.slice(0, MAX_CHARACTERS);
  // Avoid leaving half of a UTF-16 surrogate pair after the input cap.
  if (/[\uD800-\uDBFF]$/.test(source)) source = source.slice(0, -1);
  const root = [], stack = [root];
  let count = 0;
  const nodeCount = (node) => 1 + (node.children || []).reduce((sum, child) => sum + nodeCount(child), 0);
  const append = (node) => {
    count += nodeCount(node);
    if (count > MAX_NODES) throw new Error('Markdown node limit');
    stack[stack.length - 1].push(node);
    return node;
  };
  function visit(tokens) {
    for (const token of tokens) {
      if (token.type === 'inline') { visit(token.children || []); continue; }
      if (token.type === 'text' || token.type === 'html_inline' || token.type === 'html_block') {
        if (token.content) append(plain(token.content));
        continue;
      }
      if (token.type === 'softbreak' || token.type === 'hardbreak') { append(element('br')); continue; }
      if (token.type === 'code_inline') { append(element('code', [plain(token.content)])); continue; }
      if (token.type === 'fence' || token.type === 'code_block') { append(element('pre', [plain(token.content.replace(/\n$/, ''))])); continue; }
      if (token.type === 'image') {
        append(plain(token.content ? '[图片：' + token.content + ']' : '[图片]'));
        continue;
      }
      if (token.type === 'hr') { append(element('hr')); continue; }
      if (token.nesting === -1) { if (stack.length > 1) stack.pop(); continue; }
      if (token.nesting === 1) {
        const name = token.type === 'link_open' ? 'span' : TAGS.has(token.tag) ? token.tag : 'span';
        let style = token.type === 'link_open' ? LINK_STYLE : STYLES[name] || '';
        if (name === 'th' || name === 'td') {
          const alignment = (token.attrGet('style') || '').match(/^text-align:(left|center|right)$/);
          if (alignment) style += 'text-align:' + alignment[1] + ';';
        }
        // Tight list paragraphs must not introduce extra blank lines.
        if (token.hidden && name === 'p') style = 'margin:0;line-height:1.85;';
        const node = append(element(name, [], style));
        if (name === 'ol') {
          const start = Number(token.attrGet('start'));
          if (Number.isInteger(start) && start > 0 && start <= 999999999) node.attrs.start = String(start);
        }
        stack.push(node.children);
        continue;
      }
      if (token.content) append(plain(token.content));
    }
  }
  try {
    visit(parser.parse(source, {}));
    if (truncated) { stack.length = 1; append(element('p', [plain('内容较长，已显示前半部分。')])); }
    return root;
  } catch (_) {
    // A bounded plain-text fallback remains readable; raw HTML stays a text node.
    return [element('p', [plain(source + (truncated ? '\n内容较长，已显示前半部分。' : ''))], 'white-space:pre-wrap;word-break:break-all;line-height:1.85;')];
  }
}
module.exports = { renderMarkdown, MAX_CHARACTERS, MAX_NODES };
