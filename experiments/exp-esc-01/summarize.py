#!/usr/bin/env python3
"""Informe de capacidad, cumplimiento del objetivo y calidad de la medición."""
import argparse
import csv
import json
from pathlib import Path
from statistics import median


def capacity(stages):
    """No confundir no demostrar 500 rpm con tener capacidad cero."""
    lower = None
    for stage in stages:
        if stage['passed']:
            lower = stage['target_rpm']
        else:
            return {'demonstrated_rpm': lower,
                    'first_failed_rpm': stage['target_rpm'],
                    'boundary': 'sla_failure' if stage['valid_load'] else 'measurement_incomplete'}
    return {'demonstrated_rpm': lower, 'first_failed_rpm': None, 'boundary': 'at_least_maximum_tested'}


def summarize(series):
    if (series / 'autoscaling').exists():
        from summarize_autoscaling import summarize as automatic
        return automatic(series)
    rows, individual, fingerprints, missing = [], [], [], []
    all_runs = {}
    for replicas in [1, 2, 3]:
        folder = series / f'replicas-{replicas}'
        path = folder / 'metadata.json'
        if not path.exists():
            missing.append(f'replicas-{replicas}/metadata.json')
            continue
        metadata = json.loads(path.read_text())
        config = dict(metadata['configuration'])
        config.pop('quotation_replicas', None)
        if not config.get('autoscaling', {}).get('enabled'):
            config.pop('autoscaling', None)
        fingerprints.append(json.dumps({'infra': config, 'script': metadata['script_sha256'],
            'profile': metadata['config'], 'k6': metadata['k6_version'],
            'source': metadata.get('source_sha256')}, sort_keys=True))
        runs = []
        for repetition in [1, 2, 3]:
            run = folder / f'run-{repetition}'
            if not (run / 'summary.json').exists() or not (run / 'execution.json').exists():
                missing.append(str(run.relative_to(series)))
                continue
            execution = json.loads((run / 'execution.json').read_text())
            if execution.get('exit_code') not in [0, 99]:
                missing.append(str(run.relative_to(series)) + ': error de ejecución')
                continue
            summary = json.loads((run / 'summary.json').read_text())
            if summary['replicas'] != replicas or summary['config'] != metadata['config']:
                raise ValueError('Resumen incompatible con metadata')
            before = json.loads((run / 'before.json').read_text()) if (run / 'before.json').exists() else None
            after = json.loads((run / 'after.json').read_text()) if (run / 'after.json').exists() else None
            # Retener resúmenes históricos aunque el runner anterior no guardara after.json.
            if before is None or after is None:
                missing.append(str(run.relative_to(series)) + ': snapshot ausente')
            if before and (before.get('healthy') is False or before.get('collection_errors')):
                missing.append(str(run.relative_to(series)) + ': precondición fallida')
            if after and after.get('collection_errors'):
                missing.append(str(run.relative_to(series)) + ': captura posterior incompleta')
            local_meta = json.loads((run / 'metadata.json').read_text()) if (run / 'metadata.json').exists() else metadata
            individual.append({'replicas': replicas, 'repetition': repetition,
                'dataset_state': local_meta['dataset_state'], 'capacity': capacity(summary['stages']),
                'post_health': after.get('healthy') if after else None,
                'post_issues': after.get('issues', []) if after else ['Snapshot posterior no disponible'],
                'stages': summary['stages']})
            runs.append(summary)
        all_runs[replicas] = runs
        for rate in metadata['config']['rates_rpm']:
            stages = [stage for run in runs for stage in run['stages'] if stage['target_rpm'] == rate]
            if not stages:
                continue
            def med(values):
                return median(values) if len(values) == 3 and all(isinstance(v, (int, float)) for v in values) else None
            rows.append({'replicas': replicas, 'target_rpm': rate, 'repetitions': len(stages),
                'median_p50_ms': med([s['percentiles'].get('p(50)') for s in stages]),
                'median_p90_ms': med([s['percentiles'].get('p(90)') for s in stages]),
                'median_p95_ms': med([s['percentiles'].get('p(95)') for s in stages]),
                'median_p99_ms': med([s['percentiles'].get('p(99)') for s in stages]),
                'median_error_rate': med([s['error_rate'] for s in stages]),
                'median_achieved_rpm': med([s['achieved_rpm'] for s in stages]),
                'median_successful_rpm': med([s['successful_rpm'] for s in stages]),
                'valid_repetitions': sum(s['valid_load'] for s in stages),
                'passed_repetitions': sum(s['passed'] for s in stages),
                'dropped_total': sum(s['dropped'] for s in stages)})
    comparable = not missing and len(fingerprints) == 3 and len(set(fingerprints)) == 1
    limits = {}
    for replicas, runs in all_runs.items():
        caps = [capacity(run['stages']) for run in runs]
        values = [c['demonstrated_rpm'] for c in caps]
        limits[str(replicas)] = {
            'median_demonstrated_rpm': median(values) if len(values) == 3 and all(v is not None for v in values) else None,
            'individual': caps,
        }
    target = next((r for r in rows if r['replicas'] == 3 and r['target_rpm'] == 50000), None)
    objective = 'inconcluso'
    if comparable and target and target['valid_repetitions'] == 3:
        objective = 'cumple_en_tres_repeticiones' if target['passed_repetitions'] == 3 else 'no_cumple_en_todas_las_repeticiones'
    one = limits.get('1', {}).get('median_demonstrated_rpm')
    three = limits.get('3', {}).get('median_demonstrated_rpm')
    growth = 'inconcluso'
    ratio = None
    if comparable and one is not None and three is not None:
        ratio = three / one
        growth = 'aumenta_capacidad_demostrada' if three > one else 'no_se_demuestra_aumento_en_niveles_probados'
    report = {'report_version': 2, 'configuration_comparable': comparable, 'missing_evidence': missing,
        'objective_50000_rpm_with_3_replicas': objective,
        'scaling_1_to_3': growth, 'ratio_demonstrated_capacity_3_over_1': ratio,
        'capacity_by_replicas': limits, 'individual_results': individual, 'stages': rows,
        'interpretation': [
            'No aprobar 500 rpm significa capacidad no demostrada en el rango, no capacidad cero.',
            'El cociente compara niveles demostrados, no límites exactos de capacidad ni escalamiento lineal.',
            'El objetivo exige tres repeticiones válidas y aprobadas; también se publican sus medianas.',
            'Un estado final no saludable es un resultado del ensayo, no se descarta.',
            'Verificar igualdad del dataset, red y recursos del generador; los snapshots no certifican ausencia de reemplazos durante la carga.',
            'Correlacionar CloudWatch antes de atribuir saturación a CPU, RDS, ALB o generador.']}
    series.mkdir(parents=True, exist_ok=True)
    (series / 'comparison.json').write_text(json.dumps(report, indent=2) + '\n')
    if rows:
        with (series / 'comparison.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    lines = ['# EXP-ESC-01', '', f'Objetivo 50.000 rpm con 3 réplicas: **{objective}**.',
             f'Escalamiento 1 → 3: **{growth}**.', '',
             '| Réplicas | RPM objetivo | p95 mediana (ms) | Error mediana | RPM exitosas mediana | Válidas | Aprobadas |',
             '| --- | --- | --- | --- | --- | --- | --- |']
    for r in rows:
        lines.append(f"| {r['replicas']} | {r['target_rpm']} | {r['median_p95_ms']} | {r['median_error_rate']} | {r['median_successful_rpm']} | {r['valid_repetitions']}/3 | {r['passed_repetitions']}/3 |")
    lines += ['', 'Valores null/None: evidencia insuficiente; no equivalen a cero.', '', *report['interpretation']]
    (series / 'report.md').write_text('\n'.join(lines) + '\n')
    print(f'Objetivo: {objective}; escalamiento: {growth}; evidencia comparable: {comparable}')
    print(f'Informe: {series / "report.md"}')
    return 0 if comparable else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('series', type=Path)
    raise SystemExit(summarize(parser.parse_args().series))
