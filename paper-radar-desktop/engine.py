"""Paper Radar Desktop: free public metadata, dated evidence, local SQLite.
No API keys, logins, LLM calls, subscription services or fabricated popularity scores.
"""
from __future__ import annotations
import calendar, concurrent.futures as cf, csv, hashlib, html, io, json, os, re, sqlite3, threading, time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlparse
from urllib.robotparser import RobotFileParser
import requests
from bs4 import BeautifulSoup
VERSION='2.0.0'
UA='PaperRadarDesktop/2.0 (personal academic discovery; public metadata only)'
CNKI_URL='https://kns.cnki.net/kns8s/AdvSearch'
TOP_IDS={'aer','qje','jpe','ecta','restud','nber'}
OFFICIAL={
 'jjyj':['https://jjyj.cbpt.cnki.net/','https://www.erj.cn/'],
 'glsj':['https://glsj.cbpt.cnki.net/','https://www.mwm.net.cn/'],
 'sjjj':['https://sjjj.magtech.com.cn/CN/current','https://sjjj.magtech.com.cn/CN/archive'],
 'jjxjk':['https://ccj.pku.edu.cn/journal/Info?jid=96822','https://www.nsd.pku.edu.cn/cbw/jjxjk/qkml/index.htm'],
 'zggyjj':['https://ggyy.cbpt.cnki.net/portal','https://www.ciejournal.org/'],
 'sljj':['https://www.jqte.net/sljjjsjjyj/ch/index.aspx'],
 'shxyj':['https://shxyj.ajcass.com/'],
 'jjdl':['https://www.jjdl.com.cn/CN/current','https://www.jjdl.com.cn/CN/article/showOldVolumn.do'],
 'sjjjyzz':['https://sjjz.cbpt.cnki.net/']}
ALIASES={
 'jjxjk':['经济学(季刊)','经济学（季刊）','China Economic Quarterly'],
 'sjjj':['世界经济','The Journal of World Economy'],
 'jjdl':['经济地理','Economic Geography'],
 'jjyj':['经济研究','Economic Research Journal'],
 'glsj':['管理世界','Management World'],
 'zggyjj':['中国工业经济','China Industrial Economics'],
 'sljj':['数量经济技术经济研究','The Journal of Quantitative & Technical Economics'],
 'shxyj':['社会学研究','Sociological Studies'],
 'sjjjyzz':['世界经济与政治','World Economics and Politics']}
class Cancelled(Exception):pass
class SourceError(Exception):pass
def stamp():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def text(s):
 if not s:return ''
 return re.sub(r'\s+',' ',BeautifulSoup(str(s),'html.parser').get_text(' ',strip=True)).strip()
def norm(s):return re.sub(r'[^\w\u4e00-\u9fff]','',html.unescape(str(s or '')).lower())
def doi_norm(s):return re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi\s*:\s*)','',unquote(str(s or '')).strip(),flags=re.I).lower().rstrip(' .;')
def safe_url(u):
 try:
  p=urlparse(u);return p.scheme in ('https','http') and bool(p.hostname) and not p.username and not p.password
 except ValueError:return False
def interval(s):
 try:
  if re.fullmatch(r'\d{4}',str(s)):return date(int(s),1,1),date(int(s),12,31)
  if re.fullmatch(r'\d{4}-\d{2}',str(s)):
   y,m=map(int,s.split('-'));return date(y,m,1),date(y,m,calendar.monthrange(y,m)[1])
  d=date.fromisoformat(str(s)[:10]);return d,d
 except (ValueError,TypeError):return None
def normalize_date(s):
 m=re.match(r'^\s*(20\d{2})(?:[-/年](\d{1,2}))?(?:[-/月](\d{1,2}))?',str(s or ''))
 if not m:return ''
 p=m.groups();v=p[0]+('-%02d'%int(p[1]) if p[1] else '')+('-%02d'%int(p[2]) if p[2] else '')
 return v if interval(v) else ''
def window_start(end,value):
 if value in ('7d','30d'):return end-timedelta(days=int(value[:-1])-1)
 n=6 if value=='6m' else 12;index=end.year*12+end.month-1-n;y,m=divmod(index,12);m+=1
 return date(y,m,min(end.day,calendar.monthrange(y,m)[1]))+timedelta(days=1)
def in_window(s,start,end,overlap=False):
 iv=interval(s);return bool(iv and ((iv[0]<=end and iv[1]>=start) if overlap else (start<=iv[0] and iv[1]<=end)))
def is_research(title):
 t=text(title)
 if re.search(r'^(front matter|back matter|contents|table of contents|index to|editorial|editor.s report|announcement|erratum|corrigendum|correction|retraction|cover image|issue information|list of referees|book reviews?)\b',t,re.I):return False
 if re.search(r'^(目录|封面|编委会|征稿|征订|更正|勘误|致谢)|(?:书评|评介)$',t):return False
 return len(t)>5
