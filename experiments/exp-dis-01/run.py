#!/usr/bin/env python3
"""Ejecuta EXP-DIS-01 e inyecta una detención ECS explícitamente autorizada."""
import argparse, datetime as dt, hashlib, json, os, subprocess, threading, time
from pathlib import Path
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]; SERVICES = ['catalogo','simulador','consulta','cotizacion']
def command(args):
    r=subprocess.run(args,text=True,capture_output=True,timeout=120)
    if r.returncode: raise RuntimeError(f"{' '.join(args[:2])}: {r.stderr.strip()}")
    return r.stdout
def aws(*args): return json.loads(command(['aws',*args,'--output','json']))
def save(path,data): path.write_text(json.dumps(data,indent=2)+'\n')
CLUSTER='solventa-exp'; REGION='us-east-1'
TARGET_GROUP_ARNS={
    'cotizacion':'arn:aws:elasticloadbalancing:us-east-1:882567899411:targetgroup/solventa-exp-cotizacion/26497e586d321e91',
    'consulta':'arn:aws:elasticloadbalancing:us-east-1:882567899411:targetgroup/solventa-exp-consulta/ee5f0800f64af5a6',
}
ALB_ARN='arn:aws:elasticloadbalancing:us-east-1:882567899411:loadbalancer/app/solventa-exp-entry/11236b51ca2cd7fa'
def arn_suffix(arn): return arn.split(':',5)[-1]
def discover_config():
    """Construye config directamente desde AWS (sin Terraform local; ver HANDOFF.md)."""
    os.environ.update(AWS_REGION=REGION,AWS_DEFAULT_REGION=REGION,AWS_PAGER='')
    services=aws('ecs','describe-services','--cluster',CLUSTER,'--services',*SERVICES)['services']
    by_name={s['serviceName']:s for s in services}
    task_definitions={name:s['taskDefinition'] for name,s in by_name.items()}
    quotation_target=aws('application-autoscaling','describe-scalable-targets','--service-namespace','ecs','--resource-ids',f'service/{CLUSTER}/cotizacion')['ScalableTargets']
    quotation_policies=aws('application-autoscaling','describe-scaling-policies','--service-namespace','ecs','--resource-id',f'service/{CLUSTER}/cotizacion')['ScalingPolicies']
    backend_policies=[]
    for name in ['catalogo','simulador','consulta']:
        backend_policies+=aws('application-autoscaling','describe-scaling-policies','--service-namespace','ecs','--resource-id',f'service/{CLUSTER}/{name}')['ScalingPolicies']
    simulador_def=aws('ecs','describe-task-definition','--task-definition',task_definitions['simulador'])['taskDefinition']
    cotizacion_def=aws('ecs','describe-task-definition','--task-definition',task_definitions['cotizacion'])['taskDefinition']
    simulador_env={e['name']:e['value'] for e in simulador_def['containerDefinitions'][0]['environment']}
    cotizacion_env={e['name']:e['value'] for e in cotizacion_def['containerDefinitions'][0]['environment']}
    log_groups={name:f'/ecs/{CLUSTER}/{name}' for name in SERVICES}
    log_groups.update(service_connect=f'/ecs/{CLUSTER}/service-connect', ecs_events=f'/ecs/{CLUSTER}/events')
    config={
        'region':REGION,'cluster':CLUSTER,
        'autoscaling':{'enabled':bool(quotation_policies),
                       'min_replicas':quotation_target[0]['MinCapacity'] if quotation_target else None,
                       'max_replicas':quotation_target[0]['MaxCapacity'] if quotation_target else None},
        'backend_autoscaling':{'enabled':bool(backend_policies)},
        'database_identifier':'solventa-exp',
        'quotation_replicas':by_name['cotizacion']['desiredCount'],
        'task_definitions':task_definitions,
        'external_delay_ms':int(simulador_env.get('RESPONSE_DELAY_MS',-1)),
        'external_retries':int(cotizacion_env.get('EXTERNAL_SOURCE_RETRIES',-1)),
        'target_groups':{name:{'arn':arn,'arn_suffix':arn_suffix(arn)} for name,arn in TARGET_GROUP_ARNS.items()},
        'alb':{'arn_suffix':arn_suffix(ALB_ARN)},
        'log_groups':log_groups,
    }
    entry_url='https://ox05ty0z5g.execute-api.us-east-1.amazonaws.com'
    return config,entry_url
def observe(config):
    result={'timestamp':dt.datetime.now(dt.timezone.utc).isoformat(),'services':{},'target_health':{},'errors':[]}
    try:
        result['services']=aws('ecs','describe-services','--cluster',config['cluster'],'--services',*SERVICES)
        result['target_health']=aws('elbv2','describe-target-health','--target-group-arn',config['target_groups']['cotizacion']['arn'])
    except Exception as error: result['errors'].append(str(error))
    return result
def healthy_two(point, config):
    services=point.get('services',{}).get('services',[]); quotation=next((s for s in services if s['serviceName']=='cotizacion'),{})
    targets=point.get('target_health',{}).get('TargetHealthDescriptions',[])
    return (quotation.get('desiredCount'),quotation.get('runningCount'),quotation.get('pendingCount')) == (2,2,0) and len(targets)==2 and all(t['TargetHealth']['State']=='healthy' for t in targets)
