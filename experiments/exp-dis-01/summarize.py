#!/usr/bin/env python3
"""Consolida EXP-DIS-01: disponibilidad, p95 de perturbación y RTO."""
import argparse, json
from pathlib import Path
from statistics import median
def med(values): return median(values) if len(values)==3 and all(isinstance(v,(int,float)) for v in values) else None
def summarize(series):
 runs=[];missing=[]
 for i in range(1,4):
  run=series/f'run-{i}'
  if not (run/'summary.json').exists() or not (run/'execution.json').exists(): missing.append(f'run-{i}');continue
  execution=json.loads((run/'execution.json').read_text());summary=json.loads((run/'summary.json').read_text())
  if execution.get('exit_code') not in (0,99) or execution.get('rto_seconds') is None: missing.append(f'run-{i}: ejecución/RTO incompleto');continue
  p=summary['perturbation'];runs.append({'run':i,'success_rate':p.get('success_rate'),'p95_ms':p.get('percentiles',{}).get('p(95)'),'error_rate':p.get('error_rate'),'valid_load':p.get('valid_load'),'load_passed':p.get('passed'),'rto_seconds':execution['rto_seconds'],'rto_passed':execution['rto_seconds']<=summary['config']['rto_seconds']})
 complete=len(runs)==3 and all(r['valid_load'] for r in runs)
 passed=complete and all(r['load_passed'] and r['rto_passed'] for r in runs)
 report={'experiment':'EXP-DIS-01','runs_found':len(runs),'missing_evidence':missing,'individual_results':runs,'median_success_rate':med([r['success_rate'] for r in runs]),'median_p95_ms':med([r['p95_ms'] for r in runs]),'median_error_rate':med([r['error_rate'] for r in runs]),'median_rto_seconds':med([r['rto_seconds'] for r in runs]),'hypothesis':'cumplida' if not missing and passed else 'no_cumplida_o_inconclusa'}
 (series/'report.json').write_text(json.dumps(report,indent=2)+'\n');lines=['# EXP-DIS-01','',f"Hipótesis: **{report['hypothesis']}**.",'','| Corrida | Éxito | p95 perturbación (ms) | Error | RTO (s) | Aprobada |','| --- | ---: | ---: | ---: | ---: | --- |']
 for r in runs: lines.append(f"| {r['run']} | {r['success_rate']} | {r['p95_ms']} | {r['error_rate']} | {r['rto_seconds']} | {r['load_passed'] and r['rto_passed']} |")
 lines.extend(['',f"Medianas: éxito={report['median_success_rate']}, p95={report['median_p95_ms']} ms, RTO={report['median_rto_seconds']} s."])
 if missing: lines.append('Evidencia incompleta: '+', '.join(missing))
 (series/'report.md').write_text('\n'.join(lines)+'\n');return report
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('series',type=Path);print(summarize(p.parse_args().series)['hypothesis'])
