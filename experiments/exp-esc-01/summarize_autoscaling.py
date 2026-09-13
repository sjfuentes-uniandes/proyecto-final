"""Informe de la política automática, independiente de la comparación fija 1/2/3."""
import json
from statistics import median


def summarize(series):
    runs, missing = [], []
    for repetition in [1, 2, 3]:
        folder = series / 'autoscaling' / f'run-{repetition}'
        if not (folder / 'summary.json').exists():
            missing.append(repetition)
            continue
        summary = json.loads((folder / 'summary.json').read_text())
        timeline = [json.loads(line) for line in (folder / 'scaling-timeline.jsonl').read_text().splitlines()] if (folder / 'scaling-timeline.jsonl').exists() else []
        counts = [service for point in timeline for service in point.get('services', []) if service['serviceName'] == 'cotizacion']
        after = json.loads((folder / 'after.json').read_text()) if (folder / 'after.json').exists() else {}
        runs.append({'repetition': repetition, 'stages': summary['stages'],
                     'max_desired': max((s['desiredCount'] for s in counts), default=None),
                     'max_running': max((s['runningCount'] for s in counts), default=None),
                     'observed_scale_out': len({s['desiredCount'] for s in counts}) > 1,
                     'timeline_errors': sum('collection_error' in p or bool(p.get('failures')) for p in timeline),
                     'post_status': after.get('status', 'unverified')})
    rows = []
    rates = sorted({s['target_rpm'] for run in runs for s in run['stages']})
    for rate in rates:
        stages = [s for run in runs for s in run['stages'] if s['target_rpm'] == rate]
        complete = [s for s in stages if s['valid_load']]
        rows.append({'target_rpm': rate, 'complete_repetitions': len(complete),
                     'passed_repetitions': sum(s['passed'] for s in complete),
                     'median_p95_ms': median(s['percentiles']['p(95)'] for s in complete) if complete else None,
                     'median_error_rate': median(s['error_rate'] for s in complete) if complete else None})
    report = {'mode': 'autoscaling', 'missing_repetitions': missing, 'runs': runs, 'stages': rows,
              'note': 'Mesetas no alcanzadas o incompletas no demuestran capacidad. Consultar timeline y actividades para tiempos de escalamiento. No estima ganancia entre réplicas fijas.'}
    (series / 'autoscaling-report.json').write_text(json.dumps(report, indent=2) + '\n')
    lines = ['# Resultados de autoscaling', '', report['note'], '',
             '| RPM | Mesetas completas / 3 | Aprobadas / 3 | p95 mediana ms | Error mediana |',
             '| --- | --- | --- | --- | --- |']
    for r in rows:
        lines.append(f"| {r['target_rpm']} | {r['complete_repetitions']} | {r['passed_repetitions']} | {r['median_p95_ms']} | {r['median_error_rate']} |")
    lines += ['', 'None significa evidencia insuficiente.', '', '| Repetición | Máximo solicitado | Máximo ejecutándose | Estado posterior | Errores captura |', '| --- | --- | --- | --- | --- |']
    for r in runs:
        lines.append(f"| {r['repetition']} | {r['max_desired']} | {r['max_running']} | {r['post_status']} | {r['timeline_errors']} |")
    lines.append(f'\nRepeticiones ausentes: {missing}')
    (series / 'report.md').write_text('\n'.join(lines) + '\n')
    print(series / 'report.md')
    return 1 if missing else 0
