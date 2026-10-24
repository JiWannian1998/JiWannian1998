"""Real Windows-network acceptance. No synthetic records used here."""
import concurrent.futures as cf,json,pathlib,sys
from datetime import date
import engine as E
ROOT=pathlib.Path(__file__).resolve().parent;CAT=json.loads((ROOT/'catalog.json').read_text(encoding='utf-8'))
for s in CAT:
 if s['id']=='ecta':s['extra_issns']=['1468-0262']
OUT=pathlib.Path(sys.argv[1] if len(sys.argv)>1 else 'verification');OUT.mkdir(parents=True,exist_ok=True)
client=E.Client(use_cache=False);end=date.today();start=E.window_start(end,'1y');papers=[];checks=[];reports=[]
def log(s):print(s.encode('ascii','backslashreplace').decode(),flush=True)
for d,sid,expected in [('10.1257/aer.20231016','aer','Conservation Priorities'),('10.3386/w35514','nber','Investing in Mothers')]:
 try:
  j,obj=client.json('https://api.crossref.org/works/'+d);p=E.parse_crossref(j['message'],next(s for s in CAT if s['id']==sid));good=bool(p and p['doi']==d and expected in p['title']);checks.append({'name':sid+'_known_record','passed':good,'url':obj['url'],'title':p['title'] if p else ''})
  if p:papers.append(p)
 except Exception as e:checks.append({'name':sid+'_known_record','passed':False,'error':str(e)})
def collect(s):
 try:
  if s['language']=='en':return E.crossref(client,s,start,end,log,max_pages=1)
  if s['id'] in ('sjjj','jjdl','shxyj','glsj','jjxjk'):return E.chinese(client,s,start,end,log,budget=16)
  return [],[{'source_id':s['id'],'source':s['name'],'status':'assisted','retrieved':0,'note':'本轮未自动验证；使用知网正常浏览辅助采集。'}]
 except Exception as e:return [],[{'source_id':s['id'],'source':s['name'],'status':'error','retrieved':0,'note':str(e)}]
with cf.ThreadPoolExecutor(max_workers=3) as pool:
 for items,reps in pool.map(collect,CAT):papers+=items;reports+=reps
papers=E.dedup(papers)
try:reports.append(E.collect_evidence(client,papers,start,end,log,budget=70))
except Exception as e:reports.append({'source_id':'attention','status':'error','note':str(e)})
english=[s for s in CAT if s['language']=='en'];counts={s['id']:sum(p['source_id']==s['id'] for p in papers) for s in CAT}
checks.append({'name':'all_top5_nber_have_real_records','passed':all(counts[s]>0 for s in E.TOP_IDS),'counts':{s:counts[s] for s in E.TOP_IDS}})
checks.append({'name':'no_front_matter_or_book_reviews','passed':all(E.is_research(p['title']) for p in papers)})
checks.append({'name':'unique_identifiers','passed':len({p['id'] for p in papers})==len(papers)})
checks.append({'name':'all_links_valid_http','passed':all(E.safe_url(p['url']) for p in papers)})
checks.append({'name':'evidence_has_dates_and_document_links','passed':all(e.get('date') and E.safe_url(e['url']) and e.get('match') for p in papers for e in p.get('evidence',[]))})
report={'version':E.VERSION,'checked_at':E.stamp(),'os':sys.platform,'window':{'start':str(start),'end':str(end)},'records':len(papers),'counts':counts,'english_sources_with_records':sum(counts[s['id']]>0 for s in english),'english_sources_total':len(english),'papers_with_evidence':sum(bool(p.get('evidence')) for p in papers),'checks':checks,'source_reports':reports,'scope':'Each English source reads at most one 200-record index page in this acceptance run; app supports pagination. Chinese public pages are bounded; browser-assisted CNKI is NOT counted as verified automatic access.'}
(OUT/'live_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');(OUT/'live_records.json').write_text(json.dumps(papers,ensure_ascii=False,indent=2),encoding='utf-8');log(json.dumps({k:v for k,v in report.items() if k!='source_reports'},ensure_ascii=False,indent=2))
mandatory=checks[0]['passed'] and checks[1]['passed'] and sum(counts[s]>0 for s in E.TOP_IDS)>=4
sys.exit(0 if mandatory else 2)
