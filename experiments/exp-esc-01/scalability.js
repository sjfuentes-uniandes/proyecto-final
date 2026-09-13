import http from 'k6/http';
import { Counter, Rate, Trend } from 'k6/metrics';

const mode = __ENV.MODE || 'fixed';
const config = JSON.parse(open(mode === 'autoscaling' ? './autoscaling-config.json' : './config.json'));
const safetyErrors = new Rate('safety_errors');
const baseURL = (__ENV.BASE_URL || '').replace(/\/$/, '');
if (!/^https?:\/\//.test(baseURL)) throw new Error('BASE_URL must be an HTTP(S) endpoint');
const replicas = Number(__ENV.REPLICAS);
if (![1, 2, 3].includes(replicas)) throw new Error('REPLICAS must be 1, 2 or 3');
const outcomes = new Counter('quotes_outcomes');
const backendLatency = new Trend('quotes_http_duration_ms', true);
const connectionMetrics = Object.fromEntries(['blocked', 'connecting', 'tls_handshaking', 'waiting', 'receiving'].map(name => [name, new Trend(`client_${name}_ms`, true)]));
const completed = new Counter('quotes_completed');
const successful = new Counter('quotes_successful');
const errors = new Rate('quotes_error_rate');
const latency = new Trend('quotes_latency_ms', true);
const scenarios = {};
const thresholds = {};
const schedule = [];
let offset = 0;

function addPhase(name, target, seconds, startRate) {
  const ramp = startRate !== undefined;
  scenarios[name] = {
    executor: ramp ? 'ramping-arrival-rate' : 'constant-arrival-rate',
    exec: 'quote', startTime: `${offset}s`, timeUnit: '1m',
    preAllocatedVUs: config.preallocated_vus, maxVUs: config.max_vus,
    gracefulStop: `${config.grace_seconds}s`,
    tags: { phase: name, target_rpm: String(target), replicas: String(replicas) },
    ...(ramp ? { startRate, stages: [{ duration: `${seconds}s`, target }] }
      : { rate: target, duration: `${seconds}s` }),
  };
  schedule.push({ name, target_rpm: target, start_seconds: offset, duration_seconds: seconds });
  if (name.startsWith('hold_')) {
    const tag = `{scenario:${name}}`;
    thresholds[`quotes_latency_ms${tag}`] = [`p(95)<=${config.p95_ms}`];
    thresholds[`quotes_error_rate${tag}`] = [`rate<=${config.max_error_rate}`];
    thresholds[`quotes_completed${tag}`] = [`count>=${Math.floor(target * seconds / 60) - 1}`];
    thresholds[`quotes_successful${tag}`] = [`count>=${Math.floor(target * seconds / 60 * (1 - config.max_error_rate))}`];
    thresholds[`dropped_iterations${tag}`] = ['count==0'];
    for (const name of Object.keys(connectionMetrics)) thresholds[`client_${name}_ms${tag}`] = ['p(95)>=0'];
    thresholds[`quotes_http_duration_ms${tag}`] = ['p(95)>=0'];
    for (const outcome of ['success', 'timeout', 'transport', 'http_429', 'http_5xx', 'http_other', 'invalid_body']) {
      thresholds[`quotes_outcomes{scenario:${name},outcome:${outcome}}`] = ['count>=0'];
    }
  }
  if (mode === 'autoscaling' && name !== 'warmup') {
    thresholds[`safety_errors{scenario:${name}}`] = [{
      threshold: `rate<=${config.abort_error_rate}`, abortOnFail: true,
      delayAbortEval: `${offset + config.abort_after_seconds}s`,
    }];
    thresholds[`dropped_iterations{scenario:${name}}`] = [{
      threshold: 'count==0', abortOnFail: true, delayAbortEval: `${offset + 30}s`,
    }];
  }
  // Dejar terminar las solicitudes antes de la siguiente fase.
  offset += seconds + config.grace_seconds;
}
addPhase('warmup', 500, config.warmup_seconds);
let previous = 500;
for (const rate of config.rates_rpm) {
  addPhase(`ramp_${rate}`, rate, config.ramp_seconds, previous);
  addPhase(`hold_${rate}`, rate, config.hold_seconds);
  previous = rate;
}

export const options = {
  scenarios, thresholds,
  summaryTrendStats: ['avg', 'min', 'max', 'p(50)', 'p(90)', 'p(95)', 'p(99)'],
  // 201 es el único estado exitoso del POST; el cuerpo se valida además abajo.
  maxRedirects: 0,
  tags: { experiment: 'EXP-ESC-01', run_id: __ENV.RUN_ID || 'manual' },
};
http.setResponseCallback(http.expectedStatuses(201));

export function setup() {
  const response = http.get(`${baseURL}/consultas/poliza-000001`, {
    timeout: '5s', responseCallback: http.expectedStatuses(200),
    tags: { name: 'preflight' },
  });
  if (response.status !== 200) throw new Error(`Dataset preflight failed: HTTP ${response.status}`);
}

export function quote() {
  const started = Date.now();
  const response = http.post(`${baseURL}/cotizaciones`, JSON.stringify({ product_id: 'producto-sintetico' }), {
    headers: { 'Content-Type': 'application/json' },
    timeout: `${config.timeout_seconds}s`, tags: { name: 'POST /cotizaciones' },
  });
  // Tiempo completo observado, incluidas conexión/TLS y errores; no solo respuestas 201.
  const elapsed = Date.now() - started;
  let valid = false;
  try {
    const body = response.json();
    valid = response.status === 201 && typeof body.id === 'string'
      && /^[0-9a-f-]{36}$/.test(body.id) && body.result === 'synthetic'
      && body.dataset === 'synthetic-v1' && body.rules_version === 'synthetic-v1';
  } catch (_) { /* Cuerpos inválidos también cuentan como error. */ }
  const outcome = valid ? 'success' : response.status === 0
    ? (response.error_code === 1050 ? 'timeout' : 'transport')
    : response.status === 429 ? 'http_429' : response.status >= 500 ? 'http_5xx'
    : response.status !== 201 ? 'http_other' : 'invalid_body';
  outcomes.add(1, { outcome });
  backendLatency.add(response.timings.duration);
  for (const [name, metric] of Object.entries(connectionMetrics)) metric.add(response.timings[name]);
  completed.add(1);
  successful.add(valid ? 1 : 0);
  errors.add(!valid);
  safetyErrors.add(!valid);
  latency.add(elapsed);
  // Sin sleep ni reintentos: el ejecutor fija la tasa de llegada.
}

export function handleSummary(data) {
  function values(metric, phase) {
    return data.metrics[`${metric}{scenario:${phase}}`]?.values || {};
  }
  const stages = config.rates_rpm.map((rate) => {
    const phase = `hold_${rate}`;
    const count = values('quotes_completed', phase).count || 0;
    const success = values('quotes_successful', phase).count || 0;
    const dropped = values('dropped_iterations', phase).count || 0;
    const error = values('quotes_error_rate', phase).rate;
    const percentiles = values('quotes_latency_ms', phase);
    const expected = Math.floor(rate * config.hold_seconds / 60);
    const valid = count >= expected - 1 && dropped === 0 && Number.isFinite(error);
    const reasons = [];
    if (!valid) reasons.push('Carga incompleta, iteraciones descartadas o datos ausentes');
    if (error > config.max_error_rate) reasons.push('Errores mayores al 1 %');
    if (percentiles['p(95)'] > config.p95_ms) reasons.push('p95 mayor a 250 ms');
    const failureBreakdown = {};
    for (const outcome of ['success', 'timeout', 'transport', 'http_429', 'http_5xx', 'http_other', 'invalid_body']) {
      failureBreakdown[outcome] = data.metrics[`quotes_outcomes{scenario:${phase},outcome:${outcome}}`]?.values?.count || 0;
    }
    return { client_timings: Object.fromEntries(Object.keys(connectionMetrics).map(name => [name, values(`client_${name}_ms`, phase)])), reasons, outcomes: failureBreakdown,
      http_duration_percentiles: values('quotes_http_duration_ms', phase),
      phase, measurement_status: count === 0 ? "not_measured" : valid ? "complete" : "incomplete", target_rpm: rate, expected, completed: count, successful: success,
      dropped, error_rate: error ?? null, percentiles,
      achieved_rpm: count * 60 / config.hold_seconds,
      successful_rpm: success * 60 / config.hold_seconds,
      valid_load: valid,
      passed: valid && error <= config.max_error_rate && percentiles['p(95)'] <= config.p95_ms
        && success >= Math.floor(expected * (1 - config.max_error_rate)) };
  });
  const report = { mode, report_version: 3, experiment: 'EXP-ESC-01', run_id: __ENV.RUN_ID || 'manual',
    replicas, base_url: baseURL, config, schedule, stages,
    finished_at: new Date().toISOString(), k6: data };
  return {
    [__ENV.SUMMARY_PATH || 'summary.json']: JSON.stringify(report, null, 2),
    stdout: stages.map(s => `${s.target_rpm} rpm: ${s.passed ? 'PASS' : 'FAIL'}; p95=${s.percentiles['p(95)'] ?? 'N/A'} ms; errors=${s.error_rate}; dropped=${s.dropped}`).join('\n') + '\n',
  };
}