def initial_check(config):
    point=observe(config); issues=list(point['errors']); services=point.get('services',{}).get('services',[])
    if len(services) != len(SERVICES): issues.append('No se encontraron los cuatro servicios')
    for service in services:
        expected=2 if service['serviceName']=='cotizacion' else 1
        if (service['desiredCount'],service['runningCount'],service['pendingCount']) != (expected,expected,0): issues.append(f"{service['serviceName']}: conteo inicial inválido")
        if service['taskDefinition'] != config['task_definitions'][service['serviceName']]: issues.append(f"{service['serviceName']}: definición distinta")
    if not healthy_two(point,config): issues.append('cotizacion no tiene dos destinos sanos')
    return point,issues
def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--series',required=True); p.add_argument('--repetition',required=True,choices=['1','2','3']); p.add_argument('--dataset-state',required=True); p.add_argument('--fault-task-arn',required=True); args=p.parse_args()
    config,entry_url=discover_config()
    if config['quotation_replicas']!=2 or config['autoscaling']['enabled'] or config['backend_autoscaling']['enabled']: raise RuntimeError('Aplicar escenario DIS fijo: cotizacion=2 y autoscaling deshabilitado')
    if config['external_delay_ms'] != 50 or config['external_retries'] != 0: raise RuntimeError('El simulador debe permanecer en 50 ms y sin reintentos')
    os.environ.update(AWS_REGION=config['region'],AWS_DEFAULT_REGION=config['region'],AWS_PAGER='')
    current=aws('ecs','describe-tasks','--cluster',config['cluster'],'--tasks',args.fault_task_arn)['tasks']
    if len(current)!=1 or current[0].get('group') != 'service:cotizacion' or current[0].get('lastStatus')!='RUNNING': raise RuntimeError('--fault-task-arn debe ser una tarea RUNNING de cotizacion')
    folder=HERE/'results'/args.series; run=folder/f'run-{args.repetition}'
    if run.exists(): raise RuntimeError(f'No sobrescribir evidencia: {run}')
    run.mkdir(parents=True); metadata={'configuration':config,'dataset_state':args.dataset_state,'fault_task_arn':args.fault_task_arn,'git_commit':command(['git','-C',str(ROOT),'rev-parse','HEAD']).strip(),'k6_version':command(['k6','version']).strip(),'script_sha256':hashlib.sha256((HERE/'availability.js').read_bytes()).hexdigest(),'config':json.loads((HERE/'config.json').read_text())}
    series_metadata=folder/'metadata.json'
    if series_metadata.exists():
        previous=json.loads(series_metadata.read_text())
        for key in ['configuration','k6_version','script_sha256','config']:
            if previous.get(key)!=metadata[key]: raise RuntimeError(f'Cambió {key}; usar otra serie para conservar comparabilidad')
    else: save(series_metadata,metadata)
    save(run/'metadata.json',metadata)
    before,issues=initial_check(config);save(run/'before.json',before)
    if issues: save(run/'execution.json',{'status':'precondition_failed','issues':issues});raise RuntimeError('; '.join(issues))
    timeline=[]; stop=threading.Event()
    def monitor():
        while not stop.is_set(): timeline.append(observe(config)); stop.wait(metadata['config']['poll_seconds'])
    worker=threading.Thread(target=monitor,daemon=True);worker.start(); env=dict(os.environ,BASE_URL=entry_url,RUN_ID=f'{args.series}-{args.repetition}',SUMMARY_PATH=str(run/'summary.json'))
    started=dt.datetime.now(dt.timezone.utc).isoformat()
    with (run/'console.log').open('w') as log:
        k6=subprocess.Popen(['k6','run','-e',f'BASE_URL={env["BASE_URL"]}',
                             '-e',f'RUN_ID={env["RUN_ID"]}', '-e',f'SUMMARY_PATH={env["SUMMARY_PATH"]}',
                             'availability.js'],cwd=HERE,env=env,stdout=log,stderr=subprocess.STDOUT)
    time.sleep(metadata['config']['baseline_seconds']); t0=dt.datetime.now(dt.timezone.utc).isoformat(); stop_result=aws('ecs','stop-task','--cluster',config['cluster'],'--task',args.fault_task_arn,'--reason','EXP-DIS-01: prueba controlada de disponibilidad')
    k6.wait(); ended=dt.datetime.now(dt.timezone.utc).isoformat(); timeline.append(observe(config)); stop.set();worker.join(timeout=10)
    t1=next((x['timestamp'] for x in timeline if x['timestamp']>=t0 and healthy_two(x,config)),None); save(run/'timeline.json',timeline); save(run/'stop-task.json',stop_result); save(run/'execution.json',{'start':started,'t0':t0,'t1':t1,'end':ended,'rto_seconds':(dt.datetime.fromisoformat(t1)-dt.datetime.fromisoformat(t0)).total_seconds() if t1 else None,'exit_code':k6.returncode}); save(run/'after.json',observe(config))
    if k6.returncode not in (0,99) or not (run/'summary.json').exists(): raise RuntimeError('k6 no produjo una medición válida')
if __name__=='__main__': main()
