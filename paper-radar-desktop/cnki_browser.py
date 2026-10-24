"""Off-the-record CNKI browser. No CAPTCHA bypass, cookies export or password access."""
import json
from urllib.parse import urlparse
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QPushButton,QLabel,QLineEdit,QMessageBox
from PySide6.QtWebEngineCore import QWebEnginePage,QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
import engine as E
CAPTURE_JS=r'''(() => {
 const clean=x=>(x?.innerText||x?.textContent||'').replace(/\s+/g,' ').trim();
 const rows=[...document.querySelectorAll('table.result-table-list tbody tr, table.result-table-list tr, .result-table-list tbody tr, .result-table-list > li')];
 const out=[];
 for(const row of rows.slice(0,300)) {
  const a=row.querySelector('.name a[href], a.fz14[href], .title a[href]');
  if(!a)continue;
  const source=row.querySelector('.source a, .source');
  const authors=[...row.querySelectorAll('.author a')].map(clean).filter(Boolean);
  if(!authors.length)authors.push(...clean(row.querySelector('.author')).split(/[;；、]/).filter(Boolean));
  out.push({title:clean(a),url:a.href,source:clean(source),authors,date:clean(row.querySelector('.date')),citations:clean(row.querySelector('.quote')),downloads:clean(row.querySelector('.download'))});
 }
 return JSON.stringify({url:location.href,title:document.title,rows:out});
})()'''
class Page(QWebEnginePage):
 def createWindow(self,kind):return self
 def acceptNavigationRequest(self,url,kind,is_main):
  if url.scheme() not in ('http','https','about'):return False
  return super().acceptNavigationRequest(url,kind,is_main)
class CNKIBrowser(QDialog):
 def __init__(self,catalog,selected,callback,parent=None):
  super().__init__(parent);self.setWindowTitle('知网辅助检索 · 正常访问后读取当前题录');self.resize(1280,850);self.callback=callback;layout=QVBoxLayout(self)
  names=[s['name'] for s in catalog if s['language']=='zh' and s['id'] in selected]
  message=QLabel('在知网高级检索设置“来源期刊”和日期。页面正常显示结果后，点击“采集当前页”。\n验证码/登录由你在原站正常操作；程序不绕过限制，也不采集密码。部分题录只有年份，窄时间窗口可能排除。');message.setWordWrap(True);layout.addWidget(message)
  if names:
   names_label=QLabel('已选中文刊物：'+'、'.join(names));names_label.setWordWrap(True);layout.addWidget(names_label)
  tools=QHBoxLayout();self.address=QLineEdit(E.CNKI_URL);tools.addWidget(self.address,1);go=QPushButton('访问');go.clicked.connect(self.navigate);tools.addWidget(go);system=QPushButton('系统浏览器');system.clicked.connect(lambda:QDesktopServices.openUrl(QUrl(self.address.text())) if E.safe_url(self.address.text()) else None);tools.addWidget(system);capture=QPushButton('采集当前页题录');capture.setObjectName('primary');capture.clicked.connect(self.capture);tools.addWidget(capture);layout.addLayout(tools)
  self.profile=QWebEngineProfile(self);self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies);self.view=QWebEngineView(self);self.page=Page(self.profile,self.view);self.view.setPage(self.page);layout.addWidget(self.view,1);self.status=QLabel('仅当前用户主动采集的题录会保存在本地。');layout.addWidget(self.status)
  self.view.urlChanged.connect(lambda u:self.address.setText(u.toString()));self.view.loadFinished.connect(lambda ok:self.status.setText('页面已加载；请核对期刊和时间后采集。' if ok else '页面未能加载。可使用系统浏览器，并将合法导出的题录导入应用。'));self.view.setUrl(QUrl(E.CNKI_URL));self.address.returnPressed.connect(self.navigate)
 def navigate(self):
  u=self.address.text().strip()
  if E.safe_url(u):self.view.setUrl(QUrl(u))
 def capture(self):
  host=urlparse(self.view.url().toString()).hostname or ''
  if not (host=='cnki.net' or host.endswith('.cnki.net') or host.endswith('.cnki.com.cn')):QMessageBox.information(self,'只读取知网题录','请在知网正式检索结果页使用。');return
  self.page.runJavaScript(CAPTURE_JS,self.got)
 def got(self,result):
  try:data=json.loads(result or '{}');rows=data.get('rows',[])
  except (ValueError,TypeError):rows=[]
  if not rows:QMessageBox.information(self,'没有识别到当前页题录','请确认已经显示知网的检索结果表格，而不是首页、登录或验证页。\n页面结构不匹配时，请使用知网正常导出功能，并在主界面导入题录；不会以空结果冒充成功。');return
  self.callback(rows);self.status.setText(f'读取当前页 {len(rows)} 行；可正常翻页后再次采集。')
