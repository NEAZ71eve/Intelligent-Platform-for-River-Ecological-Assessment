Component({
  properties: { visible: { type: Boolean, value: true }, tabPage: { type: Boolean, value: false }, label: { type: String, value: '问问 AI' } },
  methods: { open() { if (this.data.visible) this.triggerEvent('open'); } },
});
