import importlib.util, json, tempfile, unittest
from pathlib import Path
SPEC=importlib.util.spec_from_file_location('summary',Path(__file__).with_name('summarize.py'));MODULE=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(MODULE)
class ReportingTests(unittest.TestCase):
 def test_requires_three_valid_runs(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp)
   for i in range(1,4):
    run=root/f'run-{i}';run.mkdir();(run/'execution.json').write_text(json.dumps({'exit_code':0}))
    endpoints={name:{'valid_load':True,'passed':True,'error_rate':0,'percentiles':{'p(50)':1,'p(90)':2,'p(95)':3,'p(99)':4}} for name in ['cotizacion','consulta']}
    (run/'summary.json').write_text(json.dumps({'endpoints':endpoints}))
   self.assertEqual(MODULE.summarize(root)['hypothesis'],'cumplida')
if __name__=='__main__': unittest.main()
