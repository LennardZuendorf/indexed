const fs = require('node:fs/promises');

const MARKER = '<!-- indexed:retrieval-eval -->';
const metricLabels = { hit_rate: 'Hit@k', hit_rate_at_5: 'Hit@5', mrr: 'MRR', unanswerable_distractor_leaks: 'Distractor leaks' };
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const number = value => typeof value === 'number' && Number.isFinite(value);
const text = value => typeof value === 'string' && value.trim().length > 0;
const rank = value => value === null || value === undefined || Number.isInteger(value);
const side = value => object(value) && text(value.label) && text(value.fingerprint)
  && text(value.interpreter) && (value.revision === null || typeof value.revision === 'string');
const metric = value => object(value) && text(value.name) && number(value.base) && number(value.head)
  && number(value.delta) && typeof value.gating === 'boolean' && ['within', 'over'].includes(value.verdict);
const moved = value => object(value) && text(value.id) && rank(value.rank_before) && rank(value.rank_after);
// The gate's own artifact is the only source of a verdict: two same-job
// measurements and the comparator's ratio. A comment cannot invent one from a
// file whose shape it does not know.
const validAb = value => object(value) && value.schema === 'indexed.eval.ab.v1'
  && ['pass', 'fail', 'invalid'].includes(value.verdict)
  && number(value.tolerance) && side(value.base) && side(value.head)
  && Array.isArray(value.metrics) && value.metrics.every(metric)
  && Array.isArray(value.cases) && value.cases.every(moved)
  && Array.isArray(value.warnings) && Array.isArray(value.invalid_reasons)
  && (value.verdict !== 'invalid' || value.invalid_reasons.length > 0);

