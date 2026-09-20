const { createSeriesPage } = require('../../lib/series');
const { entryUrl } = require('../../lib/llm');
const definition = createSeriesPage('data-center');
definition.openAI = function () {
  if (!this._interactive() || this.data.loading || this.data.error) return;
  const url = this.data.region && entryUrl('explore', 'region', this.data.region.id);
  if (url) wx.navigateTo({ url });
};
Page(definition);