def methods(title,abstract):
 s=title+' '+abstract
 rules={'随机实验':r'randomi[sz]ed|random assignment|field experiment|随机对照|随机实验','双重差分':r'difference[s]?.in.difference|双重差分|三重差分','工具变量':r'instrumental variable|工具变量','断点回归':r'regression discontinuity|断点回归','事件研究':r'event.study|事件研究','结构估计':r'structural (?:model|estimat)|结构估计|结构模型','行政/调查数据':r'administrative data|survey data|panel data|行政数据|调查数据|面板数据','访谈/田野':r'ethnograph|qualitative interview|process tracing|田野调查|深度访谈|过程追踪','实证线索':r'empirical|实证|微观数据'}
 return [k for k,v in rules.items() if re.search(v,s,re.I)]
def meta(soup,key):return [text(m.get('content')) for m in soup.select('meta[content]') if (m.get('name','').lower()==key.lower() or m.get('property','').lower()==key.lower()) and m.get('content')]
def page_date(soup):
 for k in ('article:published_time','citation_online_date','citation_publication_date','citation_date','DC.Date','datePublished'):
  for v in meta(soup,k):
   d=normalize_date(v)
   if d:return d,'网页发表日期元数据'
 for script in soup.select('script[type="application/ld+json"]'):
  try:
   j=json.loads(script.string or script.get_text());stack=j if isinstance(j,list) else [j]
   while stack:
    x=stack.pop()
    if not isinstance(x,dict):continue
    stack.extend(x.get('@graph',[]) if isinstance(x.get('@graph'),list) else [])
    d=normalize_date(x.get('datePublished',''))
    if d:return d,'结构化发表日期'
  except (ValueError,TypeError):pass
 main=soup.select_one('main, article') or soup
 for t in main.select('time[datetime]'):
  d=normalize_date(t['datetime'])
  if d:return d,'正文时间标签'
 s=main.get_text(' ',strip=True)
 m=re.search(r'(?:在线发布日期|出版日期|发布日期|刊出日期|发布时间)\s*[:：]?\s*(20\d{2}[-/年]\d{1,2}[-/月]\d{1,2})',s)
 if m:return normalize_date(m[1]),'正文明确发表日期'
 m=re.search(r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(20\d{2})\b',s[:6000])
 if m:
  try:return datetime.strptime(' '.join(m.groups()),'%B %d %Y').date().isoformat(),'正文明确日期'
  except ValueError:pass
 return '','日期未取得'
def parse_crossref(x,src):
 d=doi_norm(x.get('DOI'));title=text((x.get('title') or [''])[0])
 if not d or not is_research(title):return None
 if src['id']=='nber':
  if not re.fullmatch(r'10\.3386/w\d+',d):return None
 else:
  ids={src.get('issn'),*(src.get('extra_issns') or [])}
  if not ids.intersection(x.get('ISSN',[])) or x.get('type')!='journal-article':return None
 dates=[]
 for key,label in [('published-online','在线发表'),('published-print','纸刊发表'),('posted','首次发布')]:
  for p in x.get(key,{}).get('date-parts',[]):
   val=normalize_date('-'.join(map(str,p)))
   if val:dates.append({'date':val,'kind':label})
 if not dates:
  for key in ('published','issued'):
   for p in x.get(key,{}).get('date-parts',[]):
    val=normalize_date('-'.join(map(str,p)))
    if val:dates.append({'date':val,'kind':'登记发表日期'})
 chosen=min(dates,key=lambda z:(interval(z['date'])[0],-len(z['date']))) if dates else {'date':'','kind':'日期缺失'}
 abst=text(x.get('abstract',''));authors=[text(' '.join([a.get('given',''),a.get('family','')])) or a.get('name','') for a in x.get('author',[])]
 return {'id':d,'doi':d,'title':title,'authors':authors,'source_id':src['id'],'source':src['name'],'date':chosen['date'],'date_kind':chosen['kind'],'dates':dates,'abstract':abst,'methods':methods(title,abst),'url':'https://www.nber.org/papers/'+d.split('/')[-1] if src['id']=='nber' else 'https://doi.org/'+d,'metadata_url':'https://api.crossref.org/works/'+quote(d,safe='/'),'provider':'Crossref公开元数据','citations':x.get('is-referenced-by-count'),'evidence':[],'candidates':[],'observed_at':stamp(),'type':'工作论文版本' if src['id']=='nber' else '期刊论文'}
class Store:
 def __init__(self,root=None):
  self.root=Path(root or os.getenv('PAPERRADAR_DATA') or (Path(os.getenv('LOCALAPPDATA') or Path.home())/'PaperRadar'));self.root.mkdir(parents=True,exist_ok=True);self.path=self.root/'radar.sqlite3'
  with self.connect() as c:
   c.execute('CREATE TABLE IF NOT EXISTS papers(id TEXT PRIMARY KEY, payload TEXT NOT NULL, saved INTEGER NOT NULL DEFAULT 0, updated TEXT)')
   c.execute('CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, ts REAL NOT NULL, payload TEXT NOT NULL)')
   c.execute('CREATE TABLE IF NOT EXISTS prefs(key TEXT PRIMARY KEY, payload TEXT NOT NULL)')
   c.execute('CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, ts TEXT, payload TEXT)')
 @contextmanager
 def connect(self):
  connection=sqlite3.connect(self.path,timeout=30)
  try:
   connection.execute('PRAGMA journal_mode=WAL')
   with connection:yield connection
  finally:connection.close()
 def upsert(self,papers):
  with self.connect() as c:
   for p in papers:c.execute('INSERT INTO papers(id,payload,updated) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,updated=excluded.updated',(p['id'],json.dumps(p,ensure_ascii=False),stamp()))
 def papers(self,saved_only=False):
  with self.connect() as c:rows=c.execute('SELECT payload,saved FROM papers'+(' WHERE saved=1' if saved_only else '')).fetchall()
  return [dict(json.loads(p),saved=bool(s)) for p,s in rows]
 def bookmark(self,pid,saved):
  with self.connect() as c:c.execute('UPDATE papers SET saved=? WHERE id=?',(int(saved),pid))
 def cache(self,key,ttl=21600):
  with self.connect() as c:r=c.execute('SELECT ts,payload FROM cache WHERE key=?',(key,)).fetchone()
  return json.loads(r[1]) if r and time.time()-r[0]<ttl else None
 def put_cache(self,key,payload):
  with self.connect() as c:
   c.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?)',(key,time.time(),json.dumps(payload,ensure_ascii=False)));c.execute('DELETE FROM cache WHERE ts<?',(time.time()-7*86400,))
 def setting(self,key,default=None):
  with self.connect() as c:r=c.execute('SELECT payload FROM prefs WHERE key=?',(key,)).fetchone()
  return json.loads(r[0]) if r else default
 def save_setting(self,key,value):
  with self.connect() as c:c.execute('INSERT OR REPLACE INTO prefs VALUES(?,?)',(key,json.dumps(value,ensure_ascii=False)))
 def add_run(self,report):
  with self.connect() as c:
   c.execute('INSERT INTO runs(ts,payload) VALUES(?,?)',(stamp(),json.dumps(report,ensure_ascii=False)));c.execute('DELETE FROM runs WHERE id NOT IN(SELECT id FROM runs ORDER BY id DESC LIMIT 30)')
