"""Regresiones sin AWS ni HTTP para las conclusiones y captura de fallos."""
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from summarize import capacity, summarize
from run import snapshot


class ReportingTests(unittest.TestCase):
    def test_no_capacity_is_not_zero(self):
        result = capacity([{'target_rpm': 500, 'passed': False, 'valid_load': True}])
        self.assertIsNone(result['demonstrated_rpm'])
        self.assertEqual(result['boundary'], 'sla_failure')

    def test_dropped_load_is_not_known_capacity_boundary(self):
        result = capacity([{'target_rpm': 500, 'passed': True, 'valid_load': True},
                           {'target_rpm': 1000, 'passed': False, 'valid_load': False}])
        self.assertEqual(result['demonstrated_rpm'], 500)
        self.assertEqual(result['boundary'], 'measurement_incomplete')

    def test_maximum_passed_is_lower_bound(self):
        result = capacity([{'target_rpm': 50000, 'passed': True, 'valid_load': True}])
        self.assertEqual(result['boundary'], 'at_least_maximum_tested')

    def test_unhealthy_snapshot_keeps_task_evidence(self):
        config = {'cluster': 'test', 'task_definitions': {'cotizacion': 'revision'},
                  'image_digests': {'cotizacion': 'digest'}, 'quotation_target_group': 'tg'}
        def fake_aws(*args):
            if args[1] == 'describe-services':
                return {'services': [{'serviceName': 'cotizacion', 'desiredCount': 1, 'runningCount': 1,
                    'pendingCount': 0, 'taskDefinition': 'revision', 'deployments': [{'rolloutState': 'COMPLETED'}]}]}
            if args[1] == 'list-tasks':
                return {'taskArns': ['task-1']}
            if args[1] == 'describe-tasks':
                return {'tasks': [{'taskArn': 'task-1', 'healthStatus': 'UNHEALTHY',
                    'containers': [{'name': 'cotizacion', 'imageDigest': 'digest'}]}]}
            return {'TargetHealthDescriptions': []}
        with patch('run.aws', side_effect=fake_aws):
            result = snapshot(config, 1)
        self.assertFalse(result['healthy'])
        self.assertEqual(result['tasks'][0]['taskArn'], 'task-1')
        self.assertTrue(any('cotizacion: tarea no saludable' in issue for issue in result['issues']))

    def test_complete_series_and_incomplete_history(self):
        with tempfile.TemporaryDirectory() as directory:
            series = Path(directory)
            for replicas in [1, 2, 3]:
                folder = series / f'replicas-{replicas}'
                folder.mkdir()
                profile = {'rates_rpm': [500, 50000]}
                metadata = {'configuration': {'quotation_replicas': replicas}, 'config': profile,
                    'script_sha256': 'same', 'k6_version': 'same', 'source_sha256': {}, 'dataset_state': 'reset'}
                (folder / 'metadata.json').write_text(json.dumps(metadata))
                for repetition in [1, 2, 3]:
                    run = folder / f'run-{repetition}'
                    run.mkdir()
                    stages = [{'target_rpm': rate, 'passed': True, 'valid_load': True,
                        'percentiles': {'p(50)': 100, 'p(90)': 110, 'p(95)': 120, 'p(99)': 130},
                        'error_rate': 0, 'achieved_rpm': rate, 'successful_rpm': rate, 'dropped': 0}
                        for rate in [500, 50000]]
                    (run / 'summary.json').write_text(json.dumps({'replicas': replicas, 'config': profile, 'stages': stages}))
                    (run / 'execution.json').write_text('{"exit_code": 0}')
                    (run / 'before.json').write_text('{"healthy": true}')
                    (run / 'after.json').write_text('{"healthy": false, "issues": ["task unhealthy"]}')
            self.assertEqual(summarize(series), 0)
            report = json.loads((series / 'comparison.json').read_text())
            self.assertEqual(report['objective_50000_rpm_with_3_replicas'], 'cumple_en_tres_repeticiones')
            self.assertEqual(report['scaling_1_to_3'], 'no_se_demuestra_aumento_en_niveles_probados')
            self.assertFalse(report['individual_results'][0]['post_health'])
            (series / 'replicas-1/run-1/after.json').unlink()
            self.assertEqual(summarize(series), 1)
            report = json.loads((series / 'comparison.json').read_text())
            self.assertEqual(len(report['individual_results']), 9)
            self.assertEqual(report['objective_50000_rpm_with_3_replicas'], 'inconcluso')

    def test_autoscaling_report_keeps_unreached_stages_out_of_median(self):
        with tempfile.TemporaryDirectory() as directory:
            series = Path(directory)
            run = series / 'autoscaling' / 'run-1'
            run.mkdir(parents=True)
            stages = [{'target_rpm': 500, 'valid_load': True, 'passed': True,
                       'percentiles': {'p(95)': 200}, 'error_rate': 0},
                      {'target_rpm': 5000, 'valid_load': False, 'passed': False,
                       'percentiles': {}, 'error_rate': None}]
            (run / 'summary.json').write_text(json.dumps({'stages': stages}))
            (run / 'scaling-timeline.jsonl').write_text('\n'.join(json.dumps({'services': [
                {'serviceName': 'cotizacion', 'desiredCount': n, 'runningCount': n}]}) for n in [1, 2, 3]))
            self.assertEqual(summarize(series), 1)
            report = json.loads((series / 'autoscaling-report.json').read_text())
            self.assertEqual(report['runs'][0]['max_running'], 3)
            self.assertIsNone(report['stages'][1]['median_p95_ms'])
            self.assertEqual(report['stages'][1]['complete_repetitions'], 0)

    def test_aws_error_is_preserved(self):
        with patch('run.aws', side_effect=RuntimeError('AccessDenied')):
            result = snapshot({'cluster': 'test', 'quotation_target_group': 'tg'}, 1)
        self.assertIsNone(result['healthy'])
        self.assertEqual(result['status'], 'unverified')
        self.assertEqual(result['issues'], [])
        self.assertTrue(result['collection_errors'])


if __name__ == '__main__':
    unittest.main()
