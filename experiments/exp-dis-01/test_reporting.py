import importlib.util,json,tempfile,unittest
from pathlib import Path
SPEC=importlib.util.spec_from_file_location('summary',Path(__file__).with_name('summarize.py'));MODULE=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(MODULE)
class ReportingTests(unittest.TestCase):
 def test_rto_must_be_present_and_below_limit(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp)
   for i in range(1,4):
    run=root/f'run-{i}';run.mkdir();(run/'execution.json').write_text(json.dumps({'exit_code':0,'rto_seconds':100}));(run/'summary.json').write_text(json.dumps({'config':{'rto_seconds':120},'perturbation':{'valid_load':True,'passed':True,'success_rate':1,'error_rate':0,'percentiles':{'p(95)':1}}}))
   self.assertEqual(MODULE.summarize(root)['hypothesis'],'cumplida')
if __name__=='__main__':unittest.main()
