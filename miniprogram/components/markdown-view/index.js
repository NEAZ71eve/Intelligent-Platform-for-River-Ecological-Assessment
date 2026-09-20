const { renderMarkdown } = require('../../lib/markdown');
Component({
  properties: { content: { type: String, value: '', observer(value) { this.setData({ nodes: renderMarkdown(value) }); } } },
  data: { nodes: [] },
  lifetimes: { attached() { this.setData({ nodes: renderMarkdown(this.data.content) }); } },
});
