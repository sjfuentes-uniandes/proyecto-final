#!/usr/bin/env python3
"""Consolida tres repeticiones de EXP-LAT-01 sin ocultar evidencia incompleta."""
import argparse, json
from pathlib import Path
from statistics import median
def med(values): return median(values) if len(values)==3 and all(isinstance(v,(int,float)) for v in values) else None
def summarize(series):
    runs=[]; missing=[]
    for number in range(1,4):
        run=series/f'run-{number}'; summary=run/'summary.json'; execution=run/'execution.json'
        if not summary.exists() or not execution.exists(): missing.append(f'run-{number}');continue
        if json.loads(execution.read_text()).get('exit_code') not in (0,99): missing.append(f'run-{number}: ejecución inválida');continue
        runs.append({'run':number,**json.loads(summary.read_text())})
    endpoints={}
    for endpoint in ['cotizacion','consulta']:
        values=[run['endpoints'].get(endpoint,{}) for run in runs]; complete=len(values)==3 and all(v.get('valid_load') for v in values)
        endpoints[endpoint]={'individual':values,'median_p50_ms':med([v.get('percentiles',{}).get('p(50)') for v in values]),'median_p90_ms':med([v.get('percentiles',{}).get('p(90)') for v in values]),'median_p95_ms':med([v.get('percentiles',{}).get('p(95)') for v in values]),'median_p99_ms':med([v.get('percentiles',{}).get('p(99)') for v in values]),'median_error_rate':med([v.get('error_rate') for v in values]),'all_passed':complete and all(v.get('passed') for v in values)}
    report={'experiment':'EXP-LAT-01','runs_found':len(runs),'missing_evidence':missing,'endpoints':endpoints,'hypothesis':'cumplida' if not missing and all(v['all_passed'] for v in endpoints.values()) else 'no_cumplida_o_inconclusa'}
    (series/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    lines=['# EXP-LAT-01','',f"Hipótesis: **{report['hypothesis']}**.",'','| Endpoint | p50 mediana | p90 mediana | p95 mediana | p99 mediana | Error mediano | 3 corridas aprueban |','| --- | ---: | ---: | ---: | ---: | ---: | --- |']
    for name,value in endpoints.items(): lines.append(f"| {name} | {value['median_p50_ms']} | {value['median_p90_ms']} | {value['median_p95_ms']} | {value['median_p99_ms']} | {value['median_error_rate']} | {value['all_passed']} |")
    if missing: lines.extend(['','Evidencia incompleta: '+', '.join(missing)])
    (series/'report.md').write_text('\n'.join(lines)+'\n'); return report
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('series',type=Path);print(summarize(parser.parse_args().series)['hypothesis'])
