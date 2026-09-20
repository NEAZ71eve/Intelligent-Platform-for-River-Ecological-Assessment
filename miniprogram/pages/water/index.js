const { createSeriesPage } = require('../../lib/series');
const { entryUrl } = require('../../lib/llm');
const definition = createSeriesPage('water');
definition.openAI = function () {
  if (!this._interactive() || this.data.loading || this.data.error) return;
  const source = this.data.waterBodies[this.data.waterIndex];
    const url = source && entryUrl('explore', 'water', source.id);
  if (url) wx.navigateTo({ url });
};
Page(definition);
