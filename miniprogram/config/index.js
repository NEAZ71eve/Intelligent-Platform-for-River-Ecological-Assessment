/** No secrets belong in this file or any mini-program source. */
const defaults = {
  baseURL: 'http://127.0.0.1:8000/api/v1',
  development: true,
  timeout: 15000,
  uploadTimeout: 30000,
  maxUploadBytes: 5 * 1024 * 1024,
};
// For local overrides, edit this development configuration. Keep secrets on
// the backend. No require() points to an optional/missing module, so a fresh
// checkout can compile directly in WeChat Developer Tools.
module.exports = defaults;
