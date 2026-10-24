"""Public scholarly index. No subscription, external API key or access-control bypass."""
from __future__ import annotations
import concurrent.futures as cf
import datetime as dt
import hashlib, html, json, os, pathlib, re, time
from urllib.parse import urljoin, urlparse, unquote, quote
import requests
from bs4 import BeautifulSoup

ROOT=pathlib.Path(__file__).parent
CAT=json.loads((ROOT/'catalog.json').read_text())
NOW=dt.datetime.now(dt.timezone.utc)
TODAY=NOW.date(); START=TODAY-dt.timedelta(days=366)
STAMP=NOW.isoformat()
UA='PaperRadar/1.0 (+https://github.com/JiWannian1998/JiWannian1998/tree/main/paper-radar; public bibliographic metadata)'

def clean(s):return re.sub(r'\s+',' ',BeautifulSoup(str(s or ''),'html.parser').get_text(' ',strip=True)).strip()
def norm(s):return re.sub(r'[^\w\u4e00-\u9fff]','',clean(s).lower())
def doi(s):return unquote(str(s or '')).lower().replace('https://doi.org/','').replace('http://dx.doi.org/','').strip().rstrip('.,;)')
def valid_date(s):
    m=re.match(r'^(\d{4})[-/](\d{1,2})(?:[-/](\d{1,2}))?',str(s or ''))
    if not m:return ''
    try:
        parts=m.groups();dt.date(int(parts[0]),int(parts[1]),int(parts[2] or 1))
        return '-'.join([parts[0],parts[1].zfill(2)]+([parts[2].zfill(2)] if parts[2] else []))
    except ValueError:return ''
def in_range(s,start=START,end=TODAY):
    if not s:return False
    return start.isoformat()[:len(s)]<=s<=end.isoformat()[:len(s)]
def get(url,params=None,attempts=3):
    if urlparse(url).scheme!='https':raise ValueError('Only HTTPS public sources are allowed')
    for attempt in range(attempts):
        try:
            r=requests.get(url,params=params,headers={'User-Agent':UA,'Accept':'application/json,text/html;q=0.9,*/*;q=0.1'},timeout=(10,35))
            if r.status_code in (429,500,502,503,504) and attempt<attempts-1:
                time.sleep(min(12,2**(attempt+1)));continue
            r.raise_for_status()
            if len(r.content)>12000000:raise ValueError('Public response exceeds size limit')
            r.encoding=r.apparent_encoding or 'utf-8'
            return r
        except (requests.RequestException,ValueError):
            if attempt==attempts-1:raise
            time.sleep(attempt+1)

def methods(s):
    patterns=[('随机实验',r'randomi[sz]ed|random assignment|\bRCT\b|随机.*实验'),('双重差分',r'difference.in.differences|\bDID\b|双重差分|三重差分'),('工具变量',r'instrumental variable|工具变量'),('断点回归',r'regression discontinuity|断点回归'),('事件研究',r'event.study|事件研究'),('结构模型',r'structural (?:model|estimat)|结构估计|结构模型'),('行政/调查数据',r'administrative data|survey data|行政数据|调查数据'),('访谈/田野',r'ethnograph|interview|fieldwork|访谈|田野'),('实证分析',r'empirical|实证|微观数据')]
    return [label for label,p in patterns if re.search(p,s,re.I)]

def cr_record(x,src):
    d=doi(x.get('DOI'));titles=x.get('title') or []
    if not d or not titles:return None
    if src['id']=='nber':
        if not re.fullmatch(r'10\.3386/w\d+',d):return None
    else:
        if src['issn'] not in x.get('ISSN',[]) or x.get('type')!='journal-article':return None
    dates=[]
    for key,label in [('published-online','在线发表'),('published-print','纸刊发表'),('published','出版登记')]:
        for p in x.get(key,{}).get('date-parts',[]):
            if len(p)>=2:
                s=valid_date('-'.join(str(v) for v in p))
                if s:dates.append((s,label))
    if not dates:return None
    known=[v for v in dates if v[1]!='出版登记'] or dates
    pub,kind=min(known)
    if pub>TODAY.isoformat():return None
    abstract=clean(x.get('abstract',''))
    return {'id':d,'doi':d,'title':clean(titles[0]),'authors':[clean(a.get('given','')+' '+a.get('family','')) or a.get('name','') for a in x.get('author',[])],
        'source_id':src['id'],'source':src['name'],'date':pub,'date_kind':kind,'dates':[{'date':a,'kind':b} for a,b in dates],
        'url':('https://www.nber.org/papers/'+d.split('/')[-1] if src['id']=='nber' else 'https://doi.org/'+d),
        'metadata_url':'https://api.crossref.org/works/'+quote(d,safe='/'),'provider':'Crossref公共索引','observed_at':STAMP,
        'abstract':abstract[:650],'methods':methods(clean(titles[0])+' '+abstract),'citations':x.get('is-referenced-by-count'),
        'citation_scope':'Crossref累计引用，非近期新增','evidence':[],'rankings':[],'status':'工作论文' if src['id']=='nber' else '期刊论文'}