// Character references keep report text inert in Markdown tables and mentions.
function escape(value) {
  const raw = value == null ? 'unavailable' : typeof value === 'object' ? JSON.stringify(value) : String(value);
  const body = raw.length > 300 ? `${raw.slice(0, 300)}… [truncated]` : raw;
  return body.replace(/[\r\n]+/g, ' ').replace(/[&<>@\\`*_{}\[\]()#!|~]/g, char => `&#${char.charCodeAt(0)};`);
}
function format(value, signed = false, integer = false) {
  if (!number(value)) return 'unavailable';
  const digits = integer ? String(value) : value.toFixed(4);
  return `${signed && value > 0 ? '+' : ''}${digits}`;
}
function details(title, rows, limit = 20) {
  if (!rows.length) return '';
  const shown = rows.slice(0, limit).map(row => `- ${row}`).join('\n');
  return `\n<details>\n<summary>${title} (${rows.length})</summary>\n\n${shown}${rows.length > limit ? `\n- ${rows.length - limit} more omitted (truncated).` : ''}\n\n</details>\n`;
}

function renderReport({ ab, runUrl, headSha, outcomes = {}, errors = [] }) {
  const ok = validAb(ab);
  const verdict = ok ? ab.verdict : 'unavailable';
  const lines = [MARKER, '## Retrieval evaluation', '', `Verdict: ${verdict}`, ''];
  if (ok) {
    lines.push(
      `Merge base: ${escape(ab.base.label)} · Head: ${escape(ab.head.label)}`,
      `Fingerprints: ${escape(ab.base.fingerprint)} · ${escape(ab.head.fingerprint)}`,
      `Interpreter: ${escape(ab.base.interpreter)} · ${escape(ab.head.interpreter)}`,
      `Measured revisions: ${escape(ab.base.revision)} · ${escape(ab.head.revision)} · PR head: ${escape(headSha)}`,
      `[Workflow run](${runUrl}) · [Report artifacts](${runUrl}#artifacts)`,
    );
  } else {
    lines.push(
      `PR head: ${escape(headSha)}`,
      `[Workflow run](${runUrl}) · [Report artifacts](${runUrl}#artifacts)`,
    );
  }
  lines.push('', `Steps: ${['harness', 'measure', 'gate'].map(key => `${key}: ${escape(outcomes[key] || 'unavailable')}`).join(' · ')}`);
  if (!ok) lines.push('', 'Gate verdict unavailable: missing or malformed `eval-ab.json` — both sides must be measured in this job.');
  if (outcomes.harness === 'failure') lines.push('', '**Warning: harness tests failed.**');
  if (ok && ab.verdict === 'invalid') {
    lines.push('', '**Measurement invalid — this is a harness bug, not a verdict.**', '');
    lines.push(...ab.invalid_reasons.map(reason => `- ${escape(reason)}`));
  }
  if (ok) {
    lines.push('', `Gating metrics: hit-rate@k and MRR within ${format(ab.tolerance)} metric points of the merge base. Leaks are report-only.`);
    lines.push('', '| Metric | Merge base | Head | Delta | Verdict |', '| --- | ---: | ---: | ---: | --- |');
    for (const row of ab.metrics) {
      const label = metricLabels[row.name] || escape(row.name);
      const integer = row.name === 'unanswerable_distractor_leaks';
      const verdict = row.verdict === 'over' ? '**over tolerance**' : escape(row.gating ? 'within' : 'report only');
      lines.push(`| ${label} | ${format(row.base, false, integer)} | ${format(row.head, false, integer)} | ${format(row.delta, true, integer)} | ${verdict} |`);
    }
  }
  const sections = [];
  if (ok) {
    sections.push(details('Per-case rank movement', ab.cases.map(row => `${escape(row.id)}: rank ${escape(row.rank_before)} → ${escape(row.rank_after)}`)));
    sections.push(details('Comparator warnings', ab.warnings.map(escape), 10));
  }
  sections.push(details('Report loading errors', errors.map(escape), 10));
  const omitted = `\n\nAdditional details omitted (truncated). See [Report artifacts](${runUrl}#artifacts) for complete reports.`;
  let body = lines.join('\n'), truncated = false;
  for (const section of sections) {
    if (body.length + section.length + omitted.length + 1 > 60000) truncated = true;
    else body += `\n${section}`;
  }
  return body + (truncated ? omitted : '');
}

async function publishReport({ github, context, core, abPath = 'eval-ab.json', outcomes = {} }) {
  const errors = [];
  let ab = null;
  try { ab = JSON.parse(await fs.readFile(abPath, 'utf8')); }
  catch (error) { errors.push(`Gate result JSON unavailable: ${error.message}`); }
  const pr = context.payload?.pull_request;
  const runUrl = `${context.serverUrl || 'https://github.com'}/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}`;
  const body = renderReport({ ab, runUrl, headSha: pr?.head?.sha || context.sha, outcomes, errors });
  await core.summary.addRaw(body).write();
  if (context.eventName !== 'pull_request' || !pr || pr.head?.repo?.full_name !== `${context.repo.owner}/${context.repo.repo}`) {
    core.notice('Evaluation comment skipped: only same-repository pull requests support comments; summary and artifacts remain available.');
    return;
  }
  try {
    const args = { ...context.repo, pull_number: pr.number };
    const current = await github.rest.pulls.get(args);
    if (current.data.head.sha !== pr.head.sha) {
      core.notice('Evaluation comment skipped: PR head changed since this run started.');
      return;
    }
    const comments = await github.paginate(github.rest.issues.listComments, { ...context.repo, issue_number: pr.number, per_page: 100 });
    const existing = comments.find(comment => comment.user?.login === 'github-actions[bot]' && comment.user?.type === 'Bot' && typeof comment.body === 'string' && comment.body.includes(MARKER));
    if (existing?.body === body) return;
    if (existing) await github.rest.issues.updateComment({ ...context.repo, comment_id: existing.id, body });
    else await github.rest.issues.createComment({ ...context.repo, issue_number: pr.number, body });
  } catch (error) {
    core.warning(`Evaluation comment could not be published: ${error.message}`);
  }
}

module.exports = { renderReport, publishReport };
