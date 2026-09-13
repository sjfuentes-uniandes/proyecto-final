"""Captura verificable de la política real; ninguna mutación AWS."""
def capture(aws, config):
    args = ['--service-namespace', 'ecs', '--resource-id', f'service/{config["cluster"]}/cotizacion',
            '--scalable-dimension', 'ecs:service:DesiredCount']
    targets = aws('application-autoscaling', 'describe-scalable-targets', '--service-namespace', 'ecs',
                  '--resource-ids', f'service/{config["cluster"]}/cotizacion')
    policies = aws('application-autoscaling', 'describe-scaling-policies', *args)
    names = [a['AlarmName'] for p in policies.get('ScalingPolicies', []) for a in p.get('Alarms', [])]
    alarms = aws('cloudwatch', 'describe-alarms', '--alarm-names', *names) if names else {}
    expected = config['autoscaling']
    issues = []
    target = targets.get('ScalableTargets', [])
    if len(target) != 1 or target[0]['MinCapacity'] != expected['min_replicas'] or target[0]['MaxCapacity'] != expected['max_replicas']:
        issues.append('Target ausente o límites distintos a Terraform')
    if target and any(target[0].get('SuspendedState', {}).values()):
        issues.append('Escalamiento suspendido')
    cpu = [p for p in policies.get('ScalingPolicies', []) if p.get('TargetTrackingScalingPolicyConfiguration', {}).get('PredefinedMetricSpecification', {}).get('PredefinedMetricType') == 'ECSServiceAverageCPUUtilization']
    if len(cpu) != 1 or cpu[0]['TargetTrackingScalingPolicyConfiguration']['TargetValue'] != expected['cpu_target']:
        issues.append('Política CPU ausente o umbral distinto')
    if not names or len(alarms.get('MetricAlarms', [])) != len(set(names)) or any(not a.get('ActionsEnabled') for a in alarms.get('MetricAlarms', [])):
        issues.append('Alarmas ausentes o acciones deshabilitadas')
    return {'targets': targets, 'policies': policies, 'alarms': alarms, 'issues': issues}
