const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { renderReport, publishReport } = require('./eval-comment.cjs');
const marker = '<!-- indexed:retrieval-eval -->';
function data() {
  return {
    report: { schema: 'indexed.eval.report.v1', metrics: { k: 5, cases: 23, answerable: 19, unanswerable: 4, errors: 1, hit_rate: 0.75, mrr: 0.5, unanswerable_distractor_leaks: 1 }, failures: [{ id: 'failed', error: 'search broke' }], environment: { indexed_git_rev: 'abc123' } },
    comparison: { schema: 'indexed.eval.compare.v1', verdict: 'improved', comparable: true, metrics: { baseline: { hit_rate: 0.5, mrr: 0.25, unanswerable_distractor_leaks: 2 }, candidate: { hit_rate: 0.75, mrr: 0.5, unanswerable_distractor_leaks: 1 }, delta: { hit_rate: 0.25, mrr: 0.25, unanswerable_distractor_leaks: -1 } }, improved: [{ id: 'case', rank_before: null, rank_after: 2 }], regressed: [], newly_failed: [], environment_changes: {}, config_changes: {}, incomparable_reasons: [] },
    runUrl: 'https://github.com/o/r/actions/runs/10', headSha: 'head123', outcomes: { harness: 'success', measure: 'success', compare: 'success' },
  };
}
test('renders measured metrics, null rank, errors, commits and run links', () => {
  const body = renderReport(data());
  for (const text of [marker, 'Informational', 'improved', '| Hit@5 | 0.5000 | 0.7500 | +0.2500 |', '| MRR | 0.2500 | 0.5000 | +0.2500 |', '| Distractor leaks | 2 | 1 | -1 |', 'unavailable → 2', 'Evaluation errors: 1', 'abc123', 'head123', '/10#artifacts']) assert.ok(body.includes(text), text);
});
test('missing or malformed inputs cannot claim improvement or unchanged', () => {
  for (const report of [undefined, null, {}, [], 'bad']) {
    const body = renderReport({ ...data(), report });
    assert.match(body, /Verdict: unavailable/);
    assert.doesNotMatch(body, /Verdict: improved/);
  }
  assert.match(renderReport({ ...data(), comparison: {} }), /Verdict: unavailable/);
  for (const mutate of [
    input => { input.report.metrics.hit_rate = '0.75'; },
    input => { input.report.failures = false; },
    input => { input.comparison.metrics.delta.mrr = '0.25'; },
    input => { input.comparison.comparable = false; },
  ]) {
    const input = data(); mutate(input);
    assert.match(renderReport(input), /Verdict: unavailable/);
  }
});
test('preserves null metrics and highlights failures and incomparable reasons', () => {
  const input = data();
  input.comparison.verdict = 'incomparable'; input.comparison.comparable = false;
  input.comparison.metrics.baseline.hit_rate = null;
  input.comparison.metrics.delta.hit_rate = null;
  input.comparison.incomparable_reasons = ['model differs'];
  input.comparison.config_changes = { embedding_model: { baseline: 'old', candidate: 'new' } };
  input.comparison.environment_changes = { python: { baseline: '3.11', candidate: '3.12' } };
  input.outcomes.harness = 'failure';
  const body = renderReport(input);
  for (const text of ['| Hit@5 | unavailable | 0.7500 | unavailable |', 'harness: failure', 'model differs', 'embedding', '3.11', '3.12']) assert.ok(body.includes(text), text);
});
test('keeps Markdown block separators and prominent harness and environment warnings', () => {
  const input = data();
  input.outcomes.harness = 'failure';
  input.comparison.environment_changes = { python: { baseline: '3.11', candidate: '3.12' } };
  const body = renderReport(input), tableIndex = body.indexOf('| Metric |');
  assert.match(body, /\n\n\| Metric \|/);
  assert.match(body.slice(0, tableIndex), /\*\*Warning: harness tests failed\.\*\*/);
  assert.match(body.slice(0, tableIndex), /\*\*Warning: evaluation environments differ; interpret ranking changes with care\.\*\*/);
});
test('escapes untrusted Markdown, HTML, newlines and mentions and bounds details', () => {
  const input = data();
  input.comparison.improved = Array.from({ length: 50 }, () => ({ id: '@all |\n<img> **x** [link](bad)', rank_before: 3, rank_after: 1 }));
  const body = renderReport(input);
  assert.doesNotMatch(body, /@all|<img>|\*\*x\*\*|\[link\]\(bad\)/);
  assert.match(body, /30 more/);
  assert.ok(body.length < 20000);
});
test('bounds long reasons, failures and configuration values below comment size', () => {
  const input = data(), long = '@all * text |\n'.repeat(10000);
  input.comparison.incomparable_reasons = Array(100).fill(long);
  input.comparison.config_changes = Object.fromEntries(Array.from({ length: 100 }, (_, i) => [`model${i}`, { baseline: long, candidate: long }]));
  input.report.failures = Array(100).fill({ id: long, error: long });
  const body = renderReport(input);
  assert.ok(body.length < 60000);
  assert.match(body, /truncated/);
});
test('omits whole details when escaped multi-section output reaches the comment budget', () => {
  const input = data(), hostile = '@'.repeat(10000);
  input.outcomes.harness = 'failure';
  input.comparison.improved = Array(100).fill({ id: hostile, rank_before: 2, rank_after: 1 });
  input.comparison.incomparable_reasons = Array(100).fill(hostile);
  for (const field of ['config_changes', 'environment_changes']) {
    input.comparison[field] = Object.fromEntries(Array.from({ length: 100 }, (_, i) => [hostile + i, { baseline: hostile, candidate: hostile }]));
  }
  input.report.failures = Array(100).fill({ id: hostile, error: hostile });
  input.errors = Array(100).fill(hostile);
  const body = renderReport(input);
  assert.ok(body.length <= 60000, `escaped body length ${body.length}`);
  for (const text of ['Verdict: improved', '| Metric | Baseline | Current | Delta |', '**Warning: harness tests failed.**', 'evaluation environments differ', '/10#artifacts', 'details omitted (truncated)']) assert.ok(body.includes(text), text);
  assert.equal((body.match(/<details>/g) || []).length, (body.match(/<\/details>/g) || []).length);
  assert.match(body, /\[Report artifacts\]\(https:\/\/github.com\/o\/r\/actions\/runs\/10#artifacts\)/);
});
async function fixture(t, overrides = {}) {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'eval-comment-'));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  const input = data();
  const reportPath = path.join(dir, 'report.json'), comparisonPath = path.join(dir, 'compare.json');
  await fs.writeFile(reportPath, JSON.stringify(input.report));
  await fs.writeFile(comparisonPath, JSON.stringify(input.comparison));
  const events = [], comments = [];
  const context = { eventName: 'pull_request', repo: { owner: 'o', repo: 'r' }, runId: 10, serverUrl: 'https://github.com', payload: { pull_request: { number: 2, head: { sha: 'head123', repo: { full_name: 'o/r' } }, base: { repo: { full_name: 'o/r' } } } } };
  const core = { summary: { addRaw(body) { events.push(['summary', body]); return this; }, async write() { events.push(['write']); } }, notice: message => events.push(['notice', message]), warning: message => events.push(['warning', message]) };
  const github = { rest: { pulls: { get: async () => { events.push(['head']); return { data: { head: { sha: 'head123' } } }; } }, issues: { listComments: Symbol('listComments'), createComment: async args => events.push(['create', args]), updateComment: async args => events.push(['update', args]) } }, paginate: async (method, args) => { assert.equal(method, github.rest.issues.listComments); assert.equal(args.per_page, 100); events.push(['paginate']); return comments; } };
  return { reportPath, comparisonPath, outcomes: input.outcomes, context, core, github, events, comments, ...overrides };
}
test('creates marked comment after writing summary and paginated lookup', async t => {
  const f = await fixture(t); await publishReport(f);
  assert.deepEqual(f.events.map(e => e[0]), ['summary', 'write', 'head', 'paginate', 'create']);
  assert.equal(f.events.at(-1)[1].issue_number, 2);
  assert.match(f.events.at(-1)[1].body, /indexed:retrieval-eval/);
});
test('updates only own marked bot comment and skips unchanged body', async t => {
  const f = await fixture(t);
  f.comments.push({ id: 1, body: marker, user: { login: 'someone', type: 'User' } }, { id: 2, body: marker, user: { login: 'other[bot]', type: 'Bot' } }, { id: 3, body: marker, user: { login: 'github-actions[bot]', type: 'User' } }, { id: 4, body: marker, user: { login: 'github-actions[bot]', type: 'Bot' } });
  await publishReport(f);
  const update = f.events.find(e => e[0] === 'update')[1]; assert.equal(update.comment_id, 4);
  f.comments[3].body = update.body; f.events.length = 0; await publishReport(f);
  assert.ok(!f.events.some(e => ['create', 'update'].includes(e[0])));
});
test('manual and fork runs keep summary and explain skipped comments', async t => {
  for (const kind of ['manual', 'fork']) {
    const f = await fixture(t);
    if (kind === 'manual') { f.context.eventName = 'workflow_dispatch'; delete f.context.payload.pull_request; }
    else f.context.payload.pull_request.head.repo.full_name = 'fork/r';
    await publishReport(f);
    assert.deepEqual(f.events.map(e => e[0]), ['summary', 'write', 'notice']);
  }
});
test('stale run cannot change a newer PR head comment', async t => {
  const f = await fixture(t); f.github.rest.pulls.get = async () => ({ data: { head: { sha: 'new' } } });
  await publishReport(f); assert.deepEqual(f.events.map(e => e[0]), ['summary', 'write', 'notice']);
});
test('missing and malformed JSON produce an unavailable summary', async t => {
  const f = await fixture(t); await fs.unlink(f.reportPath); await fs.writeFile(f.comparisonPath, '{bad');
  await publishReport(f);
  assert.match(f.events[0][1], /Verdict: unavailable/);
  assert.match(f.events[0][1], /unavailable.*JSON|JSON.*unavailable/i);
});
test('API errors warn after summary without failing the informational job', async t => {
  const f = await fixture(t); f.github.rest.issues.createComment = async () => { throw new Error('no permission'); };
  await publishReport(f); assert.equal(f.events.at(-1)[0], 'warning'); assert.equal(f.events[0][0], 'summary');
});
