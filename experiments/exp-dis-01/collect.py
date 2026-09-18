#!/usr/bin/env python3
"""Recoge métricas CloudWatch de EXP-DIS-01, incluida la ventana de recuperación."""
import argparse, datetime as dt, json, os, subprocess
from pathlib import Path
def aws(*args):
 r=subprocess.run(['aws',*args,'--output','json'],text=True,capture_output=True,timeout=120)
 if r.returncode: raise RuntimeError(r.stderr.strip())
 return json.loads(r.stdout)
def collect(run, config):
 execution=json.loads((run/'execution.json').read_text()); specs=[]
 for service in ['cotizacion','consulta','catalogo','simulador']:
  for metric in ['CPUUtilization','MemoryUtilization']: specs.append(('AWS/ECS',metric,{'ClusterName':config['cluster'],'ServiceName':service},'Average'))
 for metric in ['CPUUtilization','DatabaseConnections','ReadLatency','WriteLatency','DiskQueueDepth']: specs.append(('AWS/RDS',metric,{'DBInstanceIdentifier':config['database_identifier']},'Average'))
 target=config['target_groups']['cotizacion']['arn_suffix'];alb=config['alb']['arn_suffix']
 for metric,stat in [('HealthyHostCount','Minimum'),('UnHealthyHostCount','Maximum'),('TargetResponseTime','p95'),('HTTPCode_Target_5XX_Count','Sum')]: specs.append(('AWS/ApplicationELB',metric,{'LoadBalancer':alb,'TargetGroup':target},stat))
 data=[]
 for ns,metric,dims,stat in specs:
  try: point=aws('cloudwatch','get-metric-statistics','--namespace',ns,'--metric-name',metric,'--dimensions',*[f'Name={k},Value={v}' for k,v in dims.items()],'--start-time',execution['start'],'--end-time',execution['end'],'--period','60','--extended-statistics' if stat=='p95' else '--statistics',stat)
  except Exception as error: point={'Datapoints':[],'collection_error':str(error)}
  data.append({'namespace':ns,'metric':metric,'dimensions':dims,'statistic':stat,**point})
 (run/'cloudwatch.json').write_text(json.dumps(data,indent=2)+'\n')
 logs={}
 for name,group in config.get('log_groups',{}).items():
  try: logs[name]=aws('logs','filter-log-events','--log-group-name',group,'--start-time',str(int(dt.datetime.fromisoformat(execution['start']).timestamp()*1000)),'--end-time',str(int(dt.datetime.fromisoformat(execution['end']).timestamp()*1000)))
  except Exception as error: logs[name]={'collection_error':str(error)}
 (run/'logs.json').write_text(json.dumps(logs,indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('series',type=Path);a=p.parse_args()
 for run in sorted(a.series.glob('run-*')):
  if (run/'execution.json').exists() and 'start' in json.loads((run/'execution.json').read_text()):
   config=json.loads((run/'metadata.json').read_text())['configuration'];os.environ.update(AWS_REGION=config['region'],AWS_DEFAULT_REGION=config['region'],AWS_PAGER='');collect(run,config)
