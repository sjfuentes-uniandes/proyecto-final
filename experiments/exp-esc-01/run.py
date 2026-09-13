#!/usr/bin/env python3
"""Ejecuta una repetición explícita; permite preparar la BD entre ejecuciones."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import threading

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SERVICES = ['catalogo', 'simulador', 'consulta', 'cotizacion']


def command(args):
    result = subprocess.run(args, text=True, capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f'{args[0]} {args[1]} (código {result.returncode}): {result.stderr.strip()}')
    return result.stdout


def aws(*args):
    return json.loads(command(['aws', *args, '--output', 'json']))


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')


def snapshot(configuration, replicas, dynamic=False):
    """Conserva evidencia aun cuando el sistema esté degradado."""
    result = {'services': {}, 'tasks': [], 'target_health': {}, 'issues': [], 'collection_errors': []}
    cluster = configuration['cluster']
    def query(*args):
        try:
            return aws(*args)
        except Exception as error:
            result['collection_errors'].append(str(error))
            return {}
    services = query('ecs', 'describe-services', '--cluster', cluster, '--services', *SERVICES)
    result['services'] = services
    if services and (services.get('failures') or len(services.get('services', [])) != 4):
        result['issues'].append('No se encontraron los cuatro servicios')
    for service in services.get('services', []):
        name = service['serviceName']
        expected = replicas if name == 'cotizacion' else 1
        if dynamic and name == 'cotizacion':
            expected = service['desiredCount']
            if not replicas <= expected <= configuration['autoscaling']['max_replicas']:
                result['issues'].append('cotizacion: réplicas fuera de límites')
        if (service['desiredCount'], service['runningCount'], service['pendingCount']) != (expected, expected, 0):
            result['issues'].append(f'{name}: número de tareas no estable')
        if len(service['deployments']) != 1 or service['deployments'][0].get('rolloutState') != 'COMPLETED':
            result['issues'].append(f'{name}: despliegue no completado')
        if service['taskDefinition'] != configuration['task_definitions'][name]:
            result['issues'].append(f'{name}: revisión diferente a Terraform')
        arns = query('ecs', 'list-tasks', '--cluster', cluster, '--service-name', name).get('taskArns', [])
        details = query('ecs', 'describe-tasks', '--cluster', cluster, '--tasks', *arns) if arns else {}
        if details and (details.get('failures') or len(details.get('tasks', [])) != expected):
            result['issues'].append(f'{name}: tareas incompletas')
        for task in details.get('tasks', []):
            container = next((c for c in task['containers'] if c['name'] == name), {})
            if container.get('imageDigest') != configuration['image_digests'][name]:
                result['issues'].append(f'{name}: digest distinto en {task["taskArn"]}')
            if task.get('healthStatus') != 'HEALTHY':
                result['issues'].append(f'{name}: tarea no saludable {task["taskArn"]}')
        result['tasks'].extend(details.get('tasks', []))
    result['target_health'] = query('elbv2', 'describe-target-health', '--target-group-arn', configuration['quotation_target_group'])
    states = result['target_health'].get('TargetHealthDescriptions', [])
    expected_targets = next((s['desiredCount'] for s in services.get('services', [])
                            if s['serviceName'] == 'cotizacion'), replicas) if dynamic else replicas
    if result['target_health'] and (len(states) != expected_targets or any(t['TargetHealth']['State'] != 'healthy' for t in states)):
        result['issues'].append('ALB: destinos distintos a las réplicas saludables')
    result['healthy'] = None if result['collection_errors'] else not result['issues']
    result['status'] = 'unverified' if result['collection_errors'] else ('healthy' if result['healthy'] else 'unstable')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['autoscaling', 'fixed'], default='autoscaling')
    parser.add_argument('--replicas', type=int, choices=[1, 2, 3])
    parser.add_argument('--series', required=True, help='Identificador común de las repeticiones de la misma política o escenarios fijos')
    parser.add_argument('--dataset-state', required=True, help='Descripción del estado inicial de la BD/preparación')
    parser.add_argument('--repetition', type=int, required=True, choices=[1, 2, 3])
    args = parser.parse_args()
    if not args.series.replace('-', '').replace('_', '').isalnum():
        parser.error('--series solo admite letras, números, guiones y guiones bajos')
    outputs = json.loads(command(['terraform', '-chdir=' + str(ROOT / 'infra' / 'services'), 'output', '-json']))
    configuration = outputs['experiment_configuration']['value']
    os.environ['AWS_DEFAULT_REGION'] = configuration['region']
    os.environ['AWS_REGION'] = configuration['region']
    os.environ['AWS_PAGER'] = ''
    args.replicas = args.replicas or configuration['quotation_replicas']
    if configuration.get('autoscaling', {}).get('enabled', False) != (args.mode == 'autoscaling'):
        raise RuntimeError('Aplicar quotation_autoscaling_enabled según --mode antes de ejecutar')
    if configuration['quotation_replicas'] != args.replicas:
        raise RuntimeError('Primero aplicar quotation_replicas con Terraform')
    folder = HERE / 'results' / args.series / ('autoscaling' if args.mode == 'autoscaling' else f'replicas-{args.replicas}')
    folder.mkdir(parents=True, exist_ok=True)
    metadata = {'mode': args.mode, 'configuration': configuration, 'dataset_state': args.dataset_state,
        'k6_version': command(['k6', 'version']).strip(),
        'git_commit': command(['git', '-C', str(ROOT), 'rev-parse', 'HEAD']).strip(),
        'git_status': command(['git', '-C', str(ROOT), 'status', '--short']),
        'script_sha256': hashlib.sha256((HERE / 'scalability.js').read_bytes()).hexdigest(),
        'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT / 'src').rglob('*'))
            if p.is_file() and (p.suffix == '.py' or p.name in ['Dockerfile', 'requirements.txt'])},
        'config': json.loads((HERE / ('autoscaling-config.json' if args.mode == 'autoscaling' else 'config.json')).read_text())}
    metadata_path = folder / 'metadata.json'
    if metadata_path.exists():
        previous = json.loads(metadata_path.read_text())
        for key in ['configuration', 'k6_version', 'script_sha256', 'source_sha256', 'config']:
            if previous.get(key) != metadata[key]:
                raise RuntimeError(f'Cambió {key}; usar otra serie para conservar comparabilidad')
    else:
        save(metadata_path, metadata)
    any_failure = False
    for repetition in [args.repetition]:
        run = folder / f'run-{repetition}'
        run.mkdir()
        save(run / 'metadata.json', metadata)
        if args.mode == 'autoscaling':
            from scaling_evidence import capture
            try:
                scaling = capture(aws, configuration)
            except Exception as error:
                scaling = {'issues': ['No se pudo verificar autoscaling'], 'collection_error': str(error)}
            save(run / 'scaling-before.json', scaling)
            if scaling['issues']:
                save(run / 'execution.json', {'status': 'precondition_failed', 'exit_code': None})
                print('No se inició k6:', scaling)
                return 2
        before = snapshot(configuration, args.replicas)
        save(run / 'before.json', before)
        if not before['healthy']:
            save(run / 'execution.json', {'status': 'precondition_failed', 'exit_code': None})
            print('No se inició k6. Revisar before.json:', before['issues'], before['collection_errors'])
            return 2
        start = dt.datetime.now(dt.timezone.utc).isoformat()
        env = dict(os.environ, MODE=args.mode, BASE_URL=outputs['entry_url']['value'], REPLICAS=str(args.replicas),
            RUN_ID=f'{args.series}-{args.replicas}-{repetition}', SUMMARY_PATH=str(run / 'summary.json'))
        print(f'Iniciando {env["RUN_ID"]}', flush=True)
        stop = threading.Event()
        def monitor():
            with (run / 'scaling-timeline.jsonl').open('w') as timeline:
                while not stop.is_set():
                    point = {'timestamp': dt.datetime.now(dt.timezone.utc).isoformat()}
                    try:
                        response = aws('ecs', 'describe-services', '--cluster', configuration['cluster'], '--services', *SERVICES)
                        point['services'] = [{k: service[k] for k in ['serviceName', 'desiredCount', 'runningCount', 'pendingCount']}
                                             for service in response.get('services', [])]
                        point['failures'] = response.get('failures', [])
                    except Exception as error:
                        point['collection_error'] = str(error)
                    timeline.write(json.dumps(point) + '\n')
                    timeline.flush()
                    stop.wait(15)
        worker = threading.Thread(target=monitor, daemon=True)
        worker.start()
        with (run / 'console.log').open('w') as logfile:
            result = subprocess.run(['k6', 'run', '--no-thresholds=false', '--summary-mode=full',
                '--new-machine-readable-summary=false', str(HERE / 'scalability.js')], env=env,
                stdout=logfile, stderr=subprocess.STDOUT, cwd=HERE)
        end = dt.datetime.now(dt.timezone.utc).isoformat()
        stop.set()
        worker.join(timeout=125)
        save(run / 'execution.json', {'start': start, 'end': end, 'exit_code': result.returncode})
        after = snapshot(configuration, args.replicas, dynamic=args.mode == 'autoscaling')
        save(run / 'after.json', after)
        if not after['healthy']:
            print('Estado final ' + after['status'] + ':', after['issues'], after['collection_errors'])
        print(f'Finalizó con código {result.returncode}; evidencia: {run}', flush=True)
        if not (run / 'summary.json').exists():
            raise RuntimeError('k6 no produjo resumen; revisar console.log')
        if args.mode == 'autoscaling':
            try:
                save(run / 'scaling-activities.json', aws('application-autoscaling', 'describe-scaling-activities',
                    '--service-namespace', 'ecs', '--scalable-dimension', 'ecs:service:DesiredCount',
                    '--resource-id', f'service/{configuration["cluster"]}/cotizacion'))
            except Exception as error:
                save(run / 'scaling-activities.json', {'collection_error': str(error)})
        # 99 corresponde a thresholds incumplidos; conservar y continuar las repeticiones.
        if result.returncode not in (0, 99):
            raise RuntimeError('Error de ejecución k6; no es un resultado de capacidad válido')
        any_failure |= result.returncode != 0 or not after["healthy"]
    print('Repetición conservada. Preparar BD y verificar salud antes de la siguiente. Ejecutar collect.py y summarize.py.')
    return 1 if any_failure else 0


if __name__ == '__main__':
    raise SystemExit(main())
