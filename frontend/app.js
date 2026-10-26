const $ = (id) => document.getElementById(id);
const make = (tag, cls, text) => { const node = document.createElement(tag); if (cls) node.className = cls; if (text !== undefined) node.textContent = text; return node; };
const state = { replay: null, actor: 0, decisions: [], visible: [], decision: null, report: null, selected: null, serial: 0, history: [], analysisBusy: false, llmBusy: false };
const wind = { E: '东', S: '南', W: '西', N: '北' };
const names = { dahai: '打', chi: '吃', pon: '碰', reach: '立直', ankan: '暗杠', kakan: '加杠', daiminkan: '大明杠', hora: '和牌', none: '跳过', ryukyoku: '流局' };
const label = (moves) => moves.map(a => (names[a.type] || a.type) + (a.pai ? ' ' + a.pai : '')).join(' → ');
const number = (v, digits = 3) => typeof v === 'number' ? v.toLocaleString('zh-CN', { maximumFractionDigits: digits }) : '—';
function notice(text, error = false) { $('notice').textContent = text; $('notice').classList.toggle('error', error); }
async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...options.headers } });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '请求失败，请检查输入格式');
  return data;
}
const post = (path, body) => api(path, { method: 'POST', ...(body ? { body: JSON.stringify(body) } : {}) });
function path(suffix = '') { return `/api/replays/${state.replay}/decisions/${state.decision.id}${suffix}?actor=${state.actor}`; }
function tile(pai, small = false) {
  const honor = { E: '東', S: '南', W: '西', N: '北', P: '白', F: '發', C: '中' };
  const t = make('span', 'tile' + (small ? ' small' : ''));
  t.setAttribute('aria-label', pai);
  t.title = pai;
  if (honor[pai]) { t.classList.add('honor'); t.textContent = honor[pai]; if (pai === 'F') t.classList.add('green'); if (pai === 'C') t.classList.add('red'); }
  else if (/^[1-9][mps]r?$/.test(pai)) { t.classList.add(pai[1]); if (pai.endsWith('r')) t.classList.add('red-five'); t.append(make('span', 'rank', pai[0]), make('span', 'suit', { m: '萬', p: '筒', s: '索' }[pai[1]])); }
  else t.textContent = '?';
  return t;
}
function updateButtons() {
  $('analyze').disabled = !state.decision || state.analysisBusy;
  $('explain').disabled = !state.report || state.llmBusy;
  $('ask').disabled = !state.report || state.llmBusy;
  const idx = state.visible.findIndex(d => d.id === state.decision?.id);
  $('previous').disabled = idx <= 0;
  $('next').disabled = idx < 0 || idx >= state.visible.length - 1;
}
async function health() {
  const data = await api('/api/health');
  $('engine-status').textContent = Object.entries(data.engines).map(([k, v]) => `${k === 'mortal' ? 'Mortal' : 'Akochan'} ${v.configured ? '已配置' : '未配置'}`).join('  /  ');
  $('llm-url').value = data.llm.base_url; $('llm-model').value = data.llm.model;
  $('llm-thinking').checked = data.llm.thinking_compatibility;
  $('engine-config-note').textContent = Object.entries(data.engines).map(([k, v]) => `${k}: ${v.configured ? v.version : '未配置'}`).join('；');
}
async function library(selected = state.replay) {
  const items = await api('/api/replays');
  $('library').replaceChildren(make('option', '', '选择已导入的牌谱'));
  $('library').firstChild.value = '';
  for (const item of items) { const option = make('option', '', item.title); option.value = item.id; option.title = item.source; $('library').append(option); }
  if (selected) $('library').value = selected;
  $('replay-count').textContent = `${items.length} 场`;
}
async function loadReplay(id) {
  const serial = ++state.serial;
  state.replay = id; state.report = null; state.history = [];
  const data = await api(`/api/replays/${id}/decisions?actor=${state.actor}`);
  if (serial !== state.serial) return;
  state.decisions = data.decisions;
  $('actor').replaceChildren(...[0, 1, 2, 3].map(i => { const o = make('option', '', `座位 ${i} · ${data.names[i] || '玩家'}`); o.value = i; return o; }));
  $('actor').value = state.actor;
  $('download').href = `/api/replays/${id}/mjai`; $('download').classList.remove('hidden');
  filterTimeline();
  notice(`${data.source} · 已读取 ${data.decisions.length} 个决策时点。请选择局面后分析。`);
  if (state.visible.length) await selectDecision(state.visible[0].id);
}
function filterTimeline() {
  state.visible = state.decisions.filter(d => $('reactions').checked || d.kind === 'self');
  renderTimeline(); updateButtons();
}
function renderTimeline() {
  const root = $('timeline'); root.replaceChildren(); let previous = '';
  for (const d of state.visible) {
    const group = `${wind[d.bakaze]} ${d.kyoku} 局 · ${d.honba} 本场`;
    if (group !== previous) { root.append(make('div', 'round-group', group)); previous = group; }
    const button = make('button', 'decision' + (state.decision?.id === d.id ? ' active' : ''));
    button.setAttribute('aria-current', state.decision?.id === d.id ? 'step' : 'false');
    button.append(make('span', '', `第 ${d.turn} 巡${d.kind === 'reaction' ? ' · 应对' : ''}`), make('span', 'decision-action', label(d.actual)));
    button.addEventListener('click', () => selectDecision(d.id).catch(e => notice(e.message, true)));
    root.append(button);
  }
  if (!state.visible.length) root.append(make('p', 'empty-small', '当前视角没有可复盘的完整手牌。'));
}
async function selectDecision(id) {
  const serial = ++state.serial;
  state.report = null; state.selected = null; state.history = []; state.decision = { id }; resetAnalysis();
  renderTimeline(); updateButtons();
  const data = await api(path());
  if (serial !== state.serial) return;
  state.decision = data;
  const s = data.state;
  $('round-label').textContent = `${wind[s.bakaze]} ${s.kyoku} 局 · ${s.honba} 本场 · 视角 ${s.names[s.actor]}`;
  $('turn-label').textContent = `第 ${s.turn} 巡${data.kind === 'reaction' ? '，回应对手' : '，轮到你选择'}`;
  $('actual').textContent = `实际：${label(data.actual)}`;
  renderBoard(s); updateButtons();
}
function renderBoard(s) {
  const root = $('board-content'); root.replaceChildren();
  const positions = ['south', 'east', 'north', 'west'];
  for (let offset = 0; offset < 4; offset++) {
    const actor = (s.actor + offset) % 4, position = positions[offset];
    const seat = make('div', `seat ${position}`);
    seat.append(make('span', 'seat-wind', ['東', '南', '西', '北'][(actor - s.oya + 4) % 4]));
    const info = make('div'); info.append(make('div', '', s.names[actor]), make('strong', '', number(s.scores[actor], 0)));
    if (s.reached[actor]) info.append(make('span', 'riichi', ' 立直'));
    seat.append(info); root.append(seat);
    const river = make('div', `river ${position}`);
    river.setAttribute('aria-label', `${s.names[actor]}的牌河`);
    s.rivers[actor].forEach(e => { const t = tile(e.pai, true); t.classList.toggle('called', e.called); t.classList.toggle('tsumogiri', e.tsumogiri); river.append(t); });
    root.append(river);
  }
  const center = make('div', 'board-center');
  center.append(make('strong', '', `${wind[s.bakaze]} ${s.kyoku}`), make('div', '', `余 ${s.tiles_left} 张`), make('small', '', `${s.honba} 本场 / ${s.kyotaku} 供托`)); root.append(center);
  const dora = make('div', 'board-dora'); dora.append(make('span', '', '宝牌指示牌')); const row = make('div', 'dora-row');
  s.dora_markers.forEach(p => row.append(tile(p, true))); dora.append(row); root.append(dora);
  const melds = make('div', 'meld-legend');
  s.melds.forEach((list, a) => list.forEach(m => melds.append(make('div', '', `${s.names[a]} ${label([m])} ${(m.consumed || []).join(' ')}${m.added ? ' +' + m.added : ''}`)))); root.append(melds);
  $('hand').replaceChildren();
  const hand = [...s.hand];
  if (s.trigger.type === 'tsumo' && s.trigger.actor === s.actor) { const idx = hand.indexOf(s.trigger.pai); if (idx >= 0) hand.push(...hand.splice(idx, 1)); }
  hand.forEach((p, i) => {
    const t = tile(p), b = make('button', t.className); b.append(...t.childNodes); b.title = `选择 ${p} 的候选解释`; b.setAttribute('aria-label', `查看打 ${p} 的候选解释`);
    if (s.trigger.type === 'tsumo' && s.trigger.actor === s.actor && i === hand.length - 1) b.classList.add('drawn');
    b.addEventListener('click', async () => {
      const c = state.report?.candidates.find(c => c.moves.at(-1).type === 'dahai' && c.moves.at(-1).pai === p);
      if (c) { selectCandidate(c.id); return; }
      if (!state.report) { notice('先分析当前局面，再点击手牌检验任意合法弃牌。'); return; }
      const serial = state.serial;
      try { const data = await post(path('/counterfactual'), { tile: p }); if (serial !== state.serial) return;
        $('hand-experiment-title').textContent = `额外弃牌实验：打 ${p}（独立证据，未获得模型评分）`;
        $('hand-experiment-result').textContent = JSON.stringify(data, null, 2);
        $('hand-experiment').classList.remove('hidden'); $('hand-experiment').open = true;
      } catch (err) { notice(err.message, true); }
    }); $('hand').append(b);
  });
}
function resetAnalysis() {
  $('hand-experiment').classList.add('hidden');
  $('candidates').replaceChildren(); const tr = make('tr'); const td = make('td', 'table-empty', '点击“分析当前局面”，运行引擎与独立证据计算。'); td.colSpan = 5; tr.append(td); $('candidates').append(tr);
  $('explanation-empty').classList.remove('hidden'); $('explanation-content').classList.add('hidden'); $('disagreement').classList.add('hidden'); $('model-messages').replaceChildren(); $('raw-evidence').textContent = '尚无分析'; $('chat-log').replaceChildren(make('p', 'muted', '追问只基于当前决策，不读取未来牌局。')); $('disagreement-explanation').textContent = '等待分析'; $('explanation-source').textContent = '证据优先'; $('llm-notice').textContent = '解释只引用已计算的结构化证据。'; $('explain').textContent = '生成中文 AI 解释';
}
async function analyzeCurrent() {
  const serial = state.serial; state.analysisBusy = true; updateButtons(); $('analyze').textContent = '正在分析…'; notice('正在运行真实引擎与独立证据计算。Akochan 首次计算可能较慢。');
  try { const report = await post(path('/analyze')); if (serial !== state.serial) return; state.report = report; renderReport(); notice('局面分析完成。原始评分、候选来源和证据均可展开核查。'); }
  catch (e) { notice(e.message, true); }
  finally { state.analysisBusy = false; $('analyze').textContent = '分析当前局面'; updateButtons(); }
}
function renderReport() {
  const r = state.report;
  $('model-messages').replaceChildren(...r.engines.map(e => make('div', '', `${e.name === 'mortal' ? 'Mortal' : 'Akochan'} · ${e.message}${e.status === 'ok' ? ` · ${e.version}` : ''}${e.temperature !== null ? ` · 温度 ${e.temperature}` : ''}`)));
  const badge = $('disagreement'); badge.className = `disagreement ${r.disagreement.level}`; badge.textContent = `${r.disagreement.label} · ${r.disagreement.reason}`;
  $('candidates').replaceChildren();
  for (const c of r.candidates) {
    const tr = make('tr'); tr.dataset.candidate = c.id;
    const action = make('td'), button = make('button', 'candidate-button', c.label); button.addEventListener('click', () => selectCandidate(c.id)); action.append(button);
    if (c.actual) button.append(make('span', 'actual-badge', '实际'));
    tr.append(action);
    for (const engine of ['mortal', 'akochan']) {
      const score = c.models[engine], cell = make('td');
      if (!score) cell.textContent = '—';
      else if (engine === 'mortal') { cell.append(make('span', '', `${number(score.probability * 100, 2)}%`), make('span', 'score-secondary', `#${score.rank} · Q ${number(score.score, 4)}`)); const meter = make('meter'); meter.min = 0; meter.max = 1; meter.value = score.probability; meter.setAttribute('aria-label', 'Mortal 偏好'); cell.append(meter); }
      else cell.append(make('span', '', `#${score.rank}`), make('span', 'score-secondary', score.score === null ? '规则动作，未评分' : number(score.score, 5)));
      tr.append(cell);
    }
    tr.append(make('td', '', c.evidence ? c.evidence.shanten === 0 ? '听牌' : `${c.evidence.shanten} 向听` : '未知'), make('td', '', c.evidence ? `${c.evidence.ukeire} 枚` : '未知'));
    tr.addEventListener('click', () => selectCandidate(c.id)); $('candidates').append(tr);
  }
  $('raw-evidence').textContent = JSON.stringify(r, null, 2);
  renderDisagreement(); selectCandidate(r.candidates[0]?.id); updateButtons();
}
function renderClaim(claim) {
  const p = make('p'); p.append(make('span', `claim-kind ${claim.kind}`, { fact: '事实', inference: '推测', unknown: '未知' }[claim.kind]), document.createTextNode(claim.text), make('span', 'evidence-ref', claim.evidence_ids.join(' · '))); return p;
}
function renderDisagreement() { const root = $('disagreement-explanation'); root.replaceChildren(...state.report.explanation.disagreement.map(renderClaim)); }
function selectCandidate(id) {
  const c = state.report?.candidates.find(c => c.id === id); if (!c) return; state.selected = c;
  document.querySelectorAll('tr[data-candidate]').forEach(tr => tr.classList.toggle('selected', tr.dataset.candidate === id));
  $('explanation-empty').classList.add('hidden'); $('explanation-content').classList.remove('hidden');
  $('candidate-title').textContent = c.label; $('candidate-reasons').textContent = c.reasons.join(' / ');
  if (c.moves.length > 1 && c.evidence) $('candidate-reasons').textContent += ' · 独立证据只计算末次弃牌，未计算复合动作的完整收益';
  const ex = state.report.explanation.candidates.find(e => e.candidate_id === id); $('explanation-claims').replaceChildren();
  for (const [key, title] of [['advantages', '优势与支持依据'], ['disadvantages', '劣势与证据边界'], ['conditions', '适用条件'], ['comparison', '横向比较']]) {
    const group = make('section', 'claim-group'); group.append(make('h4', '', title));
    (ex?.[key] || []).forEach(claim => group.append(renderClaim(claim)));
    if (!ex?.[key]?.length) group.append(make('p', 'muted', '暂无足够证据。')); $('explanation-claims').append(group);
  }
  $('effective-tiles').replaceChildren();
  for (const e of c.evidence?.effective_tiles || []) { const pair = make('span', 'effective-pair'); pair.append(tile(e.tile, true), make('span', '', `×${e.unseen}`)); $('effective-tiles').append(pair); }
  if (!c.evidence?.effective_tiles?.length) $('effective-tiles').append(make('span', 'muted', c.evidence ? '无剩余未见进张' : '该动作暂无独立进张证据'));
  $('counterfactual').disabled = !c.evidence; $('counterfactual-result').classList.add('hidden');
  $('explanation-source').textContent = state.report.explanation.source === 'llm' ? state.report.explanation.model : '计算证据';
  $('llm-notice').textContent = state.report.explanation.notice;
}
$('link-form').addEventListener('submit', async e => { e.preventDefault(); const button = e.currentTarget.querySelector('button'); button.disabled = true; notice('正在下载与转换雀魂牌谱…'); try { const result = await post('/api/replays/link', { url: $('replay-url').value }); await library(result.id); await loadReplay(result.id); } catch (err) { notice(err.message, true); } finally { button.disabled = false; } });
$('replay-file').addEventListener('change', async e => { const file = e.target.files[0]; if (!file) return; if (file.size > 12 * 1024 * 1024) { notice('文件不能超过 12 MiB', true); return; } const form = new FormData(); form.append('file', file); notice('正在转换牌谱…'); try { const result = await api('/api/replays/import', { method: 'POST', body: form }); await library(result.id); await loadReplay(result.id); } catch (err) { notice(err.message, true); } finally { e.target.value = ''; } });
$('example').addEventListener('click', async () => { $('example').disabled = true; try { const result = await post('/api/replays/example'); await library(result.id); await loadReplay(result.id); } catch (err) { notice(err.message, true); } finally { $('example').disabled = false; } });
$('library').addEventListener('change', e => { if (e.target.value) loadReplay(e.target.value).catch(err => notice(err.message, true)); });
$('actor').addEventListener('change', e => { state.actor = Number(e.target.value); if (state.replay) loadReplay(state.replay).catch(err => notice(err.message, true)); });
$('reactions').addEventListener('change', () => { filterTimeline(); if (state.visible.length && !state.visible.some(d => d.id === state.decision?.id)) selectDecision(state.visible[0].id); });
for (const [id, delta] of [['previous', -1], ['next', 1]]) $(id).addEventListener('click', () => { const i = state.visible.findIndex(d => d.id === state.decision?.id); const d = state.visible[i + delta]; if (d) selectDecision(d.id).catch(err => notice(err.message, true)); });
$('analyze').addEventListener('click', analyzeCurrent);
$('explain').addEventListener('click', async () => { const serial = state.serial; state.llmBusy = true; updateButtons(); $('explain').textContent = '逐组生成解释…'; notice('正在为全部候选生成中文解释并验证证据引用…'); try { const ex = await post(path('/explain')); if (serial !== state.serial) return; state.report.explanation = ex; selectCandidate(state.selected.id); renderDisagreement(); notice(ex.notice, ex.source !== 'llm'); } catch (err) { notice(err.message, true); } finally { state.llmBusy = false; $('explain').textContent = '重新生成中文 AI 解释'; updateButtons(); } });
$('counterfactual').addEventListener('click', async () => { const serial = state.serial, candidate = state.selected; try { const data = await post(path('/counterfactual'), { tile: candidate.moves.at(-1).pai }); if (serial !== state.serial || state.selected.id !== candidate.id) return; $('counterfactual-result').textContent = JSON.stringify(data, null, 2); $('counterfactual-result').classList.remove('hidden'); } catch (err) { notice(err.message, true); } });
$('chat-form').addEventListener('submit', async e => { e.preventDefault(); const question = $('question').value.trim(); if (!question || !state.report) return; const serial = state.serial; state.llmBusy = true; updateButtons(); $('chat-log').append(make('p', 'chat-question', question)); $('question').value = ''; $('ask').textContent = '正在核查证据…'; try { const result = await post(path('/chat'), { question, history: state.history }); if (serial !== state.serial) return; const answer = make('div', 'chat-answer'); result.claims.forEach(c => answer.append(renderClaim(c))); $('chat-log').append(answer); state.history.push({ role: 'user', content: question }, { role: 'assistant', content: result.claims.map(c => c.text).join('\n') }); $('chat-log').scrollTop = $('chat-log').scrollHeight; } catch (err) { notice(err.message, true); } finally { state.llmBusy = false; $('ask').textContent = '基于当前证据追问'; updateButtons(); } });
$('settings-open').addEventListener('click', () => $('settings').showModal()); $('settings-close').addEventListener('click', () => $('settings').close());
$('llm-url').addEventListener('input', () => { try { if (new URL($('llm-url').value).hostname.endsWith('.aliyuncs.com')) $('llm-thinking').checked = false; } catch {} });
async function saveLLM() { const body = { base_url: $('llm-url').value, model: $('llm-model').value, thinking_compatibility: $('llm-thinking').checked }; if ($('llm-key').value) body.api_key = $('llm-key').value; const result = await post('/api/settings/llm', body); $('llm-key').value = ''; return result; }
$('settings-form').addEventListener('submit', async e => { e.preventDefault(); try { const result = await saveLLM(); $('settings-status').textContent = result.scope; await health(); } catch (err) { $('settings-status').textContent = err.message; } });
  $('llm-test').addEventListener('click', async () => { $('llm-test').disabled = true; $('settings-status').textContent = '正在测试当前模型的实际生成…'; try { await saveLLM(); const result = await post('/api/settings/llm/test'); $('settings-status').textContent = result.ok ? `连接成功 · ${result.model} 实际生成通过 · 已持久保存` : result.message; await health(); } catch (err) { $('settings-status').textContent = err.message; } finally { $('llm-test').disabled = false; } });
Promise.all([health(), library()]).catch(e => notice(e.message, true));