class Client:
 def __init__(self,store=None,cancel=None,use_cache=True):
  self.store=store;self.cancel=cancel or threading.Event();self.use_cache=use_cache;self.locks={};self.guard=threading.Lock();self.last={};self.robots={}
 def check(self):
  if self.cancel.is_set():raise Cancelled('用户已停止检索')
 def get(self,url,params=None,api=False,attempts=2):
  self.check()
  if not safe_url(url):raise SourceError('不是合法公开HTTP地址')
  u=requests.Request('GET',url,params=params).prepare().url;key=hashlib.sha256(u.encode()).hexdigest()
  if self.store and self.use_cache:
   obj=self.store.cache(key)
   if obj:obj['cached']=True;return obj
  host=urlparse(u).hostname
  with self.guard:lock=self.locks.setdefault(host,threading.RLock())
  with lock:
   self.check()
   if not api and host not in self.robots:
    root=f'{urlparse(u).scheme}://{urlparse(u).netloc}'
    try:
     r=self._request(root+'/robots.txt',1);rp=RobotFileParser();rp.parse(r['text'].splitlines());self.robots[host]=rp
    except SourceError as e:
     if 'HTTP 404' in str(e) or 'HTTP 410' in str(e):self.robots[host]=None
     else:raise SourceError('无法确认站点抓取规则：'+str(e))
   if not api and self.robots.get(host) and not self.robots[host].can_fetch('PaperRadarDesktop',u):raise SourceError('站点robots规则不允许自动读取，请正常浏览器访问')
   if self.cancel.wait(max(0,.35-(time.monotonic()-self.last.get(host,0)))):self.check()
   obj=self._request(u,attempts);self.last[host]=time.monotonic()
  if self.store and self.use_cache:self.store.put_cache(key,obj)
  return obj
 def _request(self,u,attempts):
  err=None
  for i in range(attempts):
   self.check()
   try:
    with requests.get(u,headers={'User-Agent':UA,'Accept':'application/json,text/html,application/xml;q=0.8'},timeout=(8,22),stream=True) as r:
     if r.status_code==429 and i+1<attempts:
      delay=min(30,max(5,int(r.headers.get('Retry-After','5')))) if r.headers.get('Retry-After','5').isdigit() else 5
      if self.cancel.wait(delay):self.check()
      continue
     if r.status_code>=400:raise SourceError(f'HTTP {r.status_code}: {urlparse(r.url).hostname}')
     raw=bytearray()
     for chunk in r.iter_content(65536):
      self.check();raw.extend(chunk)
      if len(raw)>16_000_000:raise SourceError('响应大于16MB，停止读取')
     charset=re.search(br'charset\s*=\s*["\']?([\w-]+)',bytes(raw[:4000]),re.I)
     enc=r.encoding if 'charset=' in r.headers.get('Content-Type','') else (charset[1].decode() if charset else 'utf-8')
     try:body=raw.decode(enc or 'utf-8')
     except (UnicodeDecodeError,LookupError):body=raw.decode('gb18030',errors='replace')
     return {'url':r.url,'text':body,'fetched_at':stamp(),'cached':False,'status':r.status_code}
   except Cancelled:raise
   except (requests.RequestException,SourceError) as e:
    err=str(e)
    if 'HTTP 403' in err or 'HTTP 401' in err or 'HTTP 400' in err:break
    if i+1<attempts and self.cancel.wait(i+1):self.check()
  raise SourceError((err or '连接失败')[:350])
 def json(self,url,params=None):
  obj=self.get(url,params,api=True)
  try:return json.loads(obj['text']),obj
  except ValueError:raise SourceError('公开接口未返回JSON；可能为验证页')
