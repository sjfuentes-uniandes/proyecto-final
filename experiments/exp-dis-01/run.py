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
    outputs=json.loads(command(['terraform','-chdir='+str(ROOT/'infra/services'),'output','-json'])); config=outputs['experiment_configuration']['value']
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
    worker=threading.Thread(target=monitor,daemon=True);worker.start(); env=dict(os.environ,BASE_URL=outputs['entry_url']['value'],RUN_ID=f'{args.series}-{args.repetition}',SUMMARY_PATH=str(run/'summary.json'))
    started=dt.datetime.now(dt.timezone.utc).isoformat()
    with (run/'console.log').open('w') as log: k6=subprocess.Popen(['k6','run','availability.js'],cwd=HERE,env=env,stdout=log,stderr=subprocess.STDOUT)
    time.sleep(metadata['config']['baseline_seconds']); t0=dt.datetime.now(dt.timezone.utc).isoformat(); stop_result=aws('ecs','stop-task','--cluster',config['cluster'],'--task',args.fault_task_arn,'--reason','EXP-DIS-01: prueba controlada de disponibilidad')
    k6.wait(); ended=dt.datetime.now(dt.timezone.utc).isoformat(); timeline.append(observe(config)); stop.set();worker.join(timeout=10)
    t1=next((x['timestamp'] for x in timeline if x['timestamp']>=t0 and healthy_two(x,config)),None); save(run/'timeline.json',timeline); save(run/'stop-task.json',stop_result); save(run/'execution.json',{'start':started,'t0':t0,'t1':t1,'end':ended,'rto_seconds':(dt.datetime.fromisoformat(t1)-dt.datetime.fromisoformat(t0)).total_seconds() if t1 else None,'exit_code':k6.returncode}); save(run/'after.json',observe(config))
    if k6.returncode not in (0,99) or not (run/'summary.json').exists(): raise RuntimeError('k6 no produjo una medición válida')
if __name__=='__main__': main()
