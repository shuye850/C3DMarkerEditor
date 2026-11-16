from PySide6 import QtWidgets as W,QtCore,QtGui
from body_model import slot_color

class CandidatePool(W.QWidget):
    def __init__(self,editor):
        super().__init__();self.editor=editor;self.selected=None
        layout=W.QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(5)
        header=W.QHBoxLayout();layout.addLayout(header)
        self.fold=W.QPushButton('候选池 ▾');self.fold.setCheckable(True);self.fold.setChecked(True);header.addWidget(self.fold,1)
        self.colored=W.QPushButton('彩色点');self.colored.setCheckable(True);self.colored.setChecked(True);self.colored.setToolTip('显示／隐藏已配对的候选点');self.colored.toggled.connect(self.refresh);header.addWidget(self.colored)
        more=W.QPushButton('⋯');more.setFixedWidth(32);menu=W.QMenu(more);more.setMenu(menu);header.addWidget(more)
        menu.addAction('显示全部点',self.show_all);menu.addSeparator();menu.addAction('编辑编号…',self.edit);menu.addAction('当前帧拆分…',self.split);menu.addAction('选择连续片段',editor.select_current_segment)
        self.list=W.QListWidget();self.list.setViewMode(W.QListView.ViewMode.IconMode);self.list.setResizeMode(W.QListView.ResizeMode.Adjust);self.list.setMovement(W.QListView.Movement.Static);self.list.setGridSize(QtCore.QSize(52,42));self.list.setIconSize(QtCore.QSize(20,20));self.list.setFixedHeight(94);layout.addWidget(self.list)
        self.fold.toggled.connect(self.list.setVisible);self.fold.toggled.connect(lambda value:self.fold.setText('候选池 ▾' if value else '候选池 ▸'))
        self.list.itemClicked.connect(self.choose)
        self.list.itemDoubleClicked.connect(self.double_click)
    def refresh(self,*_):
        s=self.editor.s
        if not s:return
        self.list.clear()
        matrix=self.editor.pairing.matrix;frame=self.editor.frame.value()-s.first
        for i,m in enumerate(s.markers):
            matches=(matrix[:,frame]==i).nonzero()[0] if matrix is not None else []
            name=s.slots[int(matches[0])] if len(matches) else None
            if name and not self.colored.isChecked() and i!=self.selected:continue
            color=QtGui.QColor.fromRgbF(*slot_color(name)) if name else QtGui.QColor('#9aa5b5')
            hidden=i in self.editor.hidden_markers
            pix=QtGui.QPixmap(24,24);pix.fill(QtCore.Qt.GlobalColor.transparent);p=QtGui.QPainter(pix);p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            pen=QtGui.QPen(color.lighter(140) if name else QtGui.QColor('#727d8b'),1.3,QtCore.Qt.PenStyle.DashLine)
            p.setPen(pen if hidden else QtCore.Qt.PenStyle.NoPen)
            if hidden:color=QtGui.QColor.fromRgbF(*[.82+.18*x for x in slot_color(name)]) if name else QtGui.QColor('#20252d')
            p.setBrush(color);p.drawEllipse(3,3,18,18);p.end()
            item=W.QListWidgetItem(QtGui.QIcon(pix),m['label']);item.setData(QtCore.Qt.ItemDataRole.UserRole,i);item.setToolTip(f"{m['label']} · {m['start']+s.first}–{m['end']+s.first} 帧 · 双击"+('显示' if hidden else '隐藏'))
            self.list.addItem(item)
            if i==self.selected:self.list.setCurrentItem(item)
    def sync_selection(self):
        if self.selected is None:return
        for row in range(self.list.count()):
            item=self.list.item(row)
            if item.data(QtCore.Qt.ItemDataRole.UserRole)==self.selected:
                self.list.setCurrentItem(item);self.list.scrollToItem(item);break
        else:self.refresh()
    def double_click(self,item):
        marker=item.data(QtCore.Qt.ItemDataRole.UserRole)
        self.editor.select_public_marker(marker)
        self.toggle_visibility(marker in self.editor.hidden_markers)
    def toggle_visibility(self,visible):
        if self.selected is None:return
        if visible:self.editor.hidden_markers.discard(self.selected)
        else:self.editor.hidden_markers.add(self.selected)
        self.refresh();self.editor.draw()
    def show_all(self):
        self.editor.hidden_markers.clear();self.editor.hidden_sources.clear();self.refresh();self.editor.draw()
    def choose(self,item):
        self.editor.select_public_marker(item.data(QtCore.Qt.ItemDataRole.UserRole))
    def edit(self):
        e=self.editor
        if not e.s:return
        text,ok=W.QInputDialog.getMultiLineText(self,'编辑标记点编号','每行一个编号；可重命名，新增编号写在末尾。','\n'.join(m['label'] for m in e.s.markers))
        if ok:e.guard(lambda:(e.s.edit_marker_labels([x.strip() for x in text.splitlines() if x.strip()]),e.refresh()))
    def split(self):
        e=self.editor
        if not e.s or self.selected is None:return
        label,ok=W.QInputDialog.getText(self,'拆分标记点','从当前帧起移入新编号：',text=f"{e.s.markers[self.selected]['label']}_2")
        if ok:
            def run():
                self.selected=e.s.split_marker(self.selected,e.frame.value()-e.s.first,label.strip())
                source=e.s.marker_source(self.selected,e.frame.value()-e.s.first)
                e.selected_source=source if source is not None else -1;e.curve_slot_override=None;e.refresh()
            e.guard(run)