def crossref(client,src,start,end,progress=lambda s:None,max_pages=15):
 identifiers=[src.get('issn')]+src.get('extra_issns',[]);papers={};reports=[]
 for identifier in identifiers:
  url='https://api.crossref.org/prefixes/10.3386/works' if src['id']=='nber' else 'https://api.crossref.org/journals/'+identifier+'/works'
  # Cursor pagination must not be combined with publication-date sorting.
  params={'filter':f'from-pub-date:{start},until-pub-date:{end}','rows':200,'cursor':'*'}
  if src['id']!='nber':params['filter']+=',type:journal-article'
  raw=0;total=None;done=False;error='';seen=set()
  try:
   for page in range(max_pages):
    client.check();data,obj=client.json(url,params);msg=data.get('message',{});items=msg.get('items')
    if not isinstance(items,list):raise SourceError('Crossref响应结构不匹配')
    total=msg.get('total-results');raw+=len(items)
    fingerprint=tuple(x.get('DOI') for x in items)
    if items and fingerprint in seen:raise SourceError('分页返回重复记录，未宣称完整覆盖')
    seen.add(fingerprint)
    for x in items:
     p=parse_crossref(x,src)
     if p and in_window(p['date'],start,end,True):p['observed_at']=obj['fetched_at'];papers[p['id']]=p
    progress(f"{src['short']}：已读取 {raw} 条登记记录，研究论文 {len(papers)} 篇")
    if len(items)<params['rows'] or (isinstance(total,int) and raw>=total):done=True;break
    cursor=msg.get('next-cursor')
    if not cursor:raise SourceError('分页缺少下一游标，覆盖不完整')
    params['cursor']=cursor
  except Cancelled:raise
  except Exception as e:error=str(e)[:350]
  reports.append({'source_id':src['id'],'source':src['name'],'provider':'Crossref','url':url,'retrieved':len(papers),'scanned':raw,'index_total':total,'status':'ok' if done else 'partial' if papers else 'error','complete_index':done,'note':error or ('该查询索引已读完；不等于期刊全部内容' if done else '达到分页上限，覆盖不完整'),'checked_at':stamp()})
  if papers or (done and total and total>0):break
 return list(papers.values()),reports
def article_html(body,url,src):
 soup=BeautifulSoup(body,'html.parser');title=(meta(soup,'citation_title') or meta(soup,'DC.Title') or [''])[0]
 if not is_research(title) or norm(title)==norm(src['name']):return None
 journal=meta(soup,'citation_journal_title');allowed={norm(src['name']),*(norm(v) for v in ALIASES.get(src['id'],[]))}
 if journal and not allowed.intersection(norm(v) for v in journal):return None
 d,kind=page_date(soup);explicit=[]
 for m in re.finditer(r'(在线发布日期|出版日期|刊出日期)[\s:：]*(20\d{2}[-/]\d{1,2}[-/]\d{1,2})',soup.get_text(' ',strip=True)):
  v=normalize_date(m[2])
  if v:explicit.append((v,m[1]))
 if explicit:
  if d:explicit.append((d,kind))
  d,kind=min(explicit)
 if not d:
  m=re.search(r'/Y(20\d{2})/V',url)
  if m:d=m[1];kind='仅年份，未虚构月日'
 node=soup.select_one('#abstract, #abstract_cn, .abstract, #Abstract');abstract=text(node) if node else (meta(soup,'description') or [''])[0]
 if '{{' in abstract:abstract=''
 doi=doi_norm((meta(soup,'citation_doi') or [''])[0]);pid=doi or 'web:'+hashlib.sha256(url.encode()).hexdigest()[:24]
 return {'id':pid,'doi':doi,'title':title,'authors':meta(soup,'citation_author') or meta(soup,'dc.creator'),'source_id':src['id'],'source':src['name'],'date':d,'date_kind':kind,'dates':[],'abstract':abstract,'methods':methods(title,abstract),'url':url,'metadata_url':url,'provider':'期刊官方公开页','citations':None,'evidence':[],'candidates':[],'observed_at':stamp(),'type':'期刊论文'}
