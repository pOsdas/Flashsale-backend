function metricValue(metric, key) {
  if (!metric || !metric.values) return null;
  const value = metric.values[key];
  return value === undefined ? null : value;
}

export function buildSummary(data, defaultName) {
  const output = __ENV.SUMMARY_FILE || `/results/${defaultName}.json`;
  const summary = {
    test: defaultName,
    generated_at: new Date().toISOString(),
    state: data.state,
    metrics: data.metrics,
    root_group: data.root_group,
  };
  const lines = [
    '',
    `Load Lab summary: ${defaultName}`,
    `iterations: ${metricValue(data.metrics.iterations, 'count') ?? 'n/a'}`,
    `http requests: ${metricValue(data.metrics.http_reqs, 'count') ?? 'n/a'}`,
    `http failed rate: ${metricValue(data.metrics.http_req_failed, 'rate') ?? 'n/a'}`,
    `http p95 ms: ${metricValue(data.metrics.http_req_duration, 'p(95)') ?? 'n/a'}`,
    `http p99 ms: ${metricValue(data.metrics.http_req_duration, 'p(99)') ?? 'n/a'}`,
    `checks rate: ${metricValue(data.metrics.checks, 'rate') ?? 'n/a'}`,
    `dropped iterations: ${metricValue(data.metrics.dropped_iterations, 'count') ?? 0}`,
    `JSON report: ${output}`,
    '',
  ].join('\n');
  return {
    stdout: lines,
    [output]: JSON.stringify(summary, null, 2),
  };
}
