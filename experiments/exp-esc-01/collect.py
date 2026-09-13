#!/usr/bin/env python3
"""Descarga métricas CloudWatch para las ventanas ya medidas (solo lectura)."""
import argparse
import json
from pathlib import Path
import os
import datetime as dt
from run import aws, save


def collect(run, config):
    execution = json.loads((run / 'execution.json').read_text())
    target = config['quotation_target_group']
    tg = aws('elbv2', 'describe-target-groups', '--target-group-arns', target)['TargetGroups'][0]
    alb = tg['LoadBalancerArns'][0].split('loadbalancer/')[1]
    target_suffix = 'targetgroup/' + target.split('targetgroup/')[1]
    cluster = config['cluster']
    specs = []
    for service in ['cotizacion', 'consulta', 'catalogo', 'simulador']:
        for metric in ['CPUUtilization', 'MemoryUtilization']:
            specs.append(('AWS/ECS', metric, {'ClusterName': cluster, 'ServiceName': service}, 'Average'))
    for metric in ['CPUUtilization', 'DatabaseConnections', 'FreeableMemory', 'ReadLatency', 'WriteLatency', 'DiskQueueDepth', 'CPUCreditBalance']:
        specs.append(('AWS/RDS', metric, {'DBInstanceIdentifier': config.get('database_identifier', cluster)}, 'Average'))
    dims = {'LoadBalancer': alb, 'TargetGroup': target_suffix}
    for metric, stat in [('HealthyHostCount', 'Minimum'), ('RequestCount', 'Sum'),
                         ('HTTPCode_Target_5XX_Count', 'Sum'), ('TargetResponseTime', 'p95')]:
        specs.append(('AWS/ApplicationELB', metric, dims, stat))
    for metric in ['TargetConnectionErrorCount', 'HTTPCode_ELB_5XX_Count']:
        specs.append(('AWS/ApplicationELB', metric, {'LoadBalancer': alb}, 'Sum'))
    specs.append(('AWS/ApplicationELB', 'UnHealthyHostCount', dims, 'Maximum'))
    for service in ['cotizacion', 'consulta', 'catalogo', 'simulador']:
        specs.append(('AWS/ECS', 'CPUUtilization', {'ClusterName': cluster, 'ServiceName': service}, 'Maximum'))
    if config.get('api_id'):
        for metric, stat in [('Latency', 'p95'), ('IntegrationLatency', 'p95'), ('Count', 'SampleCount'), ('5xx', 'Sum'), ('4xx', 'Sum')]:
            specs.append(('AWS/ApiGateway', metric, {'ApiId': config['api_id']}, stat))
    data = []
    for namespace, metric, dimensions, statistic in specs:
        try:
            points = aws('cloudwatch', 'get-metric-statistics', '--namespace', namespace,
            '--metric-name', metric, '--dimensions',
            *[f'Name={k},Value={v}' for k, v in dimensions.items()],
            '--start-time', execution['start'], '--end-time', execution['end'],
            '--period', '60', '--extended-statistics' if statistic == 'p95' else '--statistics', statistic)
        except Exception as error:
            points = {'Datapoints': [], 'collection_error': str(error)}
        data.append({'namespace': namespace, 'metric': metric, 'dimensions': dimensions,
                     'statistic': statistic, **points})
    save(run / 'cloudwatch.json', data)
    # Guardar también margen de recuperación sin alterar la ventana de métricas de carga.
    from scaling_evidence import capture
    try:
        evidence = capture(aws, config)
        save(run / 'scaling-after-collection.json', evidence)
        end = (dt.datetime.fromisoformat(execution['end']) + dt.timedelta(minutes=15)).isoformat()
        for index, alarm in enumerate(evidence['alarms'].get('MetricAlarms', [])):
            history = aws('cloudwatch', 'describe-alarm-history', '--alarm-name', alarm['AlarmName'],
                          '--start-date', execution['start'], '--end-date', end)
            save(run / f'alarm-history-{index}.json', {'alarm_name': alarm['AlarmName'], **history})
        save(run / 'scaling-activities-collected.json', aws('application-autoscaling', 'describe-scaling-activities',
            '--service-namespace', 'ecs', '--resource-id', f'service/{cluster}/cotizacion',
            '--scalable-dimension', 'ecs:service:DesiredCount'))
    except Exception as error:
        save(run / 'scaling-collection-error.json', {'error': str(error)})
    print(run, 'métricas guardadas; series vacías:', sum(not m['Datapoints'] for m in data))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('series', type=Path)
    args = parser.parse_args()
    for metadata in sorted(args.series.glob('*/metadata.json')):
        config = json.loads(metadata.read_text())['configuration']
        os.environ.update(AWS_REGION=config['region'], AWS_DEFAULT_REGION=config['region'], AWS_PAGER='')
        for run in sorted(metadata.parent.glob('run-*')):
            if (run / 'execution.json').exists() and 'start' in json.loads((run / 'execution.json').read_text()):
                collect(run, config)
