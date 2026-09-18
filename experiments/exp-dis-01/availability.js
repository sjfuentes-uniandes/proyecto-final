import http from 'k6/http';
import { Counter, Rate, Trend } from 'k6/metrics';
const config = JSON.parse(open('./config.json'));
const baseURL = (__ENV.BASE_URL || '').replace(/\/$/, '');
if (!/^https?:\/\//.test(baseURL)) throw new Error('BASE_URL must be an HTTP(S) endpoint');
const completed = new Counter('quotes_completed'), successful = new Counter('quotes_successful');
const errors = new Rate('quotes_error_rate'), latency = new Trend('quotes_latency_ms', true), outcomes = new Counter('quotes_outcomes');
const scenario = (name, startTime, duration) => ({ executor: 'constant-arrival-rate', exec: 'quote', startTime, duration: `${duration}s`, rate: config.rate_rpm, timeUnit: '1m', preAllocatedVUs: config.preallocated_vus, maxVUs: config.max_vus, gracefulStop: '5s', tags: { phase: name } });
export const options = { scenarios: { baseline: scenario('baseline', '0s', config.baseline_seconds), perturbation: scenario('perturbation', `${config.baseline_seconds}s`, config.perturbation_seconds) },
  thresholds: { 'quotes_latency_ms{scenario:perturbation}': [`p(95)<=${config.p95_ms}`], 'quotes_error_rate{scenario:perturbation}': [`rate<=${config.max_error_rate}`], 'dropped_iterations{scenario:perturbation}': ['count==0'] },
  summaryTrendStats: ['avg', 'min', 'max', 'p(50)', 'p(90)', 'p(95)', 'p(99)'], maxRedirects: 0, tags: { experiment: 'EXP-DIS-01', run_id: __ENV.RUN_ID || 'manual' } };
export function quote() {
  const started = Date.now(); const response = http.post(`${baseURL}/cotizaciones`, JSON.stringify({ product_id: 'producto-sintetico' }), { headers: { 'Content-Type':'application/json' }, timeout: `${config.timeout_seconds}s` });
  let valid = response.status === 201; if (valid) { try { valid = typeof response.json().id === 'string'; } catch (_) { valid = false; } }
  const outcome = valid ? 'success' : response.status === 0 ? 'transport_or_timeout' : `http_${response.status}`;
  completed.add(1); successful.add(valid ? 1 : 0); errors.add(!valid); latency.add(Date.now() - started); outcomes.add(1, { outcome });
}
export function handleSummary(data) {
  const phase = (name, seconds) => { const get = (metric) => data.metrics[`${metric}{scenario:${name}}`]?.values || {}; const count = get('quotes_completed').count || 0, success = get('quotes_successful').count || 0, error = get('quotes_error_rate').rate, dropped = get('dropped_iterations').count || 0, expected = Math.floor(config.rate_rpm * seconds / 60), values = get('quotes_latency_ms'); const valid_load = count >= expected - 1 && dropped === 0 && Number.isFinite(error); return { expected, completed: count, successful: success, success_rate: count ? success / count : null, error_rate: error ?? null, dropped, percentiles: values, valid_load, passed: valid_load && success / count >= config.min_success_rate && values['p(95)'] <= config.p95_ms }; };
  const report = { report_version: 1, experiment: 'EXP-DIS-01', run_id: __ENV.RUN_ID || 'manual', base_url: baseURL, config, finished_at: new Date().toISOString(), baseline: phase('baseline', config.baseline_seconds), perturbation: phase('perturbation', config.perturbation_seconds), k6:data };
  return { [__ENV.SUMMARY_PATH || 'summary.json']: JSON.stringify(report, null, 2), stdout: JSON.stringify(report.perturbation) + '\n' };
}
