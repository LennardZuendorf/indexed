const fs = require('node:fs/promises');

const MARKER = '<!-- indexed:retrieval-eval -->';
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const number = value => typeof value === 'number' && Number.isFinite(value);
const metricNames = ['hit_rate', 'mrr', 'unanswerable_distractor_leaks'];
const metrics = value => object(value) && metricNames.every(key => value[key] === null || number(value[key]));
const validReport = value => object(value) && value.schema === 'indexed.eval.report.v1'
  && metrics(value.metrics) && Array.isArray(value.failures) && number(value.metrics.errors);
const validComparison = value => object(value) && value.schema === 'indexed.eval.compare.v1'
  && ['improved', 'regressed', 'unchanged', 'incomparable'].includes(value.verdict)
  && typeof value.comparable === 'boolean' && object(value.metrics)
  && ['baseline', 'candidate', 'delta'].every(key => metrics(value.metrics[key]))
  && ['improved', 'regressed', 'newly_failed', 'incomparable_reasons'].every(key => Array.isArray(value[key]))
  && object(value.config_changes) && object(value.environment_changes)
  && (value.comparable === (value.verdict !== 'incomparable'));

// Character references keep report text inert in Markdown tables and mentions.
function escape(value) {
  const raw = value == null ? 'unavailable' : typeof value === 'object' ? JSON.stringify(value) : String(value);
  const text = raw.length > 300 ? `${raw.slice(0, 300)}… [truncated]` : raw;
  return text.replace(/[\r\n]+/g, ' ').replace(/[&<>@\\`*_{}\[\]()#!|~]/g, char => `&#${char.charCodeAt(0)};`);
}
function format(value, signed = false, integer = false) {
  if (!number(value)) return 'unavailable';
  return `${signed && value > 0 ? '+' : ''}${integer ? value : value.toFixed(4)}`;
}
function details(title, rows, limit = 20) {
  if (!rows.length) return '';
  const shown = rows.slice(0, limit).map(row => `- ${row}`).join('\n');
  return `\n<details>\n<summary>${title} (${rows.length})</summary>\n\n${shown}${rows.length > limit ? `\n- ${rows.length - limit} more omitted (truncated).` : ''}\n\n</details>\n`;
}

function renderReport({ report, comparison, runUrl, headSha, outcomes = {}, errors = [] }) {
  const reportOk = validReport(report), comparisonOk = validComparison(comparison);
  const verdict = reportOk && comparisonOk ? comparison.verdict : 'unavailable';
  const lines = [MARKER, '## Retrieval evaluation', '', '**Informational — results do not block merging.**', '', `Verdict: ${verdict}`, '',
    `PR head: ${escape(headSha)} · Measured source commit: ${escape(reportOk ? report.environment?.indexed_git_rev : null)}`,
    `[Workflow run](${runUrl}) · [Report artifacts](${runUrl}#artifacts)`, '',
    `Steps: ${['harness', 'measure', 'compare'].map(key => `${key}: ${escape(outcomes[key] || 'unavailable')}`).join(' · ')}`];
  if (!reportOk) lines.push('', 'Evaluation report unavailable (missing or malformed JSON).');
  if (!comparisonOk) lines.push('', 'Comparison unavailable (missing or malformed JSON).');
  if (outcomes.harness === 'failure') lines.push('', '**Warning: harness tests failed.**');
  if (comparisonOk && Object.keys(comparison.environment_changes).length) {
    lines.push('', '**Warning: evaluation environments differ; interpret ranking changes with care.**');
  }
  if (reportOk) lines.push('', `Cases: ${format(report.metrics.cases, false, true)} · Answerable: ${format(report.metrics.answerable, false, true)} · Unanswerable: ${format(report.metrics.unanswerable, false, true)} · Evaluation errors: ${format(report.metrics.errors, false, true)}`);
  lines.push('', '| Metric | Baseline | Current | Delta |', '| --- | ---: | ---: | ---: |');
  for (const [key, label, integer] of [['hit_rate', `Hit@${number(report?.metrics?.k) ? report.metrics.k : '?'}`, false], ['mrr', 'MRR', false], ['unanswerable_distractor_leaks', 'Distractor leaks', true]]) {
    const before = comparisonOk ? comparison.metrics.baseline[key] : null;
    const after = reportOk ? report.metrics[key] : null;
    const delta = reportOk && comparisonOk ? comparison.metrics.delta[key] : null;
    lines.push(`| ${label} | ${format(before, false, integer)} | ${format(after, false, integer)} | ${format(delta, true, integer)} |`);
  }
  const sections = [];
  if (comparisonOk) {
    const changed = ['improved', 'regressed'].flatMap(kind => comparison[kind].map(row => `${kind}: ${escape(row?.id)} — ${format(row?.rank_before, false, true)} → ${format(row?.rank_after, false, true)}`));
    changed.push(...comparison.newly_failed.map(id => `newly failed: ${escape(id)}`));
    sections.push(details('Changed cases', changed));
    sections.push(details('Incomparable reasons', comparison.incomparable_reasons.map(escape), 10));
    for (const [field, title] of [['config_changes', 'Configuration changes'], ['environment_changes', 'Environment changes']]) {
      sections.push(details(title, Object.entries(comparison[field]).map(([key, value]) => `${escape(key)}: ${escape(value?.baseline)} → ${escape(value?.candidate)}`), 10));
    }
  }
  if (reportOk) sections.push(details('Evaluation failures', report.failures.map(row => `${escape(row?.id)}: ${escape(row?.error)}`), 10));
  sections.push(details('Report loading errors', errors.map(escape), 10));
  const omitted = `\n\nAdditional details omitted (truncated). See [Report artifacts](${runUrl}#artifacts) for complete reports.`;
  let body = lines.join('\n'), truncated = false;
  for (const section of sections) {
    if (body.length + section.length + omitted.length + 1 > 60000) truncated = true;
    else body += `\n${section}`;
  }
  return body + (truncated ? omitted : '');
}

async function publishReport({ github, context, core, reportPath = 'eval-report.json', comparisonPath = 'eval-compare.json', outcomes = {} }) {
  const errors = [];
  async function load(file, label) {
    try { return JSON.parse(await fs.readFile(file, 'utf8')); }
    catch (error) { errors.push(`${label} JSON unavailable: ${error.message}`); return null; }
  }
  const report = await load(reportPath, 'Evaluation report');
  const comparison = await load(comparisonPath, 'Comparison');
  const pr = context.payload.pull_request;
  const runUrl = `${context.serverUrl || 'https://github.com'}/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}`;
  const body = renderReport({ report, comparison, runUrl, headSha: pr?.head?.sha || context.sha, outcomes, errors });
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