def chinese(client,src,start,end,progress=lambda s:None,budget=45):
 queue=list(OFFICIAL.get(src['id'],[]));seen=set();papers={};errors=[]
 while queue and len(seen)<budget:
  client.check();url=queue.pop(0)
  if url in seen:continue
  seen.add(url)
  try:
   obj=client.get(url);soup=BeautifulSoup(obj['text'],'html.parser');actual=obj['url'];short=soup.get_text(' ',strip=True)
   if len(short)<80 or (len(short)<2500 and re.search(r'验证码|安全验证|Access Denied|captcha',short,re.I)):
    errors.append('验证/动态页面：'+urlparse(actual).hostname);continue
   p=article_html(obj['text'],actual,src)
   if p:
    if in_window(p['date'],start,end,True):papers[p['id']]=p
    continue
   articles=[];indices=[]
   for a in soup.select('a[href]'):
    u=urljoin(actual,a['href']).split('#')[0];label=a.get_text(' ',strip=True)
    if not safe_url(u) or urlparse(u).hostname!=urlparse(actual).hostname or u in seen:continue
    if re.search(r'login|register|download|\.pdf|admin|top_access|showBrowse',u,re.I):continue
    years=re.findall(r'20\d{2}',u+' '+label)
    if years and max(map(int,years))<start.year:continue
    if re.search(r'/Y20\d{2}/V\d+/I\d+/\d+|/abstract|view_abstract|ArticleDetails|/paper/[\w-]+|/doi/|/html/|/Article/',u,re.I):articles.append(u)
    elif re.search(r'过刊|本期|目录|下一页|网络首发',label) or re.search(r'/archive|/volumn/|/qkml/|showOldVolumn',u,re.I):indices.append(u)
   queue=list(dict.fromkeys(articles+queue+indices));progress(f"{src['short']}：读取 {len(seen)} 个公开页，取得 {len(papers)} 篇")
  except Cancelled:raise
  except Exception as e:errors.append(str(e)[:160])
 note=f'公开网页限额采集，已读取{len(seen)}页；不代表完整目录。'
 if not papers:note+='未取得题录；可用内置知网浏览器正常检索后采集当前结果。'
 if errors:note+=' '+'; '.join(dict.fromkeys(errors))[:700]
 return list(papers.values()),[{'source_id':src['id'],'source':src['name'],'provider':'官方公开页/知网期刊页','retrieved':len(papers),'scanned':len(seen),'status':'partial' if papers else 'assisted','complete_index':False,'note':note,'checked_at':stamp()}]
def linked_dois(soup,base):
 result=set()
 for a in soup.select('a[href]'):
  u=unquote(urljoin(base,a['href']));m=re.search(r'(?:doi\.org/|aeaweb\.org/articles\?id=)(10\.\d{4,9}/[^\s?&#]+)',u,re.I)
  if m:result.add(doi_norm(m[1]))
  m=re.search(r'nber\.org/(?:papers/|system/files/working_papers/)(w\d+)',u)
  if m:result.add('10.3386/'+m[1])
 return result
def evidence_page(body,url,source):
 soup=BeautifulSoup(body,'html.parser');ids=linked_dois(soup,url);d,kind=page_date(soup)
 if not d:
  m=re.search(r'/digest/(20\d{2})(\d{2})/',url)
  if m:d=m[1]+'-'+m[2];kind='Digest期号，月精度'
 title=text(soup.h1) if soup.h1 else (meta(soup,'og:title') or [''])[0]
 return ids,{'title':title,'url':url,'date':d,'date_kind':kind,'source':source,'kind':'研究专题介绍' if len(ids)<=2 else '文章中的文献链接（非独立专题）','match':'网页明确链接原论文DOI或NBER编号','verified':bool(ids and d and title),'checked_at':stamp()}
def evidence_sample(targets,budget):
 buckets={}
 for name,url in sorted(targets,reverse=True):buckets.setdefault(name,[]).append((name,url))
 selected=[]
 # Round-robin by provider: large NBER archive must not consume the AEA budget.
 for i in range(max((len(x) for x in buckets.values()),default=0)):
  for name in sorted(buckets):
   if i<len(buckets[name]):selected.append(buckets[name][i])
   if len(selected)>=budget:return selected
 return selected
