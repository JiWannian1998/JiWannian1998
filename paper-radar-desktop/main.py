"""Paper Radar native Windows application. No local web server or external account."""
from __future__ import annotations
import argparse,html,json,os,sys,threading,traceback
from datetime import date
from pathlib import Path
import engine as E
ROOT=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
CAT=json.loads((ROOT/'catalog.json').read_text(encoding='utf-8'))
for src in CAT:
 if src['id']=='ecta':src['extra_issns']=['1468-0262']
STYLE='''
QWidget {font-family:"Microsoft YaHei UI","Segoe UI",sans-serif;font-size:13px;color:#253c3a;}
QMainWindow,QDialog {background:#f4f6f3;}
QFrame#hero {background:#123d38;border-radius:12px;}
QLabel#brand {color:white;font-size:25px;font-weight:700;}
QLabel#subtitle {color:#b7d2ca;font-size:12px;}
QLabel#heading {color:#123d38;font-size:17px;font-weight:650;}
QLabel#muted {color:#667d77;}
QGroupBox {background:white;border:1px solid #d9e3dd;border-radius:9px;margin-top:13px;padding:15px 11px 10px;font-weight:600;}
QGroupBox::title {subcontrol-origin:margin;left:12px;padding:0 6px;}
QPushButton {background:white;border:1px solid #cddbd2;border-radius:6px;padding:7px 11px;min-height:19px;}
QPushButton:hover {background:#e7f1ec;border-color:#5c9a87;}
QPushButton:disabled {color:#9ca8a3;background:#f0f3f0;}
QPushButton#primary {background:#176957;color:white;border-color:#176957;font-weight:650;padding:10px 15px;}
QPushButton#primary:hover {background:#125241;}
QComboBox,QLineEdit,QDateEdit {background:white;border:1px solid #cddbd2;border-radius:5px;min-height:23px;padding:4px 8px;}
QTreeWidget,QTableWidget,QTextBrowser,QPlainTextEdit {background:white;border:1px solid #d9e3dd;border-radius:7px;}
QTreeWidget::item {padding:5px 0;}
QTreeWidget::item:selected,QTableWidget::item:selected {background:#d9eee3;color:#123d38;}
QHeaderView::section {background:#edf3ee;border:0;border-bottom:1px solid #d9e3dd;padding:8px;color:#4f6960;}
QTableWidget {alternate-background-color:#fafcf9;gridline-color:#edf1ed;}
QTableWidget::item {padding:9px;}
QTabWidget::pane {border:1px solid #d9e3dd;background:white;border-radius:7px;}
QTabBar::tab {padding:9px 18px;background:#e9efe9;}
QTabBar::tab:selected {background:white;color:#176957;}
QProgressBar {border:0;background:#e3ebe5;height:5px;border-radius:2px;}
QProgressBar::chunk {background:#4f9f7c;}
QCheckBox {spacing:6px;}
QSplitter::handle {background:#e3e9e3;}
'''
def app_main(argv=None):
 from PySide6.QtCore import Qt,QThread,Signal,QTimer,QDate,QUrl
 from PySide6.QtGui import QFont,QDesktopServices
 from PySide6.QtWidgets import QApplication,QMainWindow,QWidget,QFrame,QLabel,QPushButton,QVBoxLayout,QHBoxLayout,QGridLayout,QGroupBox,QComboBox,QLineEdit,QCheckBox,QTreeWidget,QTreeWidgetItem,QSplitter,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QTextBrowser,QPlainTextEdit,QTabWidget,QFileDialog,QMessageBox,QDialog,QProgressBar,QDateEdit
 parser=argparse.ArgumentParser();parser.add_argument('--self-test',action='store_true');parser.add_argument('--report-dir',default='verification');parser.add_argument('--test-records',default='');parser.add_argument('--data-dir',default='');args=parser.parse_args(argv)
 if args.data_dir:os.environ['PAPERRADAR_DATA']=args.data_dir
 QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
 app=QApplication(sys.argv[:1]);app.setApplicationName('Paper Radar');app.setOrganizationName('PaperRadar');app.setStyle('Fusion');app.setStyleSheet(STYLE);app.setFont(QFont('Microsoft YaHei UI',10))
 class SearchWorker(QThread):
  progress=Signal(str);partial=Signal(object,object);result=Signal(object,object);failed=Signal(str)
  def __init__(self,q,store):super().__init__();self.q=q;self.store=store;self.cancel=threading.Event()
  def run(self):
   try:p,r=E.search(CAT,self.q,self.store,self.progress.emit,self.partial.emit,self.cancel);self.result.emit(p,r)
   except Exception:self.failed.emit(traceback.format_exc())
 class MainWindow(QMainWindow):
  def __init__(self):
   super().__init__();self.setWindowTitle('论文雷达 · Paper Radar Desktop '+E.VERSION);self.resize(1460,930);self.setMinimumSize(1050,720)
   self.store=E.Store();self.records=self.store.papers();self.visible=[];self.report={};self.worker=None;self.pending_close=False;self.cnki=None
   root=QWidget();self.setCentralWidget(root);outer=QVBoxLayout(root);outer.setContentsMargins(18,15,18,12);outer.setSpacing(12)
   hero=QFrame();hero.setObjectName('hero');hl=QHBoxLayout(hero);hl.setContentsMargins(18,14,18,14);bl=QVBoxLayout();brand=QLabel('论文雷达  /  PAPER RADAR');brand.setObjectName('brand');bl.addWidget(brand);sub=QLabel('免费公开来源  ·  本地收藏  ·  可核查的入选证据');sub.setObjectName('subtitle');bl.addWidget(sub);hl.addLayout(bl);hl.addStretch()
   guide=QPushButton('使用说明');guide.clicked.connect(self.help);hl.addWidget(guide);data_btn=QPushButton('本地数据');data_btn.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.root))));hl.addWidget(data_btn);outer.addWidget(hero)
   split=QSplitter(Qt.Orientation.Horizontal);outer.addWidget(split,1);left=QWidget();ll=QVBoxLayout(left);ll.setContentsMargins(0,0,8,0);left.setMinimumWidth(260);left.setMaximumWidth(350);hd=QLabel('01  选择期刊与工作论文');hd.setObjectName('heading');ll.addWidget(hd);quick=QHBoxLayout()
   for label,which in [('五大刊＋NBER','top'),('中文九刊','cn'),('清空','none')]:
    b=QPushButton(label);b.clicked.connect(lambda checked=False,w=which:self.select_group(w));quick.addWidget(b)
   ll.addLayout(quick);self.tree=QTreeWidget();self.tree.setHeaderHidden(True);self.tree.setIndentation(15);self.items={};groups={};selected=self.store.setting('selected',list(E.TOP_IDS))
   for src in CAT:
    if src['group'] not in groups:
     item=QTreeWidgetItem([src['group']]);item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable|Qt.ItemFlag.ItemIsAutoTristate);item.setCheckState(0,Qt.CheckState.Unchecked);self.tree.addTopLevelItem(item);groups[src['group']]=item
    item=QTreeWidgetItem([src['short']]);item.setData(0,Qt.ItemDataRole.UserRole,src['id']);item.setToolTip(0,src['name']+'\n'+('知网正常浏览＋官网题录，部分来源需辅助访问' if src['language']=='zh' else 'Crossref公共元数据，不要求API密钥'));item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(0,Qt.CheckState.Checked if src['id'] in selected else Qt.CheckState.Unchecked);groups[src['group']].addChild(item);self.items[src['id']]=item
   self.tree.expandAll();ll.addWidget(self.tree,1);self.selected_label=QLabel();self.selected_label.setObjectName('muted');ll.addWidget(self.selected_label);self.tree.itemChanged.connect(self.selection_changed);self.selection_changed()
   cn=QPushButton('知网辅助检索 / 采集当前结果');cn.clicked.connect(self.open_cnki);ll.addWidget(cn);imp=QPushButton('导入 RIS / EndNote / JSON 题录');imp.clicked.connect(self.import_records);ll.addWidget(imp);note=QLabel('中文公开题录不等于付费全文。\n遇到验证时正常操作，不绕过访问限制。');note.setWordWrap(True);note.setObjectName('muted');ll.addWidget(note);split.addWidget(left)
   right=QWidget();rl=QVBoxLayout(right);rl.setContentsMargins(8,0,0,0);filters=QGroupBox('02  定义近期与关注窗口');grid=QGridLayout(filters)
   def combo(options):
    c=QComboBox()
    for label,value in options:c.addItem(label,value)
    return c
   self.clock=combo([('近期发表＋查看关注证据','publication'),('近期有关注证据（近一年候选）','attention'),('发表与关注同时满足','both')]);self.window=combo([('近7天','7d'),('近30天','30d'),('近半年','6m'),('近1年','1y')]);self.window.setCurrentIndex(3);self.att=combo([('近7天','7d'),('近30天','30d'),('近半年','6m'),('近1年','1y')]);self.att.setCurrentIndex(1);self.end=QDateEdit(QDate.currentDate());self.end.setCalendarPopup(True);self.end.setDisplayFormat('yyyy-MM-dd')
   for col,(label,widget) in enumerate([('时间口径',self.clock),('论文发表窗口',self.window),('关注证据窗口',self.att),('截至日期',self.end)]):grid.addWidget(QLabel(label),0,col);grid.addWidget(widget,1,col)
   self.keywords=QLineEdit();self.keywords.setPlaceholderText('可选：标题、摘要、作者中筛选关键词，不需要先知道论文名称');self.sort=combo([('已核验关注证据优先','attention'),('最新发表优先','recent'),('累计引用优先（非近期热度）','citations')]);self.empirical=combo([('实证方法线索优先','prefer'),('不限制研究类型','all'),('仅显示有实证方法线索','only')]);grid.addWidget(self.keywords,2,0,1,2);grid.addWidget(self.sort,2,2);grid.addWidget(self.empirical,2,3)
   self.evidence=QCheckBox('联网核对公开关注证据');self.evidence.setChecked(True);self.uncertain=QCheckBox('保留日期精度不足的重叠记录');self.cache=QCheckBox('使用6小时网络缓存');self.cache.setChecked(True);opts=QHBoxLayout();opts.addWidget(self.evidence);opts.addWidget(self.uncertain);opts.addWidget(self.cache);opts.addStretch();grid.addLayout(opts,3,0,1,4)
   actions=QHBoxLayout();self.search_btn=QPushButton('联网搜索论文');self.search_btn.setObjectName('primary');self.search_btn.clicked.connect(self.start_search);actions.addWidget(self.search_btn);self.stop=QPushButton('停止');self.stop.setEnabled(False);self.stop.clicked.connect(self.stop_search);actions.addWidget(self.stop);local=QPushButton('筛选本地已取得数据');local.clicked.connect(self.apply);actions.addWidget(local);actions.addStretch();self.saved=QCheckBox('只看我的收藏');self.saved.toggled.connect(self.apply);actions.addWidget(self.saved);exp=QPushButton('导出当前清单');exp.clicked.connect(self.export);actions.addWidget(exp);grid.addLayout(actions,4,0,1,4);rl.addWidget(filters)
   self.summary=QLabel('03  单篇候选清单');self.summary.setObjectName('heading');rl.addWidget(self.summary);self.notice=QLabel('尚未开始联网检索。关注证据按来源公开展示，不生成综合热度分；没有证据不等于无人关注。');self.notice.setWordWrap(True);self.notice.setObjectName('muted');rl.addWidget(self.notice);bottom=QSplitter(Qt.Orientation.Vertical);rl.addWidget(bottom,1)
   self.table=QTableWidget(0,5);self.table.setHorizontalHeaderLabels(['收藏','单篇论文 / 点击查看证据','来源','发表日期','窗口证据']);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.setAlternatingRowColors(True);self.table.setWordWrap(True);self.table.verticalHeader().hide();header=self.table.horizontalHeader();header.setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents);header.setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch);header.setSectionResizeMode(2,QHeaderView.ResizeMode.ResizeToContents);header.setSectionResizeMode(3,QHeaderView.ResizeMode.ResizeToContents);header.setSectionResizeMode(4,QHeaderView.ResizeMode.ResizeToContents);self.table.itemSelectionChanged.connect(self.show_detail);self.table.cellClicked.connect(self.cell_click);bottom.addWidget(self.table)
   self.tabs=QTabWidget();self.detail=QTextBrowser();self.detail.setOpenExternalLinks(False);self.detail.anchorClicked.connect(self.open_link);self.detail.setHtml('<h3>选择一篇论文</h3><p>这里展示文献信息、入选理由、证据网页与原文链接。</p>');self.tabs.addTab(self.detail,'论文与证据');self.log=QPlainTextEdit();self.log.setReadOnly(True);self.tabs.addTab(self.log,'检索日志 / 覆盖报告');bottom.addWidget(self.tabs);bottom.setSizes([330,240]);split.addWidget(right);split.setSizes([310,1100]);self.progress=QProgressBar();self.progress.setTextVisible(False);self.progress.setRange(0,1);self.progress.setValue(0);outer.addWidget(self.progress);self.status=QLabel('仅连接所选公开数据源；不上传你的收藏，不保存知网账号密码。');self.status.setObjectName('muted');outer.addWidget(self.status)
   for w in [self.sort,self.empirical,self.window,self.att,self.clock]:w.currentIndexChanged.connect(self.apply)
   self.uncertain.toggled.connect(self.apply);self.keywords.textChanged.connect(self.apply);self.end.dateChanged.connect(self.apply);self.apply()
  def selected_ids(self):return [sid for sid,it in self.items.items() if it.checkState(0)==Qt.CheckState.Checked]
  def selection_changed(self,*_):
   ids=self.selected_ids();self.selected_label.setText(f'已选择 {len(ids)} / {len(CAT)} 个来源');self.store.save_setting('selected',ids)
  def select_group(self,which):
   self.tree.blockSignals(True)
   for sid,item in self.items.items():item.setCheckState(0,Qt.CheckState.Checked if (which=='top' and sid in E.TOP_IDS) or (which=='cn' and sid not in {s['id'] for s in CAT if s['language']=='en'}) else Qt.CheckState.Unchecked)
   self.tree.blockSignals(False);self.selection_changed();self.apply()
  def query(self):return {'sources':self.selected_ids(),'window':self.window.currentData(),'attention':self.att.currentData(),'clock':self.clock.currentData(),'end':self.end.date().toString('yyyy-MM-dd'),'sort':self.sort.currentData(),'empirical':self.empirical.currentData(),'keywords':self.keywords.text().strip(),'uncertain':self.uncertain.isChecked(),'cache':self.cache.isChecked(),'evidence':self.evidence.isChecked()}
  def start_search(self):
   if self.worker and self.worker.isRunning():return
   if not self.selected_ids():QMessageBox.information(self,'请选择来源','请至少勾选一个期刊或NBER。');return
   self.report={};self.records=[];self.apply();self.log.clear();self.search_btn.setEnabled(False);self.stop.setEnabled(True);self.progress.setRange(0,0);self.notice.setText('正在联网检索；逐来源展示已取得的真实记录。失败来源会在日志中单独列出。');self.worker=SearchWorker(self.query(),self.store);self.worker.progress.connect(self.progress_message);self.worker.partial.connect(self.partial);self.worker.result.connect(self.complete);self.worker.failed.connect(self.failed);self.worker.finished.connect(self.idle);self.worker.start()
  def progress_message(self,s):self.status.setText(s);self.log.appendPlainText(s)
  def partial(self,papers,reps):
   self.records=E.dedup(self.records+papers)
   for r in reps:self.log.appendPlainText(f"[{r.get('status')}] {r.get('source')}：{r.get('retrieved',0)} 篇。{r.get('note','')}")
   self.apply()
  def complete(self,papers,report):
   self.records=papers;self.report=report;self.apply();success=sum(r.get('retrieved',0)>0 for r in report['sources'] if r.get('source_id')!='attention');self.notice.setText(f"本次取得 {len(papers)} 篇原始候选；{success} 个来源取得记录。请打开覆盖报告查看未成功或不完整的来源。");self.log.appendPlainText('\n完整覆盖报告\n'+json.dumps(report,ensure_ascii=False,indent=2));self.status.setText('本次完成。结果已保存在本地；累计引用不是近期关注。')
  def failed(self,s):self.log.appendPlainText(s);self.notice.setText('检索发生异常。已取得的部分保留；详细信息在覆盖报告中。');self.tabs.setCurrentIndex(1)
  def idle(self):
   self.search_btn.setEnabled(True);self.stop.setEnabled(False);self.progress.setRange(0,1);self.progress.setValue(1)
   if self.pending_close:self.close()
  def stop_search(self):
   if self.worker:self.worker.cancel.set();self.stop.setEnabled(False);self.status.setText('已请求停止；正在结束当前网络连接。')
  def apply(self,*_):
   if not hasattr(self,'table'):return
   q=self.query();data=self.records;bookmarks={p['id'] for p in self.store.papers(True)}
   if self.saved.isChecked():data=self.store.papers(True)
   self.visible,stats=E.filter_papers(data,q);self.table.blockSignals(True);self.table.setRowCount(len(self.visible))
   for row,p in enumerate(self.visible):
    p['saved']=p['id'] in bookmarks;vals=['★' if p['saved'] else '☆',p['title'],next((s['short'] for s in CAT if s['id']==p['source_id']),p['source']),p.get('date') or '未知',str(p['attention_count'])]
    for col,v in enumerate(vals):
     item=QTableWidgetItem(v);item.setToolTip(p['title']+'\n'+p.get('provider','') if col==1 else v);self.table.setItem(row,col,item)
    self.table.setRowHeight(row,66)
   self.table.blockSignals(False);self.summary.setText(f'03  单篇候选清单  ·  {len(self.visible)} 篇')
   if self.visible:self.table.selectRow(0)
   else:self.detail.setHtml('<h3>当前条件没有匹配记录</h3><p>可点击“联网搜索论文”，或扩大日期窗口。没有匹配记录不代表来源检索成功；请查看覆盖报告。</p>')
  def cell_click(self,row,col):
   if col==0 and row<len(self.visible):
    p=self.visible[row];self.store.upsert([p]);self.store.bookmark(p['id'],not p.get('saved',False));self.apply()
  def show_detail(self):
   row=self.table.currentRow()
   if row<0 or row>=len(self.visible):return
   p=self.visible[row];esc=lambda x:html.escape(str(x or ''),quote=True)
   def link(u,label):return f'<a href="{esc(u)}">{esc(label)}</a>' if E.safe_url(u) else esc(label)
   pieces=[f'<h2 style="color:#123d38">{esc(p["title"])}</h2>',f'<p>{esc("; ".join(p.get("authors",[])))}</p>',f'<p><b>{esc(p["source"])}</b> · {esc(p.get("date"))} · {esc(p.get("date_kind"))} · {esc(p.get("type"))}</p>',f'<p>{link(p["url"],"打开原始文献")}　{link(p.get("metadata_url",""),"元数据出处")}</p>','<h3>为什么入选</h3>']
   for r in p.get('reasons',[]):pieces.append('<p>'+esc(r['text'])+' '+link(r.get('url',''),'核对出处')+'</p>')
   pieces.append('<h3>摘要 / 研究线索</h3><p>'+esc(p.get('abstract') or '公开元数据未提供摘要。不会根据题目编造研究结论。')+'</p>');pieces.append('<h3>关注证据</h3>')
   for e in p.get('evidence',[]):
    active=e in p.get('active_evidence',[]);pieces.append(f'<p><b>{esc(e.get("date"))}</b> · {esc(e.get("source"))} · {"窗口内" if active else "窗口外或日期精度不足"}<br>{link(e["url"],e["title"])}<br>{esc(e.get("match"))}</p>')
   if not p.get('evidence'):pieces.append('<p>有限公开栏目未发现已核验的对应证据。不等于没有社会影响。</p>')
   pieces.append('<h3>数据口径</h3><p>Crossref累计引用：'+esc(p.get('citations') if p.get('citations') is not None else '未取得')+'；不是最近一个月新增引用。<br>元数据来源：'+esc(p.get('provider'))+'<br>采集时间：'+esc(p.get('observed_at'))+'</p>')
   if p.get('cnki_cumulative'):pieces.append('<p>知网页面累计指标（未作近期热度）：'+esc(json.dumps(p['cnki_cumulative'],ensure_ascii=False))+'</p>')
   self.detail.setHtml('<html><body style="font-family:Microsoft YaHei UI;font-size:13px;line-height:1.7;padding:12px">'+''.join(pieces)+'</body></html>')
  def open_link(self,url):
   if E.safe_url(url.toString()):QDesktopServices.openUrl(url)
  def export(self):
   if not self.visible:QMessageBox.information(self,'没有可导出的论文','请先搜索或打开收藏。');return
   filename,kind=QFileDialog.getSaveFileName(self,'导出带证据的清单',str(Path.home()/'PaperRadar.csv'),'CSV清单 (*.csv);;RIS题录 (*.ris);;JSON完整数据 (*.json)')
   if not filename:return
   try:
    suffix=Path(filename).suffix.lower()
    if suffix=='.json':Path(filename).write_text(json.dumps({'papers':self.visible,'report':self.report},ensure_ascii=False,indent=2),encoding='utf-8')
    elif suffix=='.ris':Path(filename).write_text(E.export_ris(self.visible),encoding='utf-8')
    else:Path(filename).write_text(E.export_csv(self.visible),encoding='utf-8-sig',newline='')
    self.status.setText('已导出到 '+filename)
   except Exception as e:QMessageBox.warning(self,'导出失败',str(e))
  def import_records(self):
   filename,_=QFileDialog.getOpenFileName(self,'导入知网题录或本软件导出数据','','题录 (*.txt *.ris *.enw *.json);;所有文件 (*)')
   if not filename:return
   try:
    raw=Path(filename).read_bytes()
    try:content=raw.decode('utf-8-sig')
    except UnicodeDecodeError:content=raw.decode('gb18030')
    papers=E.parse_reference_import(content,CAT);self.store.upsert(papers);self.records=E.dedup(self.records+papers);self.apply();QMessageBox.information(self,'题录导入',f'导入 {len(papers)} 篇可识别来源的题录。\n不会为导入记录生成虚构热度；仅年份的日期可能不通过窄窗口筛选。')
   except Exception as e:QMessageBox.warning(self,'导入失败',str(e))
  def open_cnki(self):
   try:
    from cnki_browser import CNKIBrowser
    if self.cnki is None:self.cnki=CNKIBrowser(CAT,self.selected_ids(),self.accept_cnki,self)
    self.cnki.show();self.cnki.raise_()
   except Exception as e:QMessageBox.warning(self,'知网浏览器无法启动','可使用系统浏览器检索后导出题录再导入。\n'+str(e));QDesktopServices.openUrl(QUrl(E.CNKI_URL))
  def accept_cnki(self,rows):
   papers,rejected=E.import_cnki_rows(rows,CAT);self.store.upsert(papers);self.records=E.dedup(self.records+papers);self.apply();QMessageBox.information(self,'当前知网页面采集完成',f'取得 {len(papers)} 篇匹配已登记期刊的题录；排除 {rejected} 条。\n仅读取当前可见检索结果。可在知网翻页后继续采集，或导出更多题录再导入。')
  def help(self):
   dlg=QDialog(self);dlg.setWindowTitle('使用说明与数据边界');dlg.resize(840,680);layout=QVBoxLayout(dlg);view=QTextBrowser();view.setOpenExternalLinks(True);view.setHtml((ROOT/'GUIDE.html').read_text(encoding='utf-8'));layout.addWidget(view);dlg.exec()
  def closeEvent(self,event):
   if self.worker and self.worker.isRunning():
    if not self.pending_close and QMessageBox.question(self,'检索正在进行','停止检索并退出？')!=QMessageBox.StandardButton.Yes:event.ignore();return
    self.pending_close=True;self.stop_search();event.ignore();return
   if self.cnki:self.cnki.close()
   event.accept()
 window=MainWindow();window.show()
 if args.self_test:
  from PySide6.QtTest import QTest
  report_dir=Path(args.report_dir);report_dir.mkdir(parents=True,exist_ok=True)
  def test():
   checks=[]
   def check(name,value,detail=''):checks.append({'name':name,'passed':bool(value),'detail':detail})
   try:
    records=json.loads(Path(args.test_records).read_text(encoding='utf-8')) if args.test_records else []
    if isinstance(records,dict):records=records.get('papers',[])
    window.records=records;window.store.upsert(records);window.select_group('top');window.window.setCurrentIndex(3);window.apply();check('native_window_shown',window.isVisible());check('36_source_controls',len(window.items)==36);check('real_network_records_loaded',bool(records),str(len(records)));check('actual_table_rows',window.table.rowCount()>0,str(window.table.rowCount()));check('default_sources_are_top5_nber',all(p['source_id'] in E.TOP_IDS for p in window.visible));check('no_front_matter',all(E.is_research(p['title']) for p in records));known=[p for p in records if p.get('doi')=='10.1257/aer.20231016'];check('known_AER_title_verified',bool(known and 'Florida Wetlands' in known[0]['title']))
    if known:window.keywords.setText('Conservation Priorities');window.apply();check('exact_keyword_filter',bool(window.visible));window.keywords.clear()
    if window.visible:
     p=window.visible[0];window.store.bookmark(p['id'],True);check('SQLite_bookmark',any(x['id']==p['id'] for x in window.store.papers(True)));csv=E.export_csv(window.visible);ris=E.export_ris(window.visible);check('CSV_contains_real_title',p['title'] in csv);check('RIS_contains_real_DOI',not p.get('doi') or p['doi'] in ris);check('evidence_detail_rendered',bool(window.detail.toPlainText()));window.store.bookmark(p['id'],False)
    window.window.setCurrentIndex(0);window.apply();start=E.window_start(date.today(),'7d');check('7_day_filter',all(E.in_window(p['date'],start,date.today()) for p in window.visible));window.window.setCurrentIndex(3);window.select_group('cn');check('CNKI_sources_exactly_nine',len(window.selected_ids())==9);window.select_group('top');window.apply()
    try:
     from cnki_browser import CAPTURE_JS
     from PySide6.QtWebEngineWidgets import QWebEngineView
     check('QtWebEngine_bundled',bool(QWebEngineView and CAPTURE_JS))
    except Exception as e:check('QtWebEngine_bundled',False,str(e))
    QTest.qWait(300);window.grab().save(str(report_dir/'desktop.png'))
   except Exception:check('selftest_exception',False,traceback.format_exc())
   result={'version':E.VERSION,'tested_at':E.stamp(),'platform':sys.platform,'frozen':bool(getattr(sys,'frozen',False)),'real_records_used':True,'checks':checks,'passed':sum(x['passed'] for x in checks),'total':len(checks)};(report_dir/'gui_test.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');app.exit(0 if all(x['passed'] for x in checks) else 2)
  QTimer.singleShot(1200,test)
 return app.exec()
if __name__=='__main__':
 try:sys.exit(app_main())
 except Exception:
  log=E.Store().root/'startup_error.txt';log.write_text(traceback.format_exc(),encoding='utf-8')
  if sys.stderr:traceback.print_exc()
  if sys.platform=='win32':
   import ctypes
   ctypes.windll.user32.MessageBoxW(0,'程序启动失败。错误日志：'+str(log),'Paper Radar',16)
  sys.exit(1)
