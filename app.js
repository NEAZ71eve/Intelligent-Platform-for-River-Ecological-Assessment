const config = require('./config/index');
const { createClient } = require('./lib/client');
const { createSession } = require('./lib/session');
App({
  config,
  globalData: { region: null, health: null },
  onLaunch() {
    this.session = createSession(wx);
    this.api = createClient(wx, config, this.session);
  },
});