def collect_evidence(client,papers,start,end,progress=lambda s:None,budget=100):
 bydoi={p['doi']:p for p in papers if p.get('doi')};targets=set();errors=[];scanned=0;matched=0;inspected=[]
 queue=[('AEA研究精选','https://www.aeaweb.org/research'),('NBER Digest','https://www.nber.org/digest')];seen=set()
 while queue and len(seen)<14:
  name,root=queue.pop(0)
  if root in seen:continue
  seen.add(root)
  try:
   obj=client.get(root);soup=BeautifulSoup(obj['text'],'html.parser')
   for a in soup.select('a[href]'):
    u=urljoin(obj['url'],a['href']).split('#')[0];parts=urlparse(u)
    if parts.scheme!='https':continue
    if parts.hostname in ('www.aeaweb.org','aeaweb.org'):
     if re.fullmatch(r'/research/[\w-]+',parts.path) and parts.path not in ('/research/about','/research/archive','/research/contact'):targets.add((name,u))
     elif parts.path in ('/research','/research/archive') and u not in seen:queue.append((name,u))
    elif re.fullmatch(r'(?:www\d?\.)?nber\.org',parts.hostname or ''):
     if re.fullmatch(r'/digest/\d{6}/[^/]+',parts.path):targets.add((name,u))
     elif parts.path.startswith('/digest') and not re.search(r'\.pdf$|subscribe|download',u,re.I) and u not in seen:queue.append((name,u))
  except Cancelled:raise
  except Exception as e:errors.append(name+': '+str(e)[:220])
 def visit(item):
  name,u=item
  try:
   obj=client.get(u);ids,ev=evidence_page(obj['text'],obj['url'],name);return ids,ev,''
  except Cancelled:raise
  except Exception as e:return set(),None,str(e)[:100]
 selected=evidence_sample(targets,budget)
 with cf.ThreadPoolExecutor(max_workers=3) as pool:
  for ids,ev,err in pool.map(visit,selected):
   client.check();scanned+=1
   if err:errors.append(err)
   if ev:
    inspected.append({'url':ev['url'],'title':ev['title'],'date':ev['date'],'linked_dois':sorted(ids),'verified':ev['verified']})
   if ev and ev['verified']:
    for d in ids:
     if d in bydoi:
      p=bydoi[d]
      if not any(x['url']==ev['url'] for x in p['evidence']):p['evidence'].append(ev);matched+=1
   if scanned%8==0:progress(f'关注证据：核对 {scanned}/{len(selected)} 个网页，关联 {matched} 条')
 return {'source_id':'attention','source':'公开关注证据','status':'partial','retrieved':matched,'scanned':scanned,'inspected_pages':inspected,'note':'AEA / NBER有限栏目；不是全网热度。未匹配不等于无人关注。 '+'; '.join(dict.fromkeys(errors))[:400],'checked_at':stamp()}
def dedup(papers):
 result={}
 for p in papers:
  key=doi_norm(p.get('doi')) or p['id'];p=dict(p,id=key)
  if key in result:
   old=result[key];ev={e['url']:e for e in old.get('evidence',[])+p.get('evidence',[])}
   if p.get('abstract') and not old.get('abstract'):old['abstract']=p['abstract']
   old['evidence']=list(ev.values())
  else:result[key]=p
 return list(result.values())
def filter_papers(papers,q):
 end=date.fromisoformat(q.get('end') or date.today().isoformat());start=window_start(end,q.get('window','1y'));att=window_start(end,q.get('attention','30d'));output=[];counts={'date_excluded':0,'no_evidence':0,'method_excluded':0}
 for item in dedup(papers):
  if item['source_id'] not in q.get('sources',TOP_IDS):continue
  p=dict(item);iv=interval(p.get('date'))
  if iv and iv[0]>end:counts['date_excluded']+=1;continue
  if q.get('clock','publication')!='attention' and not in_window(p.get('date'),start,end,q.get('uncertain',False)):counts['date_excluded']+=1;continue
  if q.get('keywords') and q['keywords'].casefold() not in (p['title']+' '+p.get('abstract','')+' '+' '.join(p.get('authors',[]))).casefold():continue
  if q.get('empirical')=='only' and not p.get('methods'):counts['method_excluded']+=1;continue
  active=[e for e in p.get('evidence',[]) if e.get('verified') and in_window(e.get('date'),att,end,q.get('uncertain',False))]
  p['active_evidence']=active;p['attention_count']=len(active);p['attention_domains']=len({urlparse(e['url']).hostname for e in active})
  if q.get('clock') in ('attention','both') and not active:counts['no_evidence']+=1;continue
  p['reasons']=[{'text':f"{e['date']} · {e['source']}：{e['kind']}",'url':e['url']} for e in active]
  if not active:p['reasons']=[{'text':'符合所选来源/日期；未取得窗口内关注证据，不标记为热门。','url':p.get('metadata_url') or p['url']}]
  if p.get('methods'):p['reasons'].append({'text':'方法线索：'+'、'.join(p['methods'])+'（需全文确认）','url':p['url']})
  p['uncertain_date']=bool(iv and not in_window(p.get('date'),start,end));output.append(p)
 pref=lambda p:bool(p.get('methods')) if q.get('empirical')=='prefer' else False
 def key(p):
  if q.get('sort')=='recent':return (p.get('date') or '',pref(p),p['attention_count'])
  if q.get('sort')=='citations':return (p.get('citations') if p.get('citations') is not None else -1,pref(p),p.get('date') or '')
  return (p['attention_domains'],p['attention_count'],pref(p),p.get('date') or '')
 return sorted(output,key=key,reverse=True),counts
