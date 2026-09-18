#!/usr/bin/env python3
"""Recoge métricas CloudWatch de las ventanas de EXP-LAT-01 (solo lectura)."""
import argparse, datetime as dt, json, os, subprocess
from pathlib import Path
def aws(*args):
    r=subprocess.run(['aws',*args,'--output','json'],text=True,capture_output=True,timeout=120)
    if r.returncode: raise RuntimeError(r.stderr.strip())
    return json.loads(r.stdout)
def collect(run, config):
    execution=json.loads((run/'execution.json').read_text()); start,end=execution['start'],execution['end']; specs=[]
    for service in ['cotizacion','consulta','catalogo','simulador']:
        for metric in ['CPUUtilization','MemoryUtilization']: specs.append(('AWS/ECS',metric,{'ClusterName':config['cluster'],'ServiceName':service},'Average'))
    for metric in ['CPUUtilization','DatabaseConnections','ReadLatency','WriteLatency','DiskQueueDepth']: specs.append(('AWS/RDS',metric,{'DBInstanceIdentifier':config['database_identifier']},'Average'))
    if config.get('api_id'):
        for metric,stat in [('Latency','p95'),('IntegrationLatency','p95'),('5xx','Sum'),('4xx','Sum')]: specs.append(('AWS/ApiGateway',metric,{'ApiId':config['api_id']},stat))
    records=[]
    for namespace,metric,dims,stat in specs:
        try: value=aws('cloudwatch','get-metric-statistics','--namespace',namespace,'--metric-name',metric,'--dimensions',*[f'Name={k},Value={v}' for k,v in dims.items()],'--start-time',start,'--end-time',end,'--period','60','--extended-statistics' if stat=='p95' else '--statistics',stat)
        except Exception as error: value={'Datapoints':[],'collection_error':str(error)}
        records.append({'namespace':namespace,'metric':metric,'dimensions':dims,'statistic':stat,**value})
    (run/'cloudwatch.json').write_text(json.dumps(records,indent=2)+'\n')
    logs = {}
    for name, group in config.get('log_groups', {}).items():
        try:
            logs[name] = aws('logs', 'filter-log-events', '--log-group-name', group,
                             '--start-time', str(int(dt.datetime.fromisoformat(start).timestamp() * 1000)),
                             '--end-time', str(int(dt.datetime.fromisoformat(end).timestamp() * 1000)))
        except Exception as error: logs[name] = {'collection_error': str(error)}
    (run/'logs.json').write_text(json.dumps(logs,indent=2)+'\n')
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('series',type=Path);args=parser.parse_args()
    for run in sorted(args.series.glob('run-*')):
        if (run/'execution.json').exists() and 'start' in json.loads((run/'execution.json').read_text()):
            config=json.loads((run/'metadata.json').read_text())['configuration'];os.environ.update(AWS_REGION=config['region'],AWS_DEFAULT_REGION=config['region'],AWS_PAGER='');collect(run,config)
