#!/usr/bin/env python3
"""Ejecuta una repetición verificable de EXP-LAT-01; nunca cambia AWS."""
import argparse, datetime as dt, hashlib, json, os, subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SERVICES = ['catalogo', 'simulador', 'consulta', 'cotizacion']

def command(args):
    result = subprocess.run(args, text=True, capture_output=True, timeout=120)
    if result.returncode: raise RuntimeError(f"{' '.join(args[:2])}: {result.stderr.strip()}")
    return result.stdout
def aws(*args): return json.loads(command(['aws', *args, '--output', 'json']))
def save(path, value): path.write_text(json.dumps(value, indent=2) + '\n')
def snapshot(config):
    result = {'services': {}, 'tasks': {}, 'target_health': {}, 'issues': [], 'collection_errors': []}
    def query(*args):
        try: return aws(*args)
        except Exception as error: result['collection_errors'].append(str(error)); return {}
    services = query('ecs', 'describe-services', '--cluster', config['cluster'], '--services', *SERVICES)
    result['services'] = services
    if services.get('failures') or len(services.get('services', [])) != len(SERVICES): result['issues'].append('No se encontraron los cuatro servicios')
    for service in services.get('services', []):
        name = service['serviceName']
        if (service['desiredCount'], service['runningCount'], service['pendingCount']) != (1, 1, 0): result['issues'].append(f'{name}: no está fijo en una tarea')
        if service['taskDefinition'] != config['task_definitions'][name]: result['issues'].append(f'{name}: revisión distinta a Terraform')
        task_arns = query('ecs', 'list-tasks', '--cluster', config['cluster'], '--service-name', name).get('taskArns', [])
        tasks = query('ecs', 'describe-tasks', '--cluster', config['cluster'], '--tasks', *task_arns).get('tasks', []) if task_arns else []
        result['tasks'][name] = tasks
        if len(tasks) != 1: result['issues'].append(f'{name}: tareas incompletas')
        for task in tasks:
            container = next((c for c in task.get('containers', []) if c['name'] == name), {})
            if task.get('healthStatus') != 'HEALTHY' or container.get('imageDigest') != config['image_digests'][name]: result['issues'].append(f'{name}: salud o digest inválido')
    for name, group in config['target_groups'].items():
        health = query('elbv2', 'describe-target-health', '--target-group-arn', group['arn'])
        result['target_health'][name] = health
        targets = health.get('TargetHealthDescriptions', [])
        if len(targets) != 1 or any(t['TargetHealth']['State'] != 'healthy' for t in targets): result['issues'].append(f'{name}: target group no saludable')
    result['healthy'] = not result['issues'] and not result['collection_errors']
    return result
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--series', required=True); parser.add_argument('--repetition', required=True, choices=['1','2','3'])
    parser.add_argument('--dataset-state', required=True); args = parser.parse_args()
    if not args.series.replace('-', '').replace('_', '').isalnum(): parser.error('Serie inválida')
    outputs = json.loads(command(['terraform', '-chdir=' + str(ROOT / 'infra/services'), 'output', '-json']))
    config = outputs['experiment_configuration']['value']
    if config['quotation_replicas'] != 1 or config['autoscaling']['enabled'] or config['backend_autoscaling']['enabled']:
        raise RuntimeError('Aplicar escenario LAT fijo: cotizacion=1 y autoscaling deshabilitado')
    if config['external_delay_ms'] != 50 or config['external_retries'] != 0:
        raise RuntimeError('El simulador debe permanecer en 50 ms y sin reintentos')
    os.environ.update(AWS_REGION=config['region'], AWS_DEFAULT_REGION=config['region'], AWS_PAGER='')
    folder = HERE / 'results' / args.series; run = folder / f'run-{args.repetition}'
    if run.exists(): raise RuntimeError(f'No sobrescribir evidencia: {run}')
    run.mkdir(parents=True)
    metadata = {'configuration': config, 'dataset_state': args.dataset_state, 'git_commit': command(['git','-C',str(ROOT),'rev-parse','HEAD']).strip(), 'git_status': command(['git','-C',str(ROOT),'status','--short']), 'k6_version': command(['k6','version']).strip(), 'script_sha256': hashlib.sha256((HERE/'latency.js').read_bytes()).hexdigest(), 'config': json.loads((HERE/'config.json').read_text())}
    series_metadata = folder / 'metadata.json'
    if series_metadata.exists():
        previous = json.loads(series_metadata.read_text())
        for key in ['configuration', 'k6_version', 'script_sha256', 'config']:
            if previous.get(key) != metadata[key]:
                raise RuntimeError(f'Cambió {key}; usar otra serie para conservar comparabilidad')
    else:
        save(series_metadata, metadata)
    save(run/'metadata.json', metadata)
    before = snapshot(config); save(run/'before.json', before)
    if not before['healthy']: save(run/'execution.json', {'status':'precondition_failed'}); raise RuntimeError('Precondición fallida; revisar before.json')
    env = dict(os.environ, BASE_URL=outputs['entry_url']['value'], RUN_ID=f'{args.series}-{args.repetition}', SUMMARY_PATH=str(run/'summary.json'))
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    with (run/'console.log').open('w') as log: outcome = subprocess.run(['k6','run','latency.js'], cwd=HERE, env=env, stdout=log, stderr=subprocess.STDOUT)
    ended = dt.datetime.now(dt.timezone.utc).isoformat(); save(run/'execution.json', {'start':started,'end':ended,'exit_code':outcome.returncode})
    save(run/'after.json', snapshot(config))
    if outcome.returncode not in (0, 99) or not (run/'summary.json').exists(): raise RuntimeError('k6 no produjo una medición válida')
if __name__ == '__main__': main()
