import copy,csv,io,json,sys,tempfile,unittest
from datetime import date
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import engine as E
CAT=json.loads((Path(__file__).resolve().parents[1]/'catalog.json').read_text(encoding='utf-8'));SRC=next(s for s in CAT if s['id']=='aer')
# Synthetic fixtures ONLY for unit tests, never application results.
FIX={'DOI':'10.1257/aer.test','title':['Fixture: a test research article'],'ISSN':['0002-8282'],'type':'journal-article','published-online':{'date-parts':[[2026,9,1]]},'published-print':{'date-parts':[[2026,10,1]]},'author':[{'given':'Test','family':'Author'}],'abstract':'A randomized field experiment.','is-referenced-by-count':2}
class Core(unittest.TestCase):
 def test_week(self):self.assertEqual(E.window_start(date(2026,10,24),'7d'),date(2026,10,18))
 def test_month(self):self.assertEqual(E.window_start(date(2026,10,24),'30d'),date(2026,9,25))
 def test_six_calendar_months(self):self.assertEqual(E.window_start(date(2026,10,24),'6m'),date(2026,4,25))
 def test_year(self):self.assertEqual(E.window_start(date(2026,10,24),'1y'),date(2025,10,25))
 def test_invalid_date(self):self.assertIsNone(E.interval('2026-02-30'))
 def test_month_precision(self):self.assertEqual(E.interval('2026-02'),(date(2026,2,1),date(2026,2,28)))
 def test_coarse_excluded(self):self.assertFalse(E.in_window('2026',date(2026,10,1),date(2026,10,24)))
 def test_coarse_flag(self):self.assertTrue(E.in_window('2026',date(2026,10,1),date(2026,10,24),True))
 def test_nonresearch(self):self.assertFalse(E.is_research('Front Matter'));self.assertFalse(E.is_research('经济学新书评介'))
 def test_real_research(self):self.assertTrue(E.is_research('Conservation Priorities and Environmental Offsets'))
 def test_doi_norm(self):self.assertEqual(E.doi_norm('https://doi.org/10.1257/AER.TEST'),'10.1257/aer.test')
 def test_parse(self):self.assertEqual(E.parse_crossref(FIX,SRC)['date'],'2026-09-01')
 def test_multiple_dates(self):self.assertEqual(len(E.parse_crossref(FIX,SRC)['dates']),2)
 def test_exact_source(self):bad=copy.deepcopy(FIX);bad['ISSN']=['1111-2222'];self.assertIsNone(E.parse_crossref(bad,SRC))
 def test_nber_prefix_restricted(self):s=next(s for s in CAT if s['id']=='nber');bad=copy.deepcopy(FIX);bad['DOI']='10.3386/chap.test';self.assertIsNone(E.parse_crossref(bad,s))
 def test_no_count_data_claim(self):p=E.parse_crossref(FIX,SRC);self.assertEqual(p['evidence'],[])
 def test_methods(self):self.assertIn('随机实验',E.methods('','randomized field experiment'))
 def test_qualitative(self):self.assertIn('访谈/田野',E.methods('','ethnography and process tracing'))
 def test_safe_links(self):self.assertFalse(E.safe_url('javascript:alert(1)'));self.assertFalse(E.safe_url('file:///C:/x'))
 def test_dedup(self):p=E.parse_crossref(FIX,SRC);self.assertEqual(len(E.dedup([p,p])),1)
 def test_unknown_citations_not_zero(self):x=copy.deepcopy(FIX);del x['is-referenced-by-count'];self.assertIsNone(E.parse_crossref(x,SRC)['citations'])
 def test_filters(self):p=E.parse_crossref(FIX,SRC);q={'sources':['aer'],'end':'2026-10-24','window':'1y'};self.assertEqual(len(E.filter_papers([p],q)[0]),1)
 def test_other_sources_excluded(self):p=E.parse_crossref(FIX,SRC);self.assertEqual(E.filter_papers([p],{'sources':['qje'],'end':'2026-10-24'})[0],[])
 def test_att_requires_evidence(self):p=E.parse_crossref(FIX,SRC);self.assertFalse(E.filter_papers([p],{'sources':['aer'],'clock':'both','end':'2026-10-24'})[0])
 def test_expired_evidence_excluded(self):p=E.parse_crossref(FIX,SRC);p['evidence']=[{'date':'2026-06-03','verified':True,'url':'https://www.aeaweb.org/research/x','source':'AEA','kind':'study','title':'x'}];q={'sources':['aer'],'end':'2026-10-24','clock':'both','attention':'30d'};self.assertFalse(E.filter_papers([p],q)[0])
 def test_evidence_linking(self):ids,ev=E.evidence_page('<h1>Evidence title</h1><meta property="article:published_time" content="2026-10-01"><a href="https://doi.org/10.1257/aer.test">paper</a>','https://example.org/news','test');self.assertEqual(ids,{'10.1257/aer.test'});self.assertTrue(ev['verified'])
 def test_dateless_evidence_not_verified(self):ids,ev=E.evidence_page('<h1>Title</h1><a href="https://doi.org/10.1257/aer.test">paper</a>','https://example.org','test');self.assertFalse(ev['verified'])
 def test_csv_formula(self):p=E.parse_crossref(FIX,SRC);p['title']='=HYPERLINK("https://example.org")';row=list(csv.reader(io.StringIO(E.export_csv([p]))))[1];self.assertTrue(row[0].startswith("'="))
 def test_ris(self):self.assertIn('DO  - 10.1257/aer.test',E.export_ris([E.parse_crossref(FIX,SRC)]))
 def test_sqlite(self):
  with tempfile.TemporaryDirectory() as t:
   s=E.Store(t);p=E.parse_crossref(FIX,SRC);s.upsert([p]);s.bookmark(p['id'],True);s.upsert([p]);self.assertEqual(len(s.papers(True)),1)
 def test_cnki_exact_source(self):rows=[{'title':'这是一条测试题录','source':'世界经济研究','url':'https://kns.cnki.net/a','date':'2026-10-01'}];self.assertEqual(E.import_cnki_rows(rows,CAT)[0],[])
 def test_cnki_fields(self):rows=[{'title':'这是一条测试题录','source':'世界经济','url':'https://kns.cnki.net/a','date':'2026-10-01','authors':['测试'],'citations':'10'}];p=E.import_cnki_rows(rows,CAT)[0][0];self.assertEqual(p['source_id'],'sjjj');self.assertIsNone(p['citations']);self.assertEqual(p['evidence'],[])
 def test_import_ris(self):p=E.parse_crossref(FIX,SRC);items=E.parse_reference_import(E.export_ris([p]),CAT);self.assertEqual(items[0]['doi'],p['doi'])
 def test_cancel(self):c=E.Client();c.cancel.set();self.assertRaises(E.Cancelled,c.check)
 def test_no_false_future(self):p=E.parse_crossref(FIX,SRC);p['date']='2027-01-01';self.assertFalse(E.filter_papers([p],{'sources':['aer'],'end':'2026-10-24','uncertain':True})[0])
if __name__=='__main__':unittest.main(verbosity=2)
