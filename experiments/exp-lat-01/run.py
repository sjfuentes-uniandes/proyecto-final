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
CLUSTER='solventa-exp'; REGION='us-east-1'; API_ID='ox05ty0z5g'
TARGET_GROUP_ARNS={
    'cotizacion':'arn:aws:elasticloadbalancing:us-east-1:882567899411:targetgroup/solventa-exp-cotizacion/26497e586d321e91',
    'consulta':'arn:aws:elasticloadbalancing:us-east-1:882567899411:targetgroup/solventa-exp-consulta/ee5f0800f64af5a6',
}
def discover_config():
    """Construye config directamente desde AWS (sin Terraform local; ver exp-dis-01/HANDOFF.md)."""
    os.environ.update(AWS_REGION=REGION,AWS_DEFAULT_REGION=REGION,AWS_PAGER='')
    services=aws('ecs','describe-services','--cluster',CLUSTER,'--services',*SERVICES)['services']
    by_name={s['serviceName']:s for s in services}
    task_definitions={name:s['taskDefinition'] for name,s in by_name.items()}
    image_digests={}
    task_defs={}
    for name,arn in task_definitions.items():
        task_defs[name]=aws('ecs','describe-task-definition','--task-definition',arn)['taskDefinition']
        image=task_defs[name]['containerDefinitions'][0]['image']
        image_digests[name]=image.split('@',1)[1] if '@' in image else None
    quotation_policies=aws('application-autoscaling','describe-scaling-policies','--service-namespace','ecs','--resource-id',f'service/{CLUSTER}/cotizacion')['ScalingPolicies']
    backend_policies=[]
    for name in ['catalogo','simulador','consulta']:
        backend_policies+=aws('application-autoscaling','describe-scaling-policies','--service-namespace','ecs','--resource-id',f'service/{CLUSTER}/{name}')['ScalingPolicies']
    simulador_env={e['name']:e['value'] for e in task_defs['simulador']['containerDefinitions'][0]['environment']}
    cotizacion_env={e['name']:e['value'] for e in task_defs['cotizacion']['containerDefinitions'][0]['environment']}
    log_groups={name:f'/ecs/{CLUSTER}/{name}' for name in SERVICES}
    log_groups.update(service_connect=f'/ecs/{CLUSTER}/service-connect', ecs_events=f'/ecs/{CLUSTER}/events', api_gateway=f'/aws/apigateway/{CLUSTER}')
    config={
        'region':REGION,'cluster':CLUSTER,'api_id':API_ID,
        'autoscaling':{'enabled':bool(quotation_policies)},
        'backend_autoscaling':{'enabled':bool(backend_policies)},
        'database_identifier':'solventa-exp',
        'quotation_replicas':by_name['cotizacion']['desiredCount'],
        'task_definitions':task_definitions,
        'image_digests':image_digests,
        'external_delay_ms':int(simulador_env.get('RESPONSE_DELAY_MS',-1)),
        'external_retries':int(cotizacion_env.get('EXTERNAL_SOURCE_RETRIES',-1)),
        'target_groups':{name:{'arn':arn} for name,arn in TARGET_GROUP_ARNS.items()},
        'log_groups':log_groups,
    }
    entry_url='https://ox05ty0z5g.execute-api.us-east-1.amazonaws.com'
    return config,entry_url
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
    config, entry_url = discover_config()
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
    env = dict(os.environ, BASE_URL=entry_url, RUN_ID=f'{args.series}-{args.repetition}', SUMMARY_PATH=str(run/'summary.json'))
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    with (run/'console.log').open('w') as log:
        outcome = subprocess.run(['k6', 'run', '-e', f'BASE_URL={env["BASE_URL"]}',
                                  '-e', f'RUN_ID={env["RUN_ID"]}', '-e', f'SUMMARY_PATH={env["SUMMARY_PATH"]}',
                                  'latency.js'], cwd=HERE, env=env, stdout=log, stderr=subprocess.STDOUT)
    ended = dt.datetime.now(dt.timezone.utc).isoformat(); save(run/'execution.json', {'start':started,'end':ended,'exit_code':outcome.returncode})
    save(run/'after.json', snapshot(config))
    if outcome.returncode not in (0, 99) or not (run/'summary.json').exists(): raise RuntimeError('k6 no produjo una medición válida')
if __name__ == '__main__': main()
