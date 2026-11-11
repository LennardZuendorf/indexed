const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { renderReport, publishReport } = require('./eval-comment.cjs');
const marker = '<!-- indexed:retrieval-eval -->';
const fingerprint = 'AMD EPYC 7763 64-Core Processor|x86_64|4|Linux';
function data() {
  return {
    ab: {
      schema: 'indexed.eval.ab.v1', kind: 'indexed-eval', verdict: 'fail', tolerance: 0.02, unit: 'points',
      base: { label: 'origin/main @ abc1234', revision: 'abc1234', fingerprint, interpreter: '3.13.18' },
      head: { label: 'head @ def5678', revision: 'def5678', fingerprint, interpreter: '3.13.18' },
      metrics: [
        { name: 'hit_rate', base: 0.75, head: 0.75, delta: 0, gating: true, verdict: 'within' },
        { name: 'mrr', base: 0.5, head: 0.4, delta: -0.1, gating: true, verdict: 'over' },
        { name: 'unanswerable_distractor_leaks', base: 2, head: 4, delta: 2, gating: false, verdict: 'within' },
      ],
      cases: [{ id: 'case', rank_before: null, rank_after: 2 }],
      warnings: ['a benchmark was measured on one side only'],
      invalid_reasons: [],
    },
    runUrl: 'https://github.com/o/r/actions/runs/10', headSha: 'head123',
    outcomes: { harness: 'success', measure: 'success', gate: 'failure' },
  };
}
test('renders the same-job verdict, both revisions, fingerprints and per-case movement', () => {
  const body = renderReport(data());
  for (const text of [marker, 'Verdict: fail', 'origin/main &#64; abc1234', 'head &#64; def5678', 'AMD EPYC 7763 64-Core Processor', 'abc1234', 'def5678',
    '| Hit@k | 0.7500 | 0.7500 | 0.0000 | within |', '| MRR | 0.5000 | 0.4000 | -0.1000 | **over tolerance** |',
    '| Distractor leaks | 2 | 4 | +2 | report only |', 'unavailable → 2', 'gate: failure', 'within 0.0200 metric points',
    'head123', '/10#artifacts']) assert.ok(body.includes(text), text);
});
test('missing or malformed gate results cannot claim a verdict', () => {
  for (const ab of [undefined, null, {}, [], 'bad']) {
    const body = renderReport({ ...data(), ab });
    assert.match(body, /Verdict: unavailable/);
    assert.doesNotMatch(body, /Verdict: (pass|fail|invalid)/);
  }
  for (const mutate of [
    input => { input.ab.metrics[0].base = '0.75'; },
    input => { input.ab.metrics[0].delta = '0'; },
    input => { input.ab.metrics[0].verdict = 'better'; },
    input => { input.ab.base.fingerprint = 42; },
    input => { input.ab.cases = false; },
  ]) {
    const input = data(); mutate(input);
    assert.match(renderReport(input), /Verdict: unavailable/);
  }
});
test('an invalid measurement names the harness bug and its reasons', () => {
  const input = data();
  input.ab.verdict = 'invalid'; input.ab.metrics = []; input.ab.invalid_reasons = ['the pinned case set differs'];
  const body = renderReport(input);
  for (const text of ['Verdict: invalid', '**Measurement invalid — this is a harness bug, not a verdict.**', 'the pinned case set differs']) assert.ok(body.includes(text), text);
  input.ab.invalid_reasons = [];
  assert.match(renderReport(input), /Verdict: unavailable/);
});
test('keeps the harness warning above the table', () => {
  const input = data(); input.outcomes.harness = 'failure';
  const body = renderReport(input), tableIndex = body.indexOf('| Metric |');
  assert.match(body.slice(0, tableIndex), /\*\*Warning: harness tests failed\.\*\*/);
});
test('escapes untrusted Markdown, HTML, newlines and mentions and bounds details', () => {
  const input = data();
  input.ab.cases = Array.from({ length: 50 }, () => ({ id: '@all |\n<img> **x** [link](bad)', rank_before: 3, rank_after: 1 }));
  const body = renderReport(input);
  assert.doesNotMatch(body, /@all|<img>|\*\*x\*\*|\[link\]\(bad\)/);
  assert.match(body, /30 more/);
  assert.ok(body.length < 20000);
});
test('bounds long warnings and errors below the comment size', () => {
  const input = data(), long = '@all * text |\n'.repeat(10000);
  input.ab.warnings = Array(100).fill(long);
  input.errors = Array(100).fill(long);
  const body = renderReport(input);
  assert.ok(body.length < 60000);
  assert.match(body, /truncated/);
});
test('omits whole details when escaped multi-section output reaches the budget', () => {
  const input = data(), hostile = '@'.repeat(10000);
  input.outcomes.harness = 'failure';
  input.ab.cases = Array(100).fill({ id: hostile, rank_before: 2, rank_after: 1 });
  input.ab.warnings = Array(100).fill(hostile);
  input.errors = Array(100).fill(hostile);
  const body = renderReport(input);
  assert.ok(body.length <= 60000, `escaped body length ${body.length}`);
  for (const text of ['Verdict: fail', '| Metric | Merge base | Head | Delta | Verdict |', '**Warning: harness tests failed.**', '/10#artifacts']) assert.ok(body.includes(text), text);
  assert.equal((body.match(/<details>/g) || []).length, (body.match(/<\/details>/g) || []).length);
  assert.match(body, /\[Report artifacts\]\(https:\/\/github.com\/o\/r\/actions\/runs\/10#artifacts\)/);
});
async function fixture(t) {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'eval-comment-'));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  const input = data();
  const abPath = path.join(dir, 'eval-ab.json');
  await fs.writeFile(abPath, JSON.stringify(input.ab));
  const events = [], comments = [];
  const context = { eventName: 'pull_request', repo: { owner: 'o', repo: 'r' }, runId: 10, serverUrl: 'https://github.com', payload: { pull_request: { number: 2, head: { sha: 'head123', repo: { full_name: 'o/r' } }, base: { repo: { full_name: 'o/r' } } } } };
  const core = { summary: { addRaw(body) { events.push(['summary', body]); return this; }, async write() { events.push(['write']); } }, notice: message => events.push(['notice', message]), warning: message => events.push(['warning', message]) };
  const github = { rest: { pulls: { get: async () => { events.push(['head']); return { data: { head: { sha: 'head123' } } }; } }, issues: { listComments: Symbol('listComments'), createComment: async args => events.push(['create', args]), updateComment: async args => events.push(['update', args]) } }, paginate: async (method, args) => { assert.equal(method, github.rest.issues.listComments); assert.equal(args.per_page, 100); events.push(['paginate']); return comments; } };
  return { abPath, outcomes: input.outcomes, context, core, github, events, comments };
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
test('missing and malformed gate JSON produce an unavailable summary', async t => {
  const f = await fixture(t); await fs.writeFile(f.abPath, '{bad');
  await publishReport(f);
  assert.match(f.events[0][1], /Verdict: unavailable/);
  assert.match(f.events[0][1], /unavailable|JSON/i);
});
test('API errors warn after summary without failing the job', async t => {
  const f = await fixture(t); f.github.rest.issues.createComment = async () => { throw new Error('no permission'); };
  await publishReport(f); assert.equal(f.events.at(-1)[0], 'warning'); assert.equal(f.events[0][0], 'summary');
});

function minimalInvalid() {
  return {
    schema: 'indexed.eval.ab.v1', kind: null, verdict: 'invalid', tolerance: 0.04, unit: null,
    base: { label: 'captured base' }, head: { label: 'merge result' },
    metrics: [], cases: [], warnings: [], invalid_reasons: ['the retrieval configuration differs (embedding_model)'],
  };
}
test('renders the exact minimal invalid artifact emitted by the comparator', () => {
  for (const tolerance of [0.04, null, -1]) {
    const ab = minimalInvalid(); ab.tolerance = tolerance;
    const body = renderReport({ ...data(), ab });
    assert.match(body, /Verdict: invalid/);
    assert.match(body, /the retrieval configuration differs/);
    assert.doesNotMatch(body, /missing or malformed|Verdict: unavailable|Gating metrics:|\| Metric \|/);
    assert.match(body, /Fingerprints: unavailable · unavailable/);
  }
});
test('minimal invalid metadata never weakens pass or fail artifact validation', () => {
  for (const verdict of ['pass', 'fail']) {
    const ab = minimalInvalid(); ab.verdict = verdict;
    assert.match(renderReport({ ...data(), ab }), /Verdict: unavailable/);
  }
  for (const mutate of [
    ab => { ab.invalid_reasons = []; },
    ab => { ab.invalid_reasons = [null]; },
    ab => { ab.invalid_reasons = [{}]; },
    ab => { ab.base = null; },
    ab => { ab.base.label = 42; },
    ab => { ab.base.fingerprint = {}; },
    ab => { ab.tolerance = 'invalid'; },
    ab => { ab.tolerance = Infinity; },
    ab => { ab.warnings = {}; },
    ab => { ab.metrics = [null]; },
    ab => { ab.cases = false; },
  ]) {
    const ab = minimalInvalid(); mutate(ab);
    assert.match(renderReport({ ...data(), ab }), /Verdict: unavailable/);
  }
});
test('invalid reasons stay escaped and bounded with an artifact link', () => {
  const ab = minimalInvalid();
  ab.invalid_reasons = Array(10000).fill('@all | <img> **bad** [link](url)\n'.repeat(1000));
  const body = renderReport({ ...data(), ab });
  assert.match(body, /Verdict: invalid/);
  assert.doesNotMatch(body, /@all|<img>|\*\*bad\*\*|\[link\]\(url\)/);
  assert.ok(body.length <= 60000, `body length ${body.length}`);
  assert.match(body, /omitted|truncated/);
  assert.match(body, /Report artifacts/);
});

test('publishes minimal invalid reasons in both summary and comment', async t => {
  const f = await fixture(t);
  await fs.writeFile(f.abPath, JSON.stringify(minimalInvalid()));
  await publishReport(f);
  for (const body of [f.events[0][1], f.events.find(event => event[0] === 'create')[1].body]) {
    assert.match(body, /Verdict: invalid/);
    assert.match(body, /the retrieval configuration differs/);
    assert.doesNotMatch(body, /missing or malformed|Verdict: unavailable/);
  }
});