def search(catalog,q,store,progress=lambda s:None,on_source=lambda p,r:None,cancel=None):
 cancel=cancel or threading.Event();client=Client(store,cancel,use_cache=q.get('cache',True));end=date.fromisoformat(q.get('end') or date.today().isoformat());start=window_start(end,'1y' if q.get('clock')=='attention' else q.get('window','1y'));selected=[s for s in catalog if s['id'] in q['sources']];papers=[];reports=[]
 def one(src):return chinese(client,src,start,end,progress) if src.get('language',src.get('lang'))=='zh' else crossref(client,src,start,end,progress)
 try:
  with cf.ThreadPoolExecutor(max_workers=3) as pool:
   jobs={pool.submit(one,s):s for s in selected}
   for fut in cf.as_completed(jobs):
    client.check();src=jobs[fut]
    try:items,reps=fut.result()
    except Cancelled:raise
    except Exception as e:items=[];reps=[{'source_id':src['id'],'source':src['name'],'status':'error','retrieved':0,'note':str(e)}]
    papers+=items;reports+=reps;on_source(items,reps)
  existing={p['id']:p for p in store.papers()}
  for p in papers:
   if p['id'] in existing:p['evidence']=existing[p['id']].get('evidence',[])
  if q.get('evidence',True) and papers:reports.append(collect_evidence(client,papers,window_start(end,q.get('attention','30d')),end,progress))
 except Cancelled:reports.append({'source_id':'cancelled','source':'本次检索','status':'cancelled','note':'用户停止；已完成的部分保留'})
 papers=dedup(papers);store.upsert(papers);imports=[p for p in store.papers() if p.get('provider','').startswith(('知网用户','用户导入')) and p['source_id'] in q['sources']];papers=dedup(papers+imports);visible,stats=filter_papers(papers,q);report={'checked_at':stamp(),'query':q,'fetched':len(papers),'shown':len(visible),'sources':reports,'filter_stats':stats};store.add_run(report);return papers,report
def export_csv(papers):
 out=io.StringIO(newline='');w=csv.writer(out);w.writerow(['题目','作者','来源','发表日期','日期类型','DOI','原文网址','累计引用(Crossref)','窗口内证据网页数','入选理由','证据网址','元数据来源','采集时间'])
 def cell(v):
  s=str(v if v is not None else '');return "'"+s if s.lstrip().startswith(('=','+','-','@')) else s
 for p in papers:w.writerow([cell(v) for v in [p['title'],'; '.join(p.get('authors',[])),p['source'],p.get('date'),p.get('date_kind'),p.get('doi'),p['url'],p.get('citations'),p.get('attention_count',0),' | '.join(r['text'] for r in p.get('reasons',[])),' | '.join(e['url'] for e in p.get('active_evidence',[])),p.get('provider'),p.get('observed_at')]])
 return out.getvalue()
def export_ris(papers):
 lines=[]
 for p in papers:
  lines+=['TY  - '+('RPRT' if p['source_id']=='nber' else 'JOUR'),'TI  - '+text(p['title'])];lines+=['AU  - '+text(a) for a in p.get('authors',[])];lines+=['JO  - '+p['source'],'PY  - '+(p.get('date') or '')[:4],'DA  - '+(p.get('date') or ''),'UR  - '+p['url']]
  if p.get('doi'):lines+=['DO  - '+p['doi']]
  lines+=['ER  - ','']
 return '\n'.join(lines)
def catalog_aliases(catalog,chinese_only=False):
 sources=[s for s in catalog if not chinese_only or s.get('language',s.get('lang'))=='zh']
 aliases={norm(s['name']):s for s in sources}
 for s in sources:
  for a in ALIASES.get(s['id'],[]):aliases.setdefault(norm(a),s)
 return aliases
