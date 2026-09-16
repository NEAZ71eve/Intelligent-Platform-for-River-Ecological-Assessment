Component({
  properties: { loading: Boolean, error: String, empty: Boolean, emptyText: { type: String, value: '暂无数据，稍后再来看看' } },
  methods: { retry() { this.triggerEvent('retry'); } },
});
