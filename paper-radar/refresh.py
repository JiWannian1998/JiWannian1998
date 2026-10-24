"""Repair public-source collection without any Vercel or subscription dependency.

Crossref rejects publication-date sorting combined with cursor pagination.
Filter publication dates on the server, paginate without that sort, and sort
locally in the website. A cursor token can remain constant between pages.
"""
from __future__ import annotations
import concurrent.futures as cf
import json
import os
import re
import sys
import threading
import time
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import collect as c

_original_get = c.get
_crossref_lock = threading.Lock()

def throttled_get(url, params=None, attempts=3):
    if urlparse(url).hostname == 'api.crossref.org':
        with _crossref_lock:
            try:
                return _original_get(url, params=params, attempts=attempts)
            finally:
                time.sleep(0.35)
    return _original_get(url, params=params, attempts=attempts)

c.get = throttled_get

def crossref(src):
    url = ('https://api.crossref.org/prefixes/10.3386/works' if src['id'] == 'nber'
           else 'https://api.crossref.org/journals/' + src['issn'] + '/works')
    params = {'filter': f'from-pub-date:{c.START},until-pub-date:{c.TODAY}',
              'rows': 500, 'cursor': '*'}
    if src['id'] != 'nber':
        params['filter'] += ',type:journal-article'
    papers, known, pages = [], set(), set()
    total, scanned, complete, error = None, 0, False, ''
    try:
        for _ in range(30):
            response = c.get(url, params).json()
            message = response['message']
            items = message['items']
            total = message.get('total-results')
            scanned += len(items)
            fingerprint = tuple(x.get('DOI', '') for x in items)
            if items and fingerprint in pages:
                raise ValueError('Repeated result page: incomplete coverage')
            pages.add(fingerprint)
            for item in items:
                record = c.cr_record(item, src)
                if record and c.in_range(record['date']) and record['doi'] not in known:
                    papers.append(record)
                    known.add(record['doi'])
            if len(items) < params['rows'] or (total is not None and scanned >= total):
                complete = True
                break
            token = message.get('next-cursor')
            if not token:
                raise ValueError('Missing next cursor: incomplete coverage')
            params['cursor'] = token
    except Exception as exc:
        error = str(exc)[:400]
    return papers, {'source_id': src['id'], 'provider': 'Crossref公共索引',
                    'url': url, 'count': len(papers), 'index_total': total,
                    'scanned': scanned, 'complete_index': complete,
                    'error': error, 'checked_at': c.STAMP}

c.crossref = crossref

def collect_evidence(papers):
    bydoi = {p['doi']: p for p in papers if p.get('doi')}
    # Follow links actually published by the sources; do not invent archive URLs.
    queue = [('AEA研究精选', 'https://www.aeaweb.org/research'),
             ('NBER Digest', 'https://www.nber.org/digest')]
    seen, articles, errors = set(), set(), []
    while queue and len(seen) < 16:
        source, url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            response = c.get(url, attempts=2)
            soup = BeautifulSoup(response.text, 'html.parser')
            for a in soup.select('a[href]'):
                href = urljoin(response.url, a['href']).split('#')[0]
                parts = urlparse(href)
                if parts.scheme != 'https':
                    continue
                if parts.hostname == 'www.aeaweb.org':
                    if re.fullmatch(r'/research/[^/]+', parts.path) and parts.path not in ('/research/about', '/research/archive', '/research/contact'):
                        articles.add((source, href))
                    elif parts.path in ('/research', '/research/archive') and href not in seen:
                        queue.append((source, href))
                elif parts.hostname == 'www.nber.org':
                    if re.fullmatch(r'/digest/\d{6}/[^/]+', parts.path):
                        articles.add((source, href))
                    elif parts.path.startswith('/digest') and not re.search(r'\.pdf$|subscribe|download', href, re.I) and href not in seen:
                        queue.append((source, href))
        except Exception as exc:
            errors.append({'source': source, 'url': url, 'error': str(exc)[:180]})
    def visit(item):
        source, url = item
        try:
            response = c.get(url, attempts=2)
            soup = BeautifulSoup(response.text, 'html.parser')
            ids = c.extract_dois(soup, response.url)
            date = c.page_date(soup)
            if not date:
                match = re.search(r'/digest/(20\d{2})(\d{2})/', url)
                if match:
                    date = match[1] + '-' + match[2]
            if not date or not c.in_range(date):
                return [], None
            title = c.clean(soup.h1) if soup.h1 else (c.meta(soup, 'og:title') or [url])[0]
            ev = {'title': title[:250], 'url': url, 'date': date,
                  'source': source,
                  'kind': '编辑研究介绍' if len(ids) <= 2 else '研究文章中的文献链接',
                  'match': '网页明确链接论文DOI/工作论文编号', 'verified': True,
                  'checked_at': c.STAMP}
            return [(d, ev) for d in ids if d in bydoi], None
        except Exception as exc:
            return [], {'source': source, 'url': url, 'error': str(exc)[:180]}
    urls = sorted(articles)[:80]
    with cf.ThreadPoolExecutor(max_workers=3) as pool:
        for matches, error in pool.map(visit, urls):
            if error:
                errors.append(error)
            for d, evidence in matches:
                row = bydoi[d]
                if not any(e.get('url') == evidence['url'] for e in row['evidence']):
                    row['evidence'].append(evidence)
    return {'visited': len(urls), 'discovered': len(articles),
            'matched_papers': sum(bool(p['evidence']) for p in papers),
            'errors': errors[:20],
            'coverage': '只采集AEA研究精选与NBER Digest实际公开链接；有界扫描，不是全网热度。'}

c.collect_evidence = collect_evidence

if __name__ == '__main__':
    if '--reuse-chinese' in sys.argv:
        cached = json.loads((c.ROOT / 'data.json').read_text(encoding='utf-8'))
        def cached_chinese(src):
            rows = [p for p in cached.get('papers', []) if p['source_id'] == src['id'] and c.in_range(p.get('date', ''))]
            report = next((dict(r) for r in cached.get('reports', []) if r['source_id'] == src['id']),
                          {'source_id': src['id'], 'provider': '先前公开目录采集', 'url': src['url'], 'error': '未取得'})
            report.update(count=len(rows), reused_snapshot=True,
                          note='本轮修复英文索引；中文复用此前实采记录，未重新抓取，不代表完整目录。')
            return rows, report
        c.chinese = cached_chinese
    c.main()
