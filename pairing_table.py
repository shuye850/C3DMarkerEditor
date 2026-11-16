"""Browse normally; stage one or several bijective pairings in an explicit mode."""
import numpy as np
from PySide6 import QtWidgets as W,QtCore,QtGui
from marker_names import display_name

class PairingPanel(W.QWidget):
    def __init__(self,editor):
        super().__init__();self.editor=editor;self.busy=False;self.anchor=None;self.matrix=None
        self.editing=False;self.base_matrix=None;self.base_state=None;self.session=None
        layout=W.QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        header=W.QHBoxLayout();layout.addLayout(header)
        self.mode=W.QComboBox();self.mode.addItems(['固定关键点名称','固定标记点编号']);header.addWidget(self.mode,1)
        more=W.QPushButton('⋯');more.setFixedWidth(32);menu=W.QMenu(more);menu.addAction('建模方案…',editor.template);more.setMenu(menu);header.addWidget(more)
        self.table=W.QTableWidget(0,2);self.table.setSelectionBehavior(W.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(W.QAbstractItemView.SelectionMode.SingleSelection);self.table.setEditTriggers(W.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide();self.table.horizontalHeader().setSectionResizeMode(W.QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True);self.table.verticalHeader().setDefaultSectionSize(34);self.table.setMinimumHeight(190);layout.addWidget(self.table,1)
        actions=W.QHBoxLayout();layout.addLayout(actions)
        self.confirm=W.QPushButton('配对模式');self.confirm.setProperty('role','primary');actions.addWidget(self.confirm)
        self.remove=W.QPushButton('取消配对');actions.addWidget(self.remove)
        self.mode.currentIndexChanged.connect(self.refresh);self.table.cellClicked.connect(self.row_clicked)
        self.table.cellDoubleClicked.connect(self.double_clicked)
        self.confirm.clicked.connect(self.apply);self.remove.clicked.connect(self.unpair)

    def has_pending(self):
        return self.editing and self.base_matrix is not None and not np.array_equal(self.matrix,self.base_matrix)

    def _leave(self):
        self.editing=False;self.base_matrix=None;self.base_state=None;self.session=None;self.anchor=None
        self.confirm.setText('配对模式');self.remove.setText('取消配对');self.mode.setEnabled(True)
        if hasattr(self.editor,'update_menu_state'):self.editor.update_menu_state()

    def refresh(self,*_):
        s=self.editor.s
        if not s:return
        if self.editing and (self.session is not s or self.base_state!=s.snapshot()):
            self._leave();self.editor.statusBar().showMessage('项目已改变，未确认的配对已取消。')
        self.busy=True
        if not self.editing:self.anchor=None;self.matrix=s.pairing_matrix()
        self.table.setRowCount(0);fixed=self.mode.currentIndex()==1
        self.table.setHorizontalHeaderLabels(['标记点编号','关键点名称'] if fixed else ['关键点名称','标记点编号'])
        for key in (range(len(s.markers)) if fixed else s.slots):
            row=self.table.rowCount();self.table.insertRow(row)
            item=W.QTableWidgetItem(s.markers[key]['label'] if fixed else display_name(key));item.setData(QtCore.Qt.ItemDataRole.UserRole,key);self.table.setItem(row,0,item)
            combo=W.QComboBox();combo.setView(W.QListView(combo));combo.addItem('未配对',None)
            if fixed:
                for name in s.slots:combo.addItem(display_name(name),name)
            else:
                for i,m in enumerate(s.markers):combo.addItem(m['label'],i)
            combo.currentIndexChanged.connect(lambda _,r=row:self.stage_row(r));self.table.setCellWidget(row,1,combo)
        self.busy=False;self.sync_frame()

    def begin(self,row=None):
        s=self.editor.s
        if not s:return
        if not self.editing:
            self.session=s;self.base_state=s.snapshot();self.base_matrix=s.pairing_matrix();self.matrix=self.base_matrix.copy()
            self.editing=True;self.mode.setEnabled(False);self.confirm.setText('确定配对');self.remove.setText('取消本次配对')
        self.anchor=row
        if row is not None:self.table.selectRow(row)
        self.sync_frame();self.editor.statusBar().showMessage('配对模式：单击左列，再选点；确定后统一应用，取消可放弃全部操作。')
        if hasattr(self.editor,'update_menu_state'):self.editor.update_menu_state()

    def double_clicked(self,row,column):
        if column==0:self.begin(row)

    def sync_frame(self):
        e=self.editor;s=e.s
        if not s or self.matrix is None:return
        frame=e.frame.value()-s.first;fixed=self.mode.currentIndex()==1;self.busy=True
        diff=(self.matrix!=self.base_matrix) if self.editing else None
        changed_markers=set(np.r_[self.matrix[diff],self.base_matrix[diff]]) if self.editing else set()
        for row in range(self.table.rowCount()):
            key=self.table.item(row,0).data(QtCore.Qt.ItemDataRole.UserRole)
            if fixed:
                matches=(self.matrix[:,frame]==key).nonzero()[0];value=s.slots[int(matches[0])] if len(matches) else None
                changed=key in changed_markers
            else:
                marker=int(self.matrix[row,frame]);value=marker if marker>=0 else None
                changed=self.editing and bool(diff[row].any())
            item=self.table.item(row,0);item.setBackground(QtGui.QColor('#fff0cc') if changed else QtGui.QBrush())
            combo=self.table.cellWidget(row,1);combo.blockSignals(True);combo.setCurrentIndex(max(0,combo.findData(value)));combo.setEnabled(self.editing);combo.blockSignals(False)
        self.busy=False
        if self.editing and self.anchor is not None:self.table.selectRow(self.anchor)
        elif not self.editing and e.pool.selected is not None:self.select_marker(e.pool.selected)

    def stage_row(self,row):
        if self.busy or not self.editing:return
        self.anchor=row;self.table.selectRow(row);s=self.editor.s
        key=self.table.item(row,0).data(QtCore.Qt.ItemDataRole.UserRole);value=self.table.cellWidget(row,1).currentData()
        if value is None:
            scope=self.selection_range()
            if scope is None:self.sync_frame();return
            start,end=scope
            if self.mode.currentIndex()==1:
                part=self.matrix[:,start:end+1];part[part==key]=-1
            else:self.matrix[row,start:end+1]=-1
            self.staged_changed();return
        marker,slot=(key,value) if self.mode.currentIndex()==1 else (value,key)
        self.stage_pair(marker,slot)

    def stage_pair(self,marker,slot):
        if not self.editing:return
        scope=self.selection_range()
        if scope is None:self.sync_frame();return
        s=self.editor.s;start,end=scope;m=s.markers[marker]
        start=max(start,m['start']);end=min(end,m['end'])
        if start>end:self.editor.statusBar().showMessage('选区与该编号的时间范围没有重叠。');self.sync_frame();return
        target=s.slots.index(slot)
        for frame in range(start,end+1):
            previous=np.flatnonzero(self.matrix[:,frame]==marker)
            if len(previous) and previous[0]!=target:self.matrix[previous[0],frame]=self.matrix[target,frame]
            self.matrix[target,frame]=marker
        self.staged_changed()

    def selection_range(self):
        if not self.editor.selection_active and self.editor.calibration_scope.currentIndex()==0:
            self.editor.statusBar().showMessage('当前没有选区，请先框选时间范围。');return None
        return self.editor.calibration_range()

    def staged_changed(self):
        self.sync_frame();self.editor.pool.refresh();self.editor.draw();self.editor.update_save_status()

    def select_marker(self,marker):
        if self.busy or self.matrix is None:return
        if self.editing:
            if self.anchor is not None:self.table.selectRow(self.anchor);self.table.scrollToItem(self.table.item(self.anchor,0))
            return
        frame=self.editor.frame.value()-self.editor.s.first;matches=(self.matrix[:,frame]==marker).nonzero()[0]
        row=marker if self.mode.currentIndex()==1 else int(matches[0]) if len(matches) else -1
        if row>=0:self.table.selectRow(row);self.table.scrollToItem(self.table.item(row,0))
        else:self.table.clearSelection();self.table.setCurrentCell(-1,-1)

    def row_clicked(self,row,column):
        if self.busy or not self.editor.s or column!=0:return
        if self.editing:self.anchor=row;self.table.selectRow(row);return
        s=self.editor.s;frame=self.editor.frame.value()-s.first
        marker=row if self.mode.currentIndex()==1 else int(self.matrix[row,frame])
        if marker>=0:self.editor.select_public_marker(marker)
        else:self.table.selectRow(row)

    def preview_selected(self,source):
        if self.busy or not self.editor.s:return
        marker=self.editor.pool.selected
        if marker is None:return
        if not self.editing:self.select_marker(marker);return
        if self.anchor is None:return
        if self.mode.currentIndex()==0:self.stage_pair(marker,self.editor.s.slots[self.anchor])
        else:
            frame=self.editor.frame.value()-self.editor.s.first
            matches=(self.matrix[:,frame]==marker).nonzero()[0]
            if len(matches):self.stage_pair(self.anchor,self.editor.s.slots[int(matches[0])])
            else:self.editor.statusBar().showMessage('此点未配对关键点，请使用右列下拉选择关键点。')

    def apply(self):
        if not self.editing:self.begin();return
        e=self.editor;s=e.s
        def run():
            if s is not self.session or s.snapshot()!=self.base_state:raise ValueError('项目已变化，请取消本次配对后重新进入。')
            if self.has_pending():
                changed=np.flatnonzero(np.any(self.matrix!=self.base_matrix,axis=0))
                s._commit_pairing_matrix(self.matrix,int(changed[0]),int(changed[-1]))
            self._leave();e.refresh();e.statusBar().showMessage('本次配对已统一应用并退出配对模式，可一次撤销。')
            return True
        return e.guard(run)

    def cancel(self):
        self._leave();self.editor.refresh();self.editor.statusBar().showMessage('已取消本次配对模式的全部操作。')

    def unpair(self):
        if self.editing:self.cancel();return
        e=self.editor;s=e.s;row=self.table.currentRow()
        if not s or row<0:return
        key=self.table.item(row,0).data(QtCore.Qt.ItemDataRole.UserRole);scope=self.selection_range()
        if scope is None:return
        start,end=scope
        def run():
            s.clear_pairing(start,end,marker=key if self.mode.currentIndex()==1 else None,slot=key if self.mode.currentIndex()==0 else None)
            e.refresh();e.statusBar().showMessage('已取消所选范围内的配对，坐标保留，可撤销。')
        e.guard(run)