def import_cnki_rows(rows,catalog):
 aliases=catalog_aliases(catalog,True);output=[];rejected=0
 for row in rows:
  src=aliases.get(norm(row.get('source')));title=text(row.get('title'));u=row.get('url','')
  if not src or not is_research(title) or not safe_url(u):rejected+=1;continue
  d=normalize_date(row.get('date'));authors=[text(a) for a in row.get('authors',[]) if text(a)]
  output.append({'id':'web:'+hashlib.sha256(u.encode()).hexdigest()[:24],'doi':'','title':title,'authors':authors,'source_id':src['id'],'source':src['name'],'date':d,'date_kind':'知网显示日期'+('（精度有限）' if len(d)<10 else ''),'dates':[],'abstract':'','methods':methods(title,''),'url':u,'metadata_url':u,'provider':'知网用户正常浏览后采集','citations':None,'evidence':[],'candidates':[],'observed_at':stamp(),'type':'期刊论文','cnki_cumulative':{'citations':row.get('citations'),'downloads':row.get('downloads')}})
 return dedup(output),rejected
def parse_reference_import(content,catalog):
 if len(content)>8_000_000:raise ValueError('文件超过8MB，请分批导入')
 if content.lstrip().startswith(('[','{')):
  j=json.loads(content);rows=j if isinstance(j,list) else j.get('papers',[])
  if not isinstance(rows,list):raise ValueError('JSON应为论文数组或含papers数组的对象')
  allowed={s['id'] for s in catalog};items=[]
  for p in rows:
   if isinstance(p,dict) and p.get('source_id') in allowed and p.get('title') and safe_url(p.get('url','')):
    p=dict(p);p.setdefault('id',doi_norm(p.get('doi')) or 'web:'+hashlib.sha256(p['url'].encode()).hexdigest()[:24]);p.setdefault('authors',[]);p.setdefault('doi','');p.setdefault('date','');p.setdefault('evidence',[]);p.setdefault('methods',methods(p['title'],p.get('abstract','')));p['provider']='用户导入JSON，未独立核验';p['evidence']=[dict(e,verified=False,match='导入证据待重新核验') for e in p.get('evidence',[]) if isinstance(e,dict) and safe_url(e.get('url',''))];items.append(p)
  return dedup(items)
 records=[];current={}
 for line in content.splitlines()+['ER  -']:
  m=re.match(r'^([A-Z0-9]{2})\s*-\s*(.*)$',line)
  if not m and line.startswith('%'):
   m=re.match(r'^%([A-Z0-9])\s+(.*)$',line)
   if m:key={'T':'TI','A':'AU','J':'JO','D':'PY','U':'UR','R':'DO'}.get(m[1],m[1]);value=m[2]
   else:continue
  elif m:key,value=m.groups()
  else:
   m=re.match(r'^(Title|Author|Journal|Year|PubDate|DOI|Link|URL)(?:-(?:题名|作者|刊名|年|出版日期|网址))?\s*[:：]\s*(.*)$',line,re.I)
   if m:key={'title':'TI','author':'AU','journal':'JO','year':'PY','pubdate':'DA','doi':'DO','link':'UR','url':'UR'}[m[1].lower()];value=m[2]
   else:
    m=re.match(r'^(RT|SR|T1|A1|JF|JO|YR|FD|DO|UL)\s+(.+)$',line)
    if not m:continue
    key={'RT':'TY','SR':'TY','T1':'TI','A1':'AU','JF':'JO','YR':'PY','FD':'DA','UL':'UR'}.get(m[1],m[1]);value=m[2]
  if key=='TY' and current:records.append(current);current={}
  if key=='TI' and current.get('TI'):records.append(current);current={}
  if key=='ER':
   if current:records.append(current);current={}
  else:current.setdefault(key,[]).append(value)
 aliases=catalog_aliases(catalog);out=[]
 for r in records:
  first=lambda *ks:next((r[k][0] for k in ks if r.get(k)),'');title=first('TI','T1');src=aliases.get(norm(first('JO','JF','T2','JA')))
  if not src or not is_research(title):continue
  doi=doi_norm(first('DO'));u=first('UR','LK') or ('https://doi.org/'+doi if doi else '')
  if not safe_url(u):u=CNKI_URL
  d=normalize_date(first('DA','Y1','PY'));ab=first('AB')
  out.append({'id':doi or 'import:'+hashlib.sha256((title+src['id']).encode()).hexdigest()[:24],'doi':doi,'title':title,'authors':r.get('AU',r.get('A1',[])),'source_id':src['id'],'source':src['name'],'date':d,'date_kind':'导出题录日期，未补齐月日','abstract':ab,'methods':methods(title,ab),'url':u,'metadata_url':u,'provider':'用户导入题录，未独立核验','citations':None,'evidence':[],'candidates':[],'observed_at':stamp(),'type':'期刊论文','dates':[]})
 return dedup(out)
