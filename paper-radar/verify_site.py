"""Browser acceptance uses the real collected dataset, never demo paper results."""
import json, pathlib, subprocess, time, threading, http.server, os, datetime, csv, io
from playwright.sync_api import sync_playwright
ROOT=pathlib.Path(__file__).parent.resolve()
checks=[]
def check(name,condition,detail=''):
    checks.append({'name':name,'passed':bool(condition),'detail':detail});print(name,bool(condition),detail,flush=True)
def main():
    data=json.loads((ROOT/'data.json').read_text());papers=data['papers']
    check('real_index_nonempty',len(papers)>0,str(len(papers)))
    check('catalog_has_36_sources',len(data['catalog'])==36)
    check('no_future_publication_dates',all(p['date']<=data['publication_to'] for p in papers))
    check('known_AER_DOI_and_title',any(p['doi']=='10.1257/aer.20231016' and 'Florida Wetlands' in p['title'] for p in papers))
    check('NBER_only_working_paper_DOIs',all(p['doi'].startswith('10.3386/w') for p in papers if p['source_id']=='nber'))
    check('source_identifiers_present',all(p['source_id'] in {s['id'] for s in data['catalog']} for p in papers))
    check('no_unknown_publication_dates',all(p['date'] for p in papers))
    server=http.server.ThreadingHTTPServer(('127.0.0.1',8765),lambda *a,**kw:http.server.SimpleHTTPRequestHandler(*a,directory=str(ROOT),**kw))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    with sync_playwright() as pw:
        browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True)
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:8765/index.html');page.wait_for_function('window.PaperRadar && PaperRadar.getData() && document.querySelectorAll("[data-source]").length===36')
        check('browser_loads_real_records',page.locator('.paper').count()>0)
        check('all_source_checkboxes_present',page.locator('[data-source]').count()==36)
        check('default_results_only_top5_NBER',page.evaluate('PaperRadar.getRows().every(p=>["aer","qje","jpe","ecta","restud","nber"].includes(p.source_id))'))
        page.screenshot(path=str(ROOT/'desktop.png'),full_page=False)
        check('seven_day_boundary',page.evaluate('PaperRadar.startDate("2026-10-24","7")==="2026-10-18"'))
        check('thirty_day_boundary',page.evaluate('PaperRadar.startDate("2026-10-24","30")==="2026-09-25"'))
        check('half_year_boundary',page.evaluate('PaperRadar.startDate("2026-10-24","6m")==="2026-04-24"'))
        check('year_only_excluded_by_default',page.evaluate('!PaperRadar.dateMatches("2026","2026-10-18","2026-10-24",false)'))
        check('CSV_formula_injection_protected',page.evaluate('PaperRadar.csvCell("=1+1").includes("\u0027=1+1")'))
        page.locator('#keyword').fill('Conservation Priorities');page.locator('#search').click()
        check('exact_paper_keyword_search',page.evaluate('PaperRadar.getRows().length>=1 && PaperRadar.getRows().every(p=>p.title.includes("Conservation Priorities"))'))
        if page.locator('.paper').count():
            page.locator('[data-favorite]').first.click();page.locator('#favorites').click();check('favorites_filter',page.locator('.paper').count()>=1);page.locator('#favorites').click()
            with page.expect_download() as d:page.locator('#exportCsv').click()
            download=d.value;txt=pathlib.Path(download.path()).read_text(encoding='utf-8-sig');csvrows=list(csv.reader(io.StringIO(txt)))
            check('CSV_export_has_real_title_and_DOI',len(csvrows)>1 and any('10.1257/aer.20231016' in x for x in csvrows[1]))
            with page.expect_download() as d:page.locator('#exportRis').click()
            check('RIS_export_real_paper','10.1257/aer.20231016' in pathlib.Path(d.value.path()).read_text())
        page.locator('#keyword').fill('');page.locator('#pubWindow').select_option('7');page.locator('#search').click()
        check('seven_day_results_obey_filter',page.evaluate('PaperRadar.getRows().every(p=>PaperRadar.dateMatches(p.date,PaperRadar.startDate(document.getElementById("endDate").value,"7"),document.getElementById("endDate").value,false))'))
        page.locator('#pubWindow').select_option('1y');page.locator('#onlyEvidence').check();page.locator('#search').click()
        check('evidence_only_filter',page.evaluate('PaperRadar.getRows().every(p=>p.evidence.some(e=>e.verified&&PaperRadar.dateMatches(e.date,PaperRadar.startDate(document.getElementById("endDate").value,"30"),document.getElementById("endDate").value,false)))'))
        page.locator('#onlyEvidence').uncheck();page.locator('[data-preset="zh"]').click();page.locator('#search').click()
        check('Chinese_selection_is_strict',page.evaluate('PaperRadar.getRows().every(p=>PaperRadar.getData().catalog.find(s=>s.id===p.source_id).lang==="zh")'))
        page.locator('#cnkiGuide').click();check('CNKI_guide_and_import_available',page.locator('#dialog').is_visible() and page.locator('#dialogBody').inner_text().find('Refworks')>=0);page.locator('#closeDialog').click()
        page.locator('#coverage').click();check('coverage_report_available',page.locator('#dialog').is_visible() and page.locator('#dialogBody tr').count()>=37);page.locator('#closeDialog').click()
        page.locator('#help').click();check('usage_tutorial_available',page.locator('#dialogBody').inner_text().find('累计引用')>=0);page.locator('#closeDialog').click()
        realzh=next((p for p in papers if any(s['id']==p['source_id'] and s['lang']=='zh' for s in data['catalog'])),None)
        if realzh:
            exported='RT Journal Article\nT1 '+realzh['title']+'\nJF '+realzh['source']+'\nYR '+realzh['date'][:4]+'\nA1 '+';'.join(realzh['authors'])+'\n'
            parsed=page.evaluate('t=>PaperRadar.parseImport(t)',exported)
            check('CNKI_Refworks_parse_of_real_record',len(parsed)==1 and parsed[0]['title']==realzh['title'] and parsed[0]['date']==realzh['date'][:4])
        page.locator('[data-preset="six"]').click();page.locator('#search').click();page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(ROOT/'mobile.png'),full_page=True)
        check('mobile_no_horizontal_overflow',page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1'))
        check('no_browser_runtime_errors',not errors,';'.join(errors))
        context.close();browser.close()
    server.shutdown()
    report={'tested_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'uses_real_collected_records':True,'passed':sum(c['passed'] for c in checks),'total':len(checks),'checks':checks}
    (ROOT/'browser-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    if not all(c['passed'] for c in checks):raise SystemExit('Browser/content acceptance failed')
if __name__=='__main__':main()
