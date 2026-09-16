const KEY = 'hyhq.session.v1';
const DEVICE_KEY = 'hyhq.device.v1';

function createSession(platform) {
  let current = null;
  try { current = platform.getStorageSync(KEY) || null; } catch (error) { /* Storage can be disabled. */ }
  function clear() {
    current = null;
    try { platform.removeStorageSync(KEY); } catch (error) { /* Clear in-memory state regardless. */ }
  }
  function get() {
    if (current && current.expires_at && Date.parse(current.expires_at) <= Date.now()) clear();
    return current;
  }
  return {
    get,
    token: () => (get() || {}).token || '',
    save(value) {
      current = value;
      try { platform.setStorageSync(KEY, value); } catch (error) { /* Session remains memory-only. */ }
    },
    updateUser(user) {
      if (get()) this.save(Object.assign({}, current, { user }));
    },
    clear,
    deviceId() {
      let id;
      try { id = platform.getStorageSync(DEVICE_KEY); } catch (error) { /* Generate memory fallback. */ }
      if (!id) {
        id = 'dev-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 14);
        try { platform.setStorageSync(DEVICE_KEY, id); } catch (error) { /* Never use this as authentication. */ }
      }
      return id;
    },
  };
}
module.exports = { createSession };
