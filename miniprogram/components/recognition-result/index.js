Component({
  properties: { result: Object },
  methods: {
    content(event) { this.triggerEvent('content', { id: event.currentTarget.dataset.id }); },
    retake() { this.triggerEvent('retake'); },
  },
});
