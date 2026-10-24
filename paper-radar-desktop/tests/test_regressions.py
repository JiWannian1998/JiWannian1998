import copy,json,sys,tempfile,unittest
from datetime import date
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import engine as E
CAT=json.loads((Path(__file__).resolve().parents[1]/'catalog.json').read_text(encoding='utf-8'))
SRC=next(s for s in CAT if s['id']=='aer')
def fixture(i):
 return {'DOI':f'10.1257/aer.fixture{i}','title':[f'Explicit unit-test fixture number {i}'],'ISSN':['0002-8282'],'type':'journal-article','published':{'date-parts':[[2026,9,1]]}}
class Regressions(unittest.TestCase):
 def test_evidence_budget_does_not_starve_AEA(self):
  targets={('NBER Digest',f'https://www.nber.org/digest/202610/item-{i}') for i in range(100)}|{('AEA',f'https://www.aeaweb.org/research/paper-{i}') for i in range(3)}
  sample=E.evidence_sample(targets,6);self.assertEqual(sum(x[0]=='AEA' for x in sample),3);self.assertEqual(len(sample),6)
 def test_evidence_budget_small_source_preserved(self):
  t={('A','https://a.org/one')}|{('B',f'https://b.org/{i}') for i in range(100)};self.assertIn(('A','https://a.org/one'),E.evidence_sample(t,20))
 def test_cursor_query_has_no_incompatible_sort(self):
  outer=self
  class Fake:
   def check(self):pass
   def json(self,url,params):
    outer.assertNotIn('sort',params);outer.assertNotIn('order',params);outer.assertEqual(params['cursor'],'*');return {'message':{'items':[fixture(1)],'total-results':1}},{'fetched_at':E.stamp()}
  papers,reports=E.crossref(Fake(),SRC,date(2026,1,1),date(2026,10,24));self.assertEqual(len(papers),1);self.assertTrue(reports[0]['complete_index'])
 def test_constant_cursor_with_different_pages_is_valid(self):
  class Fake:
   def __init__(self):self.i=0
   def check(self):pass
   def json(self,url,params):
    self.i+=1;items=[fixture(i) for i in range(200)] if self.i==1 else [fixture(200)]
    return {'message':{'items':items,'total-results':201,'next-cursor':'constant-token'}},{'fetched_at':E.stamp()}
  papers,reports=E.crossref(Fake(),SRC,date(2026,1,1),date(2026,10,24));self.assertEqual(len(papers),201);self.assertTrue(reports[0]['complete_index'])
 def test_english_economic_geography_not_chinese_alias(self):self.assertEqual(E.catalog_aliases(CAT)[E.norm('Economic Geography')]['id'],'eg')
 def test_chinese_alias_is_chinese_in_cnki(self):self.assertEqual(E.catalog_aliases(CAT,True)[E.norm('Economic Geography')]['id'],'jjdl')
 def test_refworks_multiple_records(self):
  s='RT Journal Article\nSR 1\nT1 测试文献一的题名\nA1 测试作者\nJF 世界经济\nYR 2026\nFD 2026-09-10\nUL https://example.org/one\n\nRT Journal Article\nSR 2\nT1 测试文献二的题名\nJF 世界经济\nYR 2026\nFD 2026-08-10\nUL https://example.org/two\n';self.assertEqual(len(E.parse_reference_import(s,CAT)),2)
 def test_store_handle_released_on_exit(self):
  with tempfile.TemporaryDirectory() as t:
   store=E.Store(t);store.save_setting('x',1);self.assertEqual(store.setting('x'),1);target=store.path.with_suffix('.backup');store.path.rename(target);self.assertTrue(target.exists())
if __name__=='__main__':unittest.main(verbosity=2)
