#!/usr/bin/env python3
"""Comprobación secuencial del despliegue. Crea tres cotizaciones sintéticas."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[2]


def cli(*args):
    return json.loads(subprocess.check_output(args, text=True, timeout=60))


class Suite:
    def __init__(self, url):
        self.url = url.rstrip('/')
        self.results = []
        self.requests = []

    def test(self, name, fn):
        try:
            fn()
            result = {'name': name, 'status': 'PASS'}
        except Exception as error:
            result = {'name': name, 'status': 'FAIL', 'detail': str(error)}
        self.results.append(result)
        print(f"{result['status']}: {name}" + (f" — {result['detail']}" if 'detail' in result else ''), flush=True)

    def request(self, path, expected, body=None, method=None, base=None):
        data = None if body is None else json.dumps(body).encode()
        req = Request((base or self.url) + path, data=data, method=method,
                      headers={'Content-Type': 'application/json', 'X-Correlation-Id': f'smoke-{uuid4()}'})
        start = time.perf_counter()
        try:
            response = urlopen(req, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            status = response.status
            correlation = response.headers.get('X-Correlation-Id')
        self.requests.append({'path': path, 'status': status, 'correlation_id': correlation,
                              'duration_ms': round((time.perf_counter() - start) * 1000, 2)})
        assert status == expected, f'{path}: HTTP {status}, esperado {expected}; {raw[:200]!r}'
        return json.loads(raw), correlation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', help='Por defecto: output entry_url de infra/services')
    parser.add_argument('--http-only', action='store_true', help='Solo HTTP; no certifica estado ECS ni logs internos')
    parser.add_argument('--catalog-url', help='Opcional: URL de catálogo accesible desde este equipo')
    parser.add_argument('--simulator-url', help='Opcional: URL del simulador accesible desde este equipo')
    parser.add_argument('--log-wait-seconds', type=int, default=60)
    args = parser.parse_args()
    outputs = None
    if not args.http_only or not args.base_url:
        outputs = cli('terraform', '-chdir=' + str(ROOT / 'infra/services'), 'output', '-json')
    suite = Suite(args.base_url or outputs['entry_url']['value'])
    start_ms = int(time.time() * 1000)
    report_dir = ROOT / 'tests/smoke/results' / dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    report_dir.mkdir(parents=True)
    config = None
    inventory = []
    if not args.http_only:
        config = outputs['experiment_configuration']['value']
        os.environ.update(AWS_REGION=config['region'], AWS_DEFAULT_REGION=config['region'], AWS_PAGER='')

        def aws(*arguments):
            return cli('aws', *arguments, '--output', 'json')

        def ecs_check(service):
            result = aws('ecs', 'describe-services', '--cluster', config['cluster'], '--services', service)
            assert not result.get('failures') and len(result['services']) == 1, 'Servicio no encontrado'
            item = result['services'][0]
            expected = config['quotation_replicas'] if service == 'cotizacion' else 1
            assert (item['desiredCount'], item['runningCount'], item['pendingCount']) == (expected, expected, 0), 'Número de tareas no estable'
            assert len(item['deployments']) == 1 and item['deployments'][0].get('rolloutState') == 'COMPLETED', 'Despliegue no completado'
            assert item['taskDefinition'] == config['task_definitions'][service], 'Revisión diferente a Terraform'
            arns = aws('ecs', 'list-tasks', '--cluster', config['cluster'], '--service-name', service)['taskArns']
            assert len(arns) == expected, 'Tareas encontradas distintas a las esperadas'
            tasks = aws('ecs', 'describe-tasks', '--cluster', config['cluster'], '--tasks', *arns)
            assert not tasks.get('failures'), 'Error al consultar tareas'
            for task in tasks['tasks']:
                container = next(c for c in task['containers'] if c['name'] == service)
                inventory.append({'service': service, 'task_arn': task['taskArn'], 'health': task.get('healthStatus'),
                                  'image_digest': container.get('imageDigest')})
                assert task.get('healthStatus') == 'HEALTHY', 'Health check del contenedor no saludable'
                assert container.get('imageDigest') == config['image_digests'][service], 'Digest ejecutado diferente al esperado'
            for lb in item.get('loadBalancers', []):
                targets = aws('elbv2', 'describe-target-health', '--target-group-arn', lb['targetGroupArn'])['TargetHealthDescriptions']
                assert len(targets) == expected and all(t['TargetHealth']['State'] == 'healthy' for t in targets), 'Destinos ALB no saludables'
        for service in ['catalogo', 'simulador', 'consulta', 'cotizacion']:
            suite.test(f'ECS, digest y salud: {service}', lambda service=service: ecs_check(service))

    def policy(policy_id, path):
        body, correlation = suite.request(path, 200)
        assert body == {'id': policy_id, 'dataset': 'synthetic-v1', 'status': 'synthetic', 'coverage': 'test-only'}, 'Proyección incorrecta'
        assert correlation, 'Falta correlación en la respuesta'
    suite.test('Consulta por defecto', lambda: policy('poliza-000001', '/consultas'))
    for number in [1, 42, 1000]:
        policy_id = f'poliza-{number:06d}'
        suite.test(f'Consulta {policy_id}', lambda pid=policy_id: policy(pid, '/consultas/' + pid))
    suite.test('Póliza inexistente devuelve 404', lambda: suite.request('/consultas/no-existe-' + str(uuid4()), 404))
    suite.test('Cotización inexistente devuelve 404', lambda: suite.request('/cotizaciones/' + str(uuid4()), 404))
    suite.test('Producto vacío devuelve 422', lambda: suite.request('/cotizaciones', 422, {'product_id': ''}))
    suite.test('Producto demasiado largo devuelve 422', lambda: suite.request('/cotizaciones', 422, {'product_id': 'x' * 65}))
    suite.test('Método de cotización no soportado devuelve 405', lambda: suite.request('/cotizaciones', 405))
    suite.test('Ruta no publicada devuelve 404', lambda: suite.request('/ruta-inexistente', 404))
    quotes = []
    correlations = []

    def quotation(body):
        payload, correlation = suite.request('/cotizaciones', 201, body)
        UUID(payload['id'])
        assert payload['id'] not in quotes, 'ID duplicado'
        assert payload['product_id'] == 'producto-sintetico', 'Producto distinto'
        assert payload['dataset'] == payload['rules_version'] == 'synthetic-v1', 'Versión de catálogo incorrecta'
        assert payload['result'] == 'synthetic', 'Resultado incorrecto'
        assert payload['source'] == {'source': 'synthetic', 'value': 'ok', 'configured_delay_ms': 50}, 'Respuesta del simulador incorrecta'
        assert correlation, 'Falta correlación'
        quotes.append(payload['id'])
        correlations.append(correlation)
        read, _ = suite.request('/cotizaciones/' + payload['id'], 200)
        assert read == payload, 'La lectura persistida no coincide con el POST'
    for number, body in enumerate([{'product_id': 'producto-sintetico'}, {}, {'product_id': 'producto-sintetico'}], 1):
        suite.test(f'Cotización {number}: catálogo, simulador, UUID y persistencia', lambda body=body: quotation(body))

    if args.catalog_url:
        def direct_catalog():
            suite.request('/health', 200, base=args.catalog_url.rstrip('/'))
            body, _ = suite.request('/catalogo', 200, base=args.catalog_url.rstrip('/'))
            assert body == {'version': 'synthetic-v1', 'products': ['producto-sintetico'],
                            'rules': {'mode': 'synthetic-no-business-logic'}}, 'Catálogo incorrecto'
        suite.test('Catálogo directo: health y datos', direct_catalog)
    if args.simulator_url:
        def direct_source():
            suite.request('/health', 200, base=args.simulator_url.rstrip('/'))
            body, _ = suite.request('/fuente', 200, base=args.simulator_url.rstrip('/'))
            assert body == {'source': 'synthetic', 'value': 'ok', 'configured_delay_ms': 50}, 'Simulador incorrecto'
        suite.test('Simulador directo: health y contrato', direct_source)

    if config:
        def logs_check():
            assert correlations, 'No hubo cotizaciones exitosas para verificar trazas'
            deadline = time.monotonic() + max(0, args.log_wait_seconds)
            found = {}
            while True:
                for service in ['cotizacion', 'simulador']:
                    result = aws('logs', 'filter-log-events', '--log-group-name', f"/ecs/{config['cluster']}/{service}",
                                 '--start-time', str(start_ms), '--filter-pattern', f'{{ $.correlation_id = "{correlations[0]}" }}')
                    events = []
                    for event in result['events']:
                        try:
                            item = json.loads(event['message'])
                        except ValueError:
                            continue
                        if item.get('event') == 'request' and item.get('path') == ('/cotizaciones' if service == 'cotizacion' else '/fuente'):
                            events.append(item)
                    if events:
                        found[service] = events
                if len(found) == 2 or time.monotonic() >= deadline:
                    break
                time.sleep(min(5, max(0, deadline - time.monotonic())))
            (report_dir / 'correlated-logs.json').write_text(json.dumps(found, indent=2))
            assert len(found) == 2, 'No llegaron logs correlacionados de cotización y simulador; revisar permisos/ingestión'
            assert any(e.get('status') == 201 and 'postgresql' in e.get('dependencies_ms', {})
                       and 'simulador' in e.get('dependencies_ms', {}) for e in found['cotizacion']), 'Faltan tiempos de dependencias'
            assert any(e.get('status') == 200 and e.get('duration_ms', 0) >= 45 for e in found['simulador']), 'La espera del simulador no aparece en sus logs'
        suite.test('Correlación real y demora del simulador en CloudWatch', logs_check)

    failed = sum(r['status'] == 'FAIL' for r in suite.results)
    report = {'base_url': suite.url, 'results': suite.results, 'requests': suite.requests,
              'inventory': inventory, 'created_quote_ids': quotes, 'failed': failed,
              'scope': 'http-only' if args.http_only else 'aws-and-http',
              'limitations': ['No se detienen tareas ni se comprueba recuperación',
                              'No mide umbrales de carga',
                              'Catálogo se verifica por salud ECS y versión integrada salvo URL directa']}
    (report_dir / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f"{len(suite.results) - failed}/{len(suite.results)} comprobaciones correctas. Evidencia: {report_dir}")
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
