const POSITIONS = { home: [0, 0], explore: [1, 0], ai: [2, 0], learn: [0, 1], profile: [1, 1], assistant: [2, 1] };
Component({
  properties: { name: { type: String, value: 'home' }, size: { type: Number, value: 60 } },
  data: { left: 0, top: 0 },
  observers: {
    name(name) {
      const [column, row] = POSITIONS[name] || POSITIONS.home;
      this.setData({ left: -100 * column, top: -100 * row });
    },
  },
});
