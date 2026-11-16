"""Preset and custom marker-scheme editor. No project changes until Apply."""
import copy,json,hashlib
from pathlib import Path
from PySide6 import QtWidgets as W,QtCore
from model_schemes import PRESETS,validate_scheme
from marker_names import display_name,storage_name
from runtime_paths import data_dir

class SchemeDialog(W.QDialog):
    def __init__(self,editor,library=None):
        super().__init__(editor);self.editor=editor;self.loading=True;self.current={}
        self.library=Path(library) if library else data_dir()/'建模方案'
        self.setWindowTitle('建模方案');self.resize(760,650)
        layout=W.QVBoxLayout(self)
        top=W.QHBoxLayout();layout.addLayout(top);top.addWidget(W.QLabel('方案预设'))
        self.presets=W.QComboBox();top.addWidget(self.presets,1)
        self.presets.addItem('当前项目方案',copy.deepcopy(editor.s.model_scheme))
        for scheme in PRESETS:self.presets.addItem(scheme['name'],copy.deepcopy(scheme))
        if self.library.exists():
            for path in sorted(self.library.glob('*.json')):
                try:
                    scheme=validate_scheme(json.loads(path.read_text(encoding='utf-8'))['scheme']);self.presets.addItem(scheme['name'],scheme)
                except (OSError,ValueError,KeyError,TypeError):continue
        tools=W.QHBoxLayout();layout.addLayout(tools)
        for text,fn in [('导入方案…',self.import_file),('导出方案…',self.export_file),('保存为预设',self.save_preset)]:
            button=W.QPushButton(text);button.clicked.connect(fn);tools.addWidget(button)
        form=W.QFormLayout();layout.addLayout(form);self.name=W.QLineEdit();form.addRow('方案名称',self.name)
        self.description=W.QPlainTextEdit();self.description.setMaximumHeight(64);form.addRow('方案说明',self.description)
        tabs=W.QTabWidget();layout.addWidget(tabs,1)
        points=W.QWidget();point_layout=W.QVBoxLayout(points);point_layout.setContentsMargins(0,4,0,0)
        self.points=W.QTableWidget(0,2);self.points.setHorizontalHeaderLabels(['点位名称（中文／缩写）','人体点']);self.points.horizontalHeader().setSectionResizeMode(0,W.QHeaderView.ResizeMode.Stretch);self.points.setColumnWidth(1,80);self.points.setSelectionBehavior(W.QAbstractItemView.SelectionBehavior.SelectRows);point_layout.addWidget(self.points)
        row=W.QHBoxLayout();point_layout.addLayout(row)
        add=W.QPushButton('新增点位');add.clicked.connect(lambda:self.add_row('',True));row.addWidget(add)
        remove=W.QPushButton('移除选中点位');remove.clicked.connect(self.remove_rows);row.addWidget(remove)
        tabs.addTab(points,'点位定义')
        links=W.QWidget();links_layout=W.QVBoxLayout(links);links_layout.addWidget(W.QLabel('每行两个缩写，以空格分隔；留空则按标准缩写自动连接。'))
        self.connections=W.QPlainTextEdit();self.connections.setPlaceholderText('LSHO LELB\nLELB LWRA');links_layout.addWidget(self.connections);tabs.addTab(links,'显示连接')
        self.summary=W.QLabel();self.summary.setWordWrap(True);self.summary.setTextFormat(QtCore.Qt.TextFormat.PlainText);layout.addWidget(self.summary)
        self.result_scheme=None
        buttons=W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Apply|W.QDialogButtonBox.StandardButton.Cancel);buttons.button(W.QDialogButtonBox.StandardButton.Apply).setText('应用方案');buttons.button(W.QDialogButtonBox.StandardButton.Apply).setProperty('role','primary');buttons.button(W.QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply);buttons.button(W.QDialogButtonBox.StandardButton.Cancel).setText('取消');buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        self.presets.currentIndexChanged.connect(self.load_selected)
        self.points.itemChanged.connect(self.recount);self.name.textChanged.connect(self.recount);self.connections.textChanged.connect(self.recount)
        self.load_selected()

    def add_row(self,code,body=True):
        row=self.points.rowCount();self.points.insertRow(row);self.points.setItem(row,0,W.QTableWidgetItem(display_name(code)))
        item=W.QTableWidgetItem();item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled|QtCore.Qt.ItemFlag.ItemIsSelectable|QtCore.Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(QtCore.Qt.CheckState.Checked if body else QtCore.Qt.CheckState.Unchecked);self.points.setItem(row,1,item)
        if not self.loading:self.points.setCurrentCell(row,0);self.recount()

    def remove_rows(self):
        for row in sorted({i.row() for i in self.points.selectedIndexes()},reverse=True):self.points.removeRow(row)
        self.recount()

    def load_selected(self,*_):
        self.loading=True;self.current=copy.deepcopy(self.presets.currentData());self.points.setRowCount(0)
        self.name.setText(self.current['name']);self.description.setPlainText(self.current.get('description',''))
        for code in self.current['body_slots']:self.add_row(code,True)
        for code in self.current.get('extra_slots',[]):self.add_row(code,False)
        self.connections.setPlainText('\n'.join(' '.join(edge) for edge in self.current.get('connections',[])))
        self.loading=False;self.recount()

    def collect(self):
        aliases={display_name(n):n for n in self.editor.s.slots}
        for n in self.current['body_slots']+self.current.get('extra_slots',[]):aliases.setdefault(display_name(n),n)
        body=[];extra=[]
        for row in range(self.points.rowCount()):
            item=self.points.item(row,0);role=self.points.item(row,1)
            if item is None or role is None:raise ValueError('点位定义不完整')
            text=item.text().strip();code=aliases.get(text,storage_name(text))
            (body if role.checkState()==QtCore.Qt.CheckState.Checked else extra).append(code)
        value=dict(self.current,name=self.name.text().strip(),description=self.description.toPlainText(),body_slots=body,extra_slots=extra)
        value['connections']=[line.split() for line in self.connections.toPlainText().splitlines() if line.strip()]
        if body!=self.current['body_slots'] or value['name']!=self.current['name']:
            value['id']='custom_'+hashlib.sha256(value['name'].encode()).hexdigest()[:12]
            if body!=self.current['body_slots'] and any(value['name']==p['name'] for p in PRESETS):value['name']+=' · 自定义'
        return validate_scheme(value)

    def recount(self,*_):
        if self.loading:return
        try:
            scheme=self.collect();effective,retained=self.editor.s.scheme_result(scheme)
            text=f"人体点 {len(scheme['body_slots'])} 个 · 附加点 {len(effective['extra_slots'])} 个。“人体点”未勾选的项为附加点。"
            if retained:text+='\n已有记录的位置将保留为附加点：'+ '、'.join(display_name(n) for n in retained)
            self.summary.setText(text)
        except ValueError as error:self.summary.setText(str(error))

    def apply(self):
        try:self.result_scheme=self.collect();self.accept()
        except ValueError as error:W.QMessageBox.warning(self,'方案未应用',str(error))

    def write_file(self,path):
        value=self.collect();Path(path).write_text(json.dumps(dict(version=1,scheme=value),ensure_ascii=False,indent=2),encoding='utf-8');return value

    def save_preset(self):
        try:
            value=self.collect();self.library.mkdir(exist_ok=True,parents=True)
            path=self.library/(hashlib.sha256(value['name'].encode()).hexdigest()[:20]+'.json');self.write_file(path)
            index=self.presets.count();self.presets.addItem(value['name'],value);self.presets.setCurrentIndex(index)
            self.summary.setText('预设已保存，下次打开仍可选择；点击应用方案后才修改当前项目。')
        except (OSError,ValueError) as error:W.QMessageBox.warning(self,'未保存',str(error))

    def import_file(self):
        path,_=W.QFileDialog.getOpenFileName(self,'导入建模方案','','方案 JSON (*.json)')
        if not path:return
        try:
            value=validate_scheme(json.loads(Path(path).read_text(encoding='utf-8'))['scheme']);self.presets.addItem(value['name'],value);self.presets.setCurrentIndex(self.presets.count()-1)
        except (OSError,ValueError,KeyError,TypeError) as error:W.QMessageBox.warning(self,'无法导入',str(error))

    def export_file(self):
        path,_=W.QFileDialog.getSaveFileName(self,'导出建模方案','建模方案.json','方案 JSON (*.json)')
        if not path:return
        try:self.write_file(path if path.lower().endswith('.json') else path+'.json')
        except (OSError,ValueError) as error:W.QMessageBox.warning(self,'无法导出',str(error))