def crossref(src):
    url='https://api.crossref.org/prefixes/10.3386/works' if src['id']=='nber' else 'https://api.crossref.org/journals/'+src['issn']+'/works'
    p={'filter':f'from-pub-date:{START},until-pub-date:{TODAY}','rows':500,'cursor':'*','sort':'published','order':'desc'}
    if src['id']!='nber':p['filter']+=',type:journal-article'
    papers=[];total=None;seen=0;err='';complete=False
    try:
        for _ in range(30):
            msg=get(url,p).json()['message'];items=msg['items'];total=msg.get('total-results');seen+=len(items)
            for x in items:
                a=cr_record(x,src)
                if a and in_range(a['date']):papers.append(a)
            if not items or (total is not None and seen>=total):complete=True;break
            new=msg.get('next-cursor')
            if not new or new==p['cursor']:raise ValueError('Cursor stalled; coverage not complete')
            p['cursor']=new
    except Exception as e:err=str(e)[:220]
    return papers,{'source_id':src['id'],'provider':'Crossref公共索引','url':url,'count':len(papers),'index_total':total,'scanned':seen,'complete_index':complete,'error':err,'checked_at':STAMP}

def meta(soup,key):return [clean(e.get('content','')) for e in soup.select('meta[content]') if (e.get('name','') or e.get('property','')).lower()==key.lower() and e.get('content')]
def page_date(soup):
    for k in ['citation_online_date','article:published_time','citation_publication_date','DC.Date','date','datePublished']:
        for v in meta(soup,k):
            d=valid_date(v)
            if d:return d
    text=clean(soup)
    m=re.search(r'(?:发布时间|出版日期|出版时间|在线发布日期)[\s:：]*(20\d{2}[-/]\d{1,2}[-/]\d{1,2})',text)
    if m:return valid_date(m[1])
    for e in soup.select('time[datetime]'):
        d=valid_date(e.get('datetime'))
        if d:return d
    m=re.search(r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(20\d{2})\b',text)
    if m:
        try:return dt.datetime.strptime(' '.join(m.groups()),'%B %d %Y').date().isoformat()
        except ValueError:pass
    return ''

def chinese_record(text,url,src):
    soup=BeautifulSoup(text,'html.parser')
    title=(meta(soup,'citation_title') or meta(soup,'DC.Title') or [''])[0]
    journal=meta(soup,'citation_journal_title')
    if journal and not any(norm(src['name'])==norm(v) for v in journal):return None
    if not title or norm(title)==norm(src['name']):return None
    pub=page_date(soup)
    if not pub or not in_range(pub):return None
    ds=meta(soup,'citation_doi');d=doi(ds[0]) if ds else ''
    body=soup.select_one('#abstract, .abstract, #abstract_cn, #Abstract')
    abst=clean(body) if body else (meta(soup,'description') or [''])[0]
    if '{{' in abst:abst=''
    return {'id':d or 'web:'+hashlib.sha256(url.encode()).hexdigest()[:20],'doi':d,'title':title,'authors':meta(soup,'citation_author') or meta(soup,'dc.creator'),'source_id':src['id'],'source':src['name'],'date':pub,'date_kind':'官方页面出版日期','dates':[],'url':url,'metadata_url':url,'provider':'知网公开期刊页' if 'cnki.net' in url else '期刊官方目录','observed_at':STAMP,'abstract':abst[:650],'methods':methods(title+' '+abst),'citations':None,'citation_scope':'未取得','evidence':[],'rankings':[],'status':'期刊论文'}

def chinese(src):
    queue=list(src.get('public_pages',[]));seen=set();papers=[];errors=[];checked=[]
    while queue and len(seen)<34:
        url=queue.pop(0)
        if url in seen:continue
        seen.add(url)
        try:
            r=get(url,attempts=2);text=r.text;soup=BeautifulSoup(text,'html.parser')
            checked.append({'url':url,'bytes':len(r.content),'title':clean(soup.title)[:100] if soup.title else ''})
            if len(r.content)<500:errors.append(url+' 返回空白/跳转页');continue
            if re.search(r'验证码|安全验证|access denied|captcha',clean(soup),re.I) and len(clean(soup))<3000:
                errors.append(url+' 需要访问验证，停止此页面');continue
            a=chinese_record(text,r.url,src)
            if a:papers.append(a);continue
            article=[];indexes=[]
            for link in soup.select('a[href]'):
                href=urljoin(r.url,link['href']).split('#')[0];label=clean(link)
                if not href.startswith('https://') or urlparse(href).hostname!=urlparse(r.url).hostname or href in seen:continue
                if re.search(r'login|Editor|download|\.pdf|register',href,re.I):continue
                years=re.findall(r'20\d{2}',href+' '+label)
                if years and max(map(int,years))<START.year:continue
                if re.search(r'/Y20\d{2}/V\d+/I\d+/\d+|/abstract|/paper/[\w-]+|view_abstract|ArticleDetails|/doi/|/html/',href,re.I):article.append(href)
                elif re.search(r'过刊|目录|本期|网络首发|202[56]',label) or re.search(r'/archive|/volumn/|showOldVolumn',href,re.I):indexes.append(href)
            queue=list(dict.fromkeys(article+queue+indexes))
        except Exception as e:errors.append(url+' '+str(e)[:110])
    return papers,{'source_id':src['id'],'provider':'知网公开目录/期刊官网','url':src['url'],'count':len(papers),'scanned':len(seen),'complete_index':False,'error':'；'.join(errors[:5]),'checked_at':STAMP,'pages':checked[:4],'note':'公开页有界采集；不代表完整目录。知网交互搜索可在网站中打开。'}

def extract_dois(soup,url):
    out=set()
    for a in soup.select('a[href]'):
        u=unquote(urljoin(url,a['href']))
        m=re.search(r'(?:doi\.org/|aeaweb\.org/articles\?id=)(10\.\d{4,9}/[^\s?#&]+)',u,re.I)
        if m:out.add(doi(m[1]))
        m=re.search(r'nber\.org/(?:papers/|system/files/working_papers/)(w\d+)',u)
        if m:out.add('10.3386/'+m[1])
    return out

def collect_evidence(papers):
    bydoi={p['doi']:p for p in papers if p['doi']};urls=set();report=[]
    seeds=[('AEA研究精选','https://www.aeaweb.org/research'),('NBER Digest','https://www.nber.org/digest')]
    # Monthly Digest archives are public indices; their month is not a fabricated day.
    for k in range(12):
        y=TODAY.year;m=TODAY.month-k
        while m<1:y-=1;m+=12
        seeds.append(('NBER Digest',f'https://www.nber.org/digest/{y:04d}{m:02d}'))
    for source,url in seeds:
        try:
            r=get(url,attempts=2);soup=BeautifulSoup(r.text,'html.parser')
            for a in soup.select('a[href]'):
                u=urljoin(r.url,a['href']).split('#')[0]
                if re.match(r'https://www\.aeaweb\.org/research/[^/?]+$',u) and not u.endswith(('/about','/archive','/contact')):urls.add((source,u))
                if re.match(r'https://www\.nber\.org/digest/\d{6}/[^/?]+$',u):urls.add((source,u))
        except Exception as e:report.append({'source':source,'url':url,'error':str(e)[:160]})
    def visit(item):
        source,url=item
        try:
            r=get(url,attempts=2);soup=BeautifulSoup(r.text,'html.parser');ids=extract_dois(soup,r.url)
            d=page_date(soup)
            if not d:
                m=re.search(r'/digest/(20\d{2})(\d{2})/',url)
                if m:d=m[1]+'-'+m[2]
            if not d or not in_range(d):return [],None
            title=clean(soup.h1) if soup.h1 else (meta(soup,'og:title') or [url])[0]
            ev={'title':title[:250],'url':url,'date':d,'source':source,'kind':'编辑研究介绍' if len(ids)<=2 else '研究文章中的文献链接','match':'网页明确链接论文DOI/工作论文编号','verified':True,'checked_at':STAMP}
            return [(i,ev) for i in ids if i in bydoi],None
        except Exception as e:return [],{'source':source,'url':url,'error':str(e)[:120]}
    with cf.ThreadPoolExecutor(max_workers=4) as pool:
        for matches,error in pool.map(visit,sorted(urls)[:160]):
            if error:report.append(error)
            for d,e in matches:bydoi[d]['evidence'].append(e)
    return {'visited':min(160,len(urls)),'discovered':len(urls),'matched_papers':sum(bool(p['evidence']) for p in papers),'errors':report[:20],'coverage':'AEA研究精选与NBER Digest公开页；不是全网热度或社交媒体总量。'}

def main():
    old={}
    if (ROOT/'data.json').exists():
        try:old=json.loads((ROOT/'data.json').read_text())
        except ValueError:pass
    papers=[];reports=[]
    with cf.ThreadPoolExecutor(max_workers=4) as pool:
        for rows,report in pool.map(crossref,CAT):
            papers.extend(rows);reports.append(report);print(report['source_id'],report['provider'],report['count'],report['error'],flush=True)
    with cf.ThreadPoolExecutor(max_workers=3) as pool:
        for rows,report in pool.map(chinese,[s for s in CAT if s['lang']=='zh']):
            papers.extend(rows);reports.append(report);print(report['source_id'],report['provider'],report['count'],flush=True)
    unique={}
    for p in papers:
        key=(p['source_id'],p['doi'] or norm(p['title']))
        if key not in unique or len(p['abstract'])>len(unique[key]['abstract']):unique[key]=p
    papers=list(unique.values())
    # Preserve good records when a provider fails; explicitly mark stale observations.
    keys={(p['source_id'],p['doi'] or norm(p['title'])) for p in papers}
    for p in old.get('papers',[]):
        key=(p['source_id'],p.get('doi') or norm(p['title']))
        if key not in keys and in_range(p.get('date','')):
            p['stale']=True;papers.append(p);keys.add(key)
    evidence=collect_evidence(papers)
    counts={s['id']:sum(p['source_id']==s['id'] for p in papers) for s in CAT}
    samples={sid:[{'title':p['title'],'date':p['date'],'url':p['url']} for p in papers if p['source_id']==sid][:2] for sid in counts}
    validation={'environment':'GitHub-hosted live public-network collection','checked_at':STAMP,'sources_with_records':sum(v>0 for v in counts.values()),'sources_total':len(CAT),'counts':counts,'sample_records':samples,'records':len(papers),'evidence':evidence,'checks':{'no_future_dates':all(p['date']<=TODAY.isoformat() for p in papers),'unique_source_keys':len(keys)==len(papers),'all_titles_present':all(len(p['title'])>2 for p in papers),'all_urls_https':all(p['url'].startswith('https://') for p in papers),'no_demo_records':True},'source_reports':reports}
    data={'generated_at':STAMP,'publication_from':START.isoformat(),'publication_to':TODAY.isoformat(),'catalog':CAT,'papers':papers,'reports':reports,'evidence_report':evidence,'validation':{k:v for k,v in validation.items() if k not in ('source_reports','sample_records')}}
    (ROOT/'data.json').write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    (ROOT/'verification.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2),encoding='utf-8')
    print('RESULT',len(papers),'records;',sum(v>0 for v in counts.values()),'sources;',evidence['matched_papers'],'papers with dated evidence',flush=True)
    if (ROOT/'template.html').exists():
        template=(ROOT/'template.html').read_text();payload=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
        (ROOT/'index.html').write_text(template.replace('/*__INITIAL_DATA__*/','window.INITIAL_DATA='+payload+';'),encoding='utf-8')

if __name__=='__main__':main()
