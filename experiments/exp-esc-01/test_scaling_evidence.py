import unittest
from scaling_evidence import capture

class ScalingEvidenceTests(unittest.TestCase):
    def test_missing_policy_blocks_run_despite_enabled_output(self):
        result = capture(lambda *args: {}, {'cluster': 'test', 'autoscaling': {
            'min_replicas': 1, 'max_replicas': 3, 'cpu_target': 35}})
        self.assertEqual(len(result['issues']), 3)

    def test_matching_live_policy(self):
        def aws(*args):
            if args[1] == 'describe-scalable-targets':
                return {'ScalableTargets': [{'MinCapacity': 1, 'MaxCapacity': 3}]}
            if args[1] == 'describe-scaling-policies':
                return {'ScalingPolicies': [{'TargetTrackingScalingPolicyConfiguration': {
                    'TargetValue': 35, 'PredefinedMetricSpecification': {'PredefinedMetricType': 'ECSServiceAverageCPUUtilization'}},
                    'Alarms': [{'AlarmName': 'high'}, {'AlarmName': 'low'}]}]}
            return {'MetricAlarms': [{'ActionsEnabled': True}, {'ActionsEnabled': True}]}
        self.assertEqual(capture(aws, {'cluster': 'test', 'autoscaling': {
            'min_replicas': 1, 'max_replicas': 3, 'cpu_target': 35}})['issues'], [])
