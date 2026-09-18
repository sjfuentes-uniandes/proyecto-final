import http from 'k6/http';
import { Counter, Rate, Trend } from 'k6/metrics';

const config = JSON.parse(open('./config.json'));
const baseURL = (__ENV.BASE_URL || '').replace(/\/$/, '');
if (!/^https?:\/\//.test(baseURL)) throw new Error('BASE_URL must be an HTTP(S) endpoint');
const endpoints = {
  cotizacion: { status: 201, path: '/cotizaciones' },
  consulta: { status: 200, path: '/consultas/poliza-000001' },
};
const metrics = Object.fromEntries(Object.keys(endpoints).map((name) => [name, {
  completed: new Counter(`${name}_completed`), successful: new Counter(`${name}_successful`),
  errors: new Rate(`${name}_error_rate`), latency: new Trend(`${name}_latency_ms`, true),
  outcomes: new Counter(`${name}_outcomes`),
}]));

export const options = {
  scenarios: Object.fromEntries(Object.keys(endpoints).map((name) => [name, {
    executor: 'constant-arrival-rate', exec: name, rate: config.rate_rpm_per_endpoint,
    timeUnit: '1m', duration: `${config.duration_seconds}s`, preAllocatedVUs: config.preallocated_vus,
    maxVUs: config.max_vus, gracefulStop: '5s', tags: { endpoint: name },
  }])),
  thresholds: Object.fromEntries(Object.entries(endpoints).flatMap(([name]) => [
    [`${name}_latency_ms{scenario:${name}}`, [`p(95)<=${name === 'cotizacion' ? config.quote_p95_ms : config.consultation_p95_ms}`]],
    [`${name}_error_rate{scenario:${name}}`, [`rate<=${config.max_error_rate}`]],
    [`dropped_iterations{scenario:${name}}`, ['count==0']],
  ])),
  summaryTrendStats: ['avg', 'min', 'max', 'p(50)', 'p(90)', 'p(95)', 'p(99)'],
  maxRedirects: 0, tags: { experiment: 'EXP-LAT-01', run_id: __ENV.RUN_ID || 'manual' },
};

function request(name) {
  const endpoint = endpoints[name];
  const started = Date.now();
  const response = name === 'cotizacion'
    ? http.post(`${baseURL}${endpoint.path}`, JSON.stringify({ product_id: 'producto-sintetico' }), { headers: { 'Content-Type': 'application/json' }, timeout: `${config.timeout_seconds}s` })
    : http.get(`${baseURL}${endpoint.path}`, { timeout: `${config.timeout_seconds}s` });
  let valid = response.status === endpoint.status;
  if (valid && name === 'cotizacion') { try { valid = typeof response.json().id === 'string'; } catch (_) { valid = false; } }
  const outcome = valid ? 'success' : response.status === 0 ? 'transport_or_timeout' : `http_${response.status}`;
  metrics[name].completed.add(1); metrics[name].successful.add(valid ? 1 : 0); metrics[name].errors.add(!valid);
  metrics[name].latency.add(Date.now() - started); metrics[name].outcomes.add(1, { outcome });
}
export function cotizacion() { request('cotizacion'); }
export function consulta() { request('consulta'); }

export function handleSummary(data) {
  const endpointSummary = Object.fromEntries(Object.keys(endpoints).map((name) => {
    const at = (metric) => data.metrics[`${metric}{scenario:${name}}`]?.values || {};
    const completed = at(`${name}_completed`).count || 0;
    const expected = Math.floor(config.rate_rpm_per_endpoint * config.duration_seconds / 60);
    const errors = at(`${name}_error_rate`).rate;
    const latency = at(`${name}_latency_ms`);
    const dropped = at('dropped_iterations').count || 0;
    const p95Limit = name === 'cotizacion' ? config.quote_p95_ms : config.consultation_p95_ms;
    const valid_load = completed >= expected - 1 && dropped === 0 && Number.isFinite(errors);
    return [name, { expected, completed, successful: at(`${name}_successful`).count || 0, dropped, error_rate: errors ?? null,
      percentiles: latency, outcomes: Object.fromEntries(Object.keys(data.metrics).filter((key) => key.startsWith(`${name}_outcomes{scenario:${name},`)).map((key) => [key.match(/outcome:([^,}]+)/)?.[1], data.metrics[key].values.count])),
      valid_load, passed: valid_load && errors <= config.max_error_rate && latency['p(95)'] <= p95Limit }];
  }));
  const report = { report_version: 1, experiment: 'EXP-LAT-01', run_id: __ENV.RUN_ID || 'manual', base_url: baseURL,
    config, finished_at: new Date().toISOString(), endpoints: endpointSummary, k6: data };
  return { [__ENV.SUMMARY_PATH || 'summary.json']: JSON.stringify(report, null, 2), stdout: JSON.stringify(endpointSummary) + '\n' };
}
