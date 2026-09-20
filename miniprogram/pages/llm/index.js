const { app } = require('../../lib/page');
const { message, task } = require('../../lib/format');
const { assessmentTask } = require('../../lib/assessment');
const { CONSENT_VERSION, DISCLAIMER, pending, quotaView, turnView, sessionView, readPage, requestId, defaultQuestion } = require('../../lib/llm');
Page({
  data: { loading: true, busy: false, loggedIn: false, error: '', actionError: '', unavailable: false, status: null, quota: null, session: null, source: null, sourceKind: '', includeImage: false, consent: false, question: '', questionCount: 0, turns: [], next: '', loadingMore: false, moreError: '', polling: false, pollNotice: '', hasPending: false, disclaimer: DISCLAIMER },
  onLoad(options) {
    this._alive = true;
    if (options && options.sessionId) this._sessionId = options.sessionId;
    else if (options && ['recognition', 'assessment'].includes(options.kind) && options.jobId) { this._sourceKind = options.kind; this._sourceId = options.jobId; }
    else this._invalid = true;
  },
  async onShow() {
    this._visible = true;
    const shown = this._showVersion = (this._showVersion || 0) + 1;
    if (this._mutation && this._mutation.token === app().session.token()) {
      this.setData({ loading: true }); await this._mutation.promise;
      if (!this.active() || shown !== this._showVersion) return;
    }
    return this.load();
  },
  onHide() { this._visible = false; this.invalidate(); this.clearView(); },
  onUnload() { this._alive = false; this.invalidate(); },
  active() { return this._alive !== false && this._visible !== false; },
  invalidate() { this._generation = (this._generation || 0) + 1; this._showVersion = (this._showVersion || 0) + 1; this._confirming = false; this.stopTimer(); },
  stopTimer() { this._pollVersion = (this._pollVersion || 0) + 1; if (this._timer) clearTimeout(this._timer); this._timer = null; },
  clearView() { this.setData({ source: null, session: null, turns: [], next: '', question: '', questionCount: 0, consent: false, includeImage: false, quota: null, busy: false, loading: false, loadingMore: false, polling: false, hasPending: false, actionError: '', pollNotice: '' }); },
  hasMutation() { return !!(this._mutation && this._mutation.token === app().session.token()); },
  current(generation, token) {
    if (!this.active() || generation !== this._generation) return false;
    if (app().session.token() === token) return true;
    this.invalidate(); this.clearView(); this.setData({ loggedIn: Boolean(app().session.token()), error: '登录状态已变化，请刷新当前会话。' }); wx.stopPullDownRefresh(); return false;
  },
  canAct() { return this.active() && !this.data.busy && !this.hasMutation() && !this._confirming && this.current(this._generation, this._token) && !!app().session.token(); },
  login() { if (this.active()) wx.switchTab({ url: '/pages/profile/index' }); },
  history() { if (this.active()) wx.navigateTo({ url: '/pages/llm-history/index' }); },
  privacy() { if (this.active()) wx.navigateTo({ url: '/pages/legal/index?kind=privacy' }); },
  onPullDownRefresh() { if (this.hasMutation()) { wx.stopPullDownRefresh(); return; } return this.load(); },
  async load() {
    if (!this.active()) return;
    if (this.hasMutation()) { wx.stopPullDownRefresh(); return; }
    this.stopTimer();
    this._pollPaused = false;
    const generation = this._generation = (this._generation || 0) + 1, token = app().session.token();
    if (this._token !== token) { this.clearView(); this._retry = null; }
    this._token = token;
    this.setData({ loading: true, error: '', actionError: '', unavailable: false, loggedIn: Boolean(token), polling: false, pollNotice: '' });
    try {
      if (this._invalid) throw new Error('请从已有花卉识别或河道观察结果进入 AI 解读。');
      await this.loadStatus(generation, token);
      if (!this.current(generation, token) || !token) return;
      if (this._sessionId) {
        const result = await app().api.request('llm/sessions/' + encodeURIComponent(this._sessionId) + '/');
        if (!this.current(generation, token)) return;
        const session = sessionView(result.data);
        this.setData({ session, sourceKind: session.kind, includeImage: session.include_image === true });
        if (!this.data.question) this.setQuestion(defaultQuestion(session.kind));
        await this.loadTurns(false, generation, token);
      } else {
        const endpoint = this._sourceKind === 'recognition' ? 'recognition-jobs/' : 'assessment-jobs/';
        const result = await app().api.request(endpoint + encodeURIComponent(this._sourceId) + '/');
        if (!this.current(generation, token)) return;
        const source = this._sourceKind === 'recognition' ? task(result.data) : assessmentTask(result.data);
        if (source.status !== 'succeeded') throw new Error('请在原任务完成并有可查看结果后使用 AI 解读。');
        this.setData({ source, sourceKind: this._sourceKind });
        if (!this.data.question) this.setQuestion(defaultQuestion(this._sourceKind));
      }
    } catch (error) { if (this.current(generation, token)) this.handleError(error); }
    finally { if (this.current(generation, token)) { this.setData({ loading: false }); wx.stopPullDownRefresh(); } }
  },
  async loadStatus(generation = this._generation, token = this._token) {
    const version = this._statusVersion = (this._statusVersion || 0) + 1;
    const response = await app().api.request('llm/status/');
    if (!this.current(generation, token) || version !== this._statusVersion) return;
    const status = response.data;
    if (!status || typeof status.enabled !== 'boolean') throw new Error('AI 服务状态返回异常，请刷新重试。');
    this.setData({ status, quota: quotaView(status.quota) });
  },
  handleError(error) {
    if (error.status === 404) { this.stopTimer(); this.setData({ session: null, source: null, turns: [], next: '', unavailable: true, hasPending: false, polling: false }); }
    this.setData({ error: message(error) });
  },
  setQuestion(question) { this.setData({ question, questionCount: Array.from(question.trim()).length }); },
  inputQuestion(event) { if (!this.canAct()) return; this.setQuestion(typeof event.detail.value === 'string' ? event.detail.value : ''); this.setData({ actionError: '' }); },
  consentChange(event) { if (this.canAct()) this.setData({ consent: event.detail.value.includes('agree') }); },
  imageChange(event) { if (this.canAct() && !this.data.session) this.setData({ includeImage: event.detail.value === true, consent: false }); },
  async mutate(work) {
    const mutation = { token: app().session.token() }; mutation.promise = new Promise((resolve) => { mutation.resolve = resolve; }); this._mutation = mutation;
    this.setData({ busy: true, actionError: '' });
    try { await work(mutation.token); }
    finally { if (this._mutation === mutation) this._mutation = null; mutation.resolve(); if (this.active() && this._token === mutation.token && app().session.token() === mutation.token) this.setData({ busy: false }); }
  },
  createSession() {
    if (!this.canAct() || !this.data.consent || !this.data.source || !this.data.status || !this.data.status.enabled || this.data.status.consent_version !== CONSENT_VERSION || this._sessionId) return;
    const generation = this._generation, token = this._token, includeImage = this.data.includeImage;
    this._confirming = true; let handled = false;
    wx.showModal({ title: '确认使用 DeepSeek 解读', content: '你同意把本次识别结果、相关公开科普资料、之后主动发送的问题和本会话的对话上下文交给 DeepSeek 处理。' + (includeImage ? '你另外选择附送本次原图经处理后的图片；过期原图不会改用缩略图。' : '本会话不附送图片。') + '建立会话不会自动提问，首次发送也占每日额度。', confirmText: '同意并继续', success: async (result) => {
      if (handled) return; handled = true;
      if (!this.current(generation, token)) return;
      this._confirming = false; if (!result.confirm) return;
      await this.mutate(async () => {
        try {
          const data = { consent_version: CONSENT_VERSION, include_image: includeImage };
          data[this._sourceKind === 'recognition' ? 'recognition_job_id' : 'assessment_job_id'] = this._sourceId;
          const response = await app().api.request('llm/sessions/', { method: 'POST', data });
          const session = sessionView(response.data);
          // Remember a successfully created session while away; onShow re-reads it.
          if (app().session.token() === token && this._alive !== false) this._sessionId = session.id;
          if (!this.current(generation, token)) return;
          this.setData({ session, source: null, turns: [], next: '', consent: false, actionError: '' });
        } catch (error) { if (this.current(generation, token)) this.setData({ actionError: message(error) + (error.code === 'IMAGE_UNAVAILABLE' ? ' 可关闭附图，重新同意后建立仅文字结果的会话。' : ' 若结果未确认，可先去会话记录查看。') }); }
      });
    }, fail: () => { if (this.current(generation, token)) this._confirming = false; } });
  },
  async send() {
    if (!this.canAct() || !this.data.session || !this.data.status || !this.data.status.enabled || this.data.hasPending) return;
    if (!this.data.quota || this.data.quota.remaining <= 0) { this.setData({ actionError: '当前没有可用额度，请刷新额度或等待北京时间重置。' }); return; }
    const question = this.data.question.trim();
    if (!question || Array.from(question).length > 500) { this.setData({ actionError: '请填写 1 至 500 字的问题。' }); return; }
    const generation = this._generation, token = this._token, sessionId = this._sessionId;
    const retry = this._retry && this._retry.question === question && this._retry.sessionId === sessionId ? this._retry : { question, sessionId, requestId: requestId() };
    this._retry = retry;
    await this.mutate(async () => {
      try {
        const response = await app().api.request('llm/sessions/' + encodeURIComponent(sessionId) + '/turns/', { method: 'POST', data: { question, request_id: retry.requestId } });
        if (!this.current(generation, token)) return;
        const turn = turnView(response.data);
        if (turn.session_id !== sessionId) throw new Error('返回轮次不属于当前会话，请刷新核对。');
        this._retry = null; this.setQuestion('');
        this.setData({ turns: [turn].concat(this.data.turns.filter((row) => row.id !== turn.id)), hasPending: pending(turn), actionError: '' });
        if (pending(turn)) this.startPolling(turn.id);
      } catch (error) { if (this.current(generation, token)) { if (error.status === 404) this.handleError(error); this.setData({ actionError: message(error) + ' 未确认的提交请先刷新核对；原问题重试会复用同一请求编号。' }); } }
      finally { if (this.current(generation, token)) { try { await this.loadStatus(generation, token); } catch (error) { if (this.current(generation, token)) this.setData({ actionError: this.data.actionError || '额度暂不可确认，请刷新后再发送。', quota: null }); } } }
    });
  },
  async loadTurns(more = false, generation = this._generation, token = this._token) {
    if (!this.current(generation, token) || !this._sessionId || (more && (!this.data.next || this.data.loadingMore || this.hasMutation()))) return;
    const version = this._turnsVersion = (this._turnsVersion || 0) + 1;
    const endpoint = 'llm/sessions/' + encodeURIComponent(this._sessionId) + '/turns/', path = more ? this.data.next : endpoint;
    const seen = more ? new Set(this._seen || []) : new Set();
    this.setData({ loadingMore: more, moreError: '' });
    try {
      const response = await app().api.request(path, more ? undefined : { data: { page_size: 20 } });
      if (!this.current(generation, token) || version !== this._turnsVersion) return;
      const page = readPage(response, path, endpoint, seen), rows = page.items.map(turnView);
      if (rows.some((turn) => turn.session_id !== this._sessionId)) throw new Error('轮次记录不属于当前会话。');
      const turns = new Map((more ? this.data.turns : []).map((row) => [row.id, row])); rows.forEach((row) => turns.set(row.id, row));
      seen.add(page.key); this._seen = seen;
      const values = Array.from(turns.values());
      this.setData({ turns: values, next: page.next, hasPending: values.some(pending) });
      const active = values.find(pending); if (active && !this.data.polling && !this._pollPaused) this.startPolling(active.id);
    } catch (error) { if (this.current(generation, token) && version === this._turnsVersion) { if (error.status === 404) this.handleError(error); this.setData({ moreError: message(error) }); } }
    finally { if (this.current(generation, token) && version === this._turnsVersion) this.setData({ loadingMore: false }); }
  },
  more() { return this.loadTurns(true); },
  startPolling(id) {
    this.stopTimer(); if (!this.active()) return;
    this._pollPaused = false;
    this._pollCount = 0; this.setData({ polling: true, pollNotice: '' }); return this.poll(id, this._pollVersion, this._generation, this._token);
  },
  async poll(id, version, generation, token) {
    if (!this.current(generation, token) || version !== this._pollVersion) return;
    try {
      const response = await app().api.request('llm/turns/' + encodeURIComponent(id) + '/');
      if (!this.current(generation, token) || version !== this._pollVersion) return;
      const turn = turnView(response.data);
      if (turn.session_id !== this._sessionId || turn.id !== id) throw new Error('AI 轮次身份不一致，请刷新核对。');
      const turns = this.data.turns.map((row) => row.id === id ? turn : row);
      this.setData({ turns, hasPending: turns.some(pending) });
      if (pending(turn)) {
        this._pollCount += 1;
        if (this._pollCount < 24) this._timer = setTimeout(() => this.poll(id, version, generation, token), 2500);
        else this.pausePolling('已暂停自动刷新，可稍后恢复；已提交的任务仍由服务端处理。');
      } else {
        this.stopTimer(); this.setData({ polling: false });
        const another = turns.find(pending); if (another) this.startPolling(another.id);
        try { await this.loadStatus(generation, token); } catch (error) { if (this.current(generation, token)) this.setData({ quota: null, pollNotice: '解读状态已更新，额度暂不可用，请刷新确认。' }); }
      }
    } catch (error) { if (this.current(generation, token) && version === this._pollVersion) { if (error.status === 404) this.handleError(error); this.pausePolling(message(error) + ' 可手动刷新或恢复查询。'); } }
  },
  pausePolling(notice) { this.stopTimer(); this._pollPaused = true; if (this.active()) this.setData({ polling: false, pollNotice: typeof notice === 'string' ? notice : '已停止自动刷新；这不会取消已提交的 DeepSeek 请求。' }); },
  resumePolling() { if (this.canAct()) { const turn = this.data.turns.find(pending); if (turn) this.startPolling(turn.id); else return this.load(); } },
  original() {
    if (!this.canAct()) return;
    const session = this.data.session, kind = session ? session.kind : this._sourceKind;
    const id = session ? (kind === 'recognition' ? session.recognition_job_id : session.assessment_job_id) : this._sourceId;
    if (!id) return;
    if (kind === 'recognition') { app().globalData.recognitionJobId = id; wx.switchTab({ url: '/pages/recognize/index' }); }
    else wx.navigateTo({ url: '/pages/assessment/index?jobId=' + encodeURIComponent(id) });
  },
});
