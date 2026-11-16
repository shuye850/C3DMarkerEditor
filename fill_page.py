"""Task-oriented arrangement of the existing fill controls."""
from PySide6 import QtWidgets as W,QtCore

class FieldGrid(W.QGridLayout):
    """Explicit field columns, independent of macOS QFormLayout style hints."""
    def __init__(self,parent=None):
        super().__init__(parent);self.rows=[];self.setColumnStretch(1,1);self.setHorizontalSpacing(8);self.setVerticalSpacing(6)
    def addRow(self,label,field=None):
        row=len(self.rows)
        if field is None:
            field=label;label=None;self.addWidget(field,row,0,1,2)
        else:
            label=W.QLabel(label) if isinstance(label,str) else label
            self.addWidget(label,row,0,QtCore.Qt.AlignmentFlag.AlignLeft|QtCore.Qt.AlignmentFlag.AlignVCenter);self.addWidget(field,row,1)
        self.rows.append((label,field))
    def setRowVisible(self,field,visible):
        for label,widget in self.rows:
            if widget is field:
                widget.setVisible(visible)
                if label is not None:label.setVisible(visible)
                break

def organize_fill_page(e,page):
    buttons={button.text():button for button in page.findChildren(W.QPushButton)}
    old_layout=page.layout();old_toggle=e.advanced_toggle;old_review=e.review_toggle
    hidden=[e.fill,e.repair_context,e.mode_note,e.fill_summary]
    retained=[e.exclude_button,e.fill_scope,e.fill_position,e.fill_time,e.fill_start,e.fill_end,e.process_mode,e.fill_method,e.repair_tension,e.gap,e.smooth_fill,e.smooth_strength,e.smooth_window]+hidden+list(buttons.values())
    for widget in retained:widget.setParent(None)
    holder=W.QWidget();holder.setLayout(old_layout);holder.deleteLater()
    outer=W.QVBoxLayout(page);outer.setContentsMargins(8,8,8,8);outer.setSpacing(6)
    for widget in hidden:widget.setParent(page);widget.hide()
    scroll=W.QScrollArea();scroll.setObjectName('fillControls');scroll.setWidgetResizable(True);scroll.setFrameShape(W.QFrame.Shape.NoFrame);scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    body=W.QWidget();stack=W.QVBoxLayout(body);stack.setContentsMargins(0,0,0,0);stack.setSpacing(8);scroll.setWidget(body);outer.addWidget(scroll,1);e.fill_scroll=scroll

    scope=W.QGroupBox('处理范围');scope.setObjectName('fillScope');scope_layout=W.QVBoxLayout(scope);form=FieldGrid();scope_layout.addLayout(form);stack.addWidget(scope)
    form.addRow('处理对象',e.fill_scope);form.addRow('当前点',e.fill_position);form.addRow('时间范围',e.fill_time)
    frames=W.QWidget();row=W.QHBoxLayout(frames);row.setContentsMargins(0,0,0,0)
    for widget in [e.fill_start,e.fill_end]:widget.setMinimumWidth(52);widget.setSizePolicy(W.QSizePolicy.Policy.Expanding,W.QSizePolicy.Policy.Fixed)
    row.addWidget(e.fill_start,1);row.addWidget(W.QLabel('至'));row.addWidget(e.fill_end,1);form.addRow('选区帧',frames)
    scope_layout.addWidget(e.exclude_button)

    method=W.QGroupBox('处理方法');method.setObjectName('fillMethod');method_layout=W.QVBoxLayout(method);algorithm=FieldGrid();method_layout.addLayout(algorithm);stack.addWidget(method)
    algorithm.addRow('处理方式',e.process_mode);algorithm.addRow('算法',e.fill_method);algorithm.addRow('最大缺口',e.gap);algorithm.addRow('贝塞尔弯曲',e.repair_tension)
    e.advanced_toggle=W.QPushButton('高级参数 ▸');e.advanced_toggle.setCheckable(True);e.advanced_toggle.setChecked(old_toggle.isChecked());method_layout.addWidget(e.advanced_toggle)
    advanced=W.QWidget();advanced_form=FieldGrid(advanced);advanced_form.setContentsMargins(0,4,0,0);advanced_form.addRow(e.smooth_fill);advanced_form.addRow('平滑强度',e.smooth_strength);advanced_form.addRow('单侧参考',e.smooth_window);method_layout.addWidget(advanced)
    e.advanced_toggle.toggled.connect(advanced.setVisible);e.advanced_toggle.toggled.connect(lambda value:e.advanced_toggle.setText('高级参数 ▾' if value else '高级参数 ▸'));advanced.setVisible(e.advanced_toggle.isChecked())

    review=W.QGroupBox('检查与批量');review.setObjectName('fillReview');review_layout=W.QVBoxLayout(review);stack.addWidget(review)
    row=W.QHBoxLayout();review_layout.addLayout(row);row.addWidget(buttons['扫描当前范围'],1)
    e.review_toggle=W.QPushButton('检查清单');e.review_toggle.setCheckable(True);e.review_toggle.setChecked(old_review.isChecked());e.review_toggle.toggled.connect(e.update_review_visibility);row.addWidget(e.review_toggle)
    review_layout.addWidget(buttons['批量补帧：全部位置 · 全程']);stack.addStretch()

    actions=W.QGroupBox('预览与应用');actions.setObjectName('fillActions');layout=W.QGridLayout(actions);outer.addWidget(actions)
    for row,texts in enumerate([['预览当前范围','应用预览'],['取消预览','恢复当前范围']]):
        for col,text in enumerate(texts):layout.addWidget(buttons[text],row,col)
    e.preview_fill_button=buttons['预览当前范围']
    # Never derive field widths from native QFormLayout policies.
    for widget in [e.fill_scope,e.fill_position,e.fill_time,e.process_mode,e.fill_method]:
        widget.setMinimumWidth(80);widget.setMinimumContentsLength(8)
        widget.setSizeAdjustPolicy(W.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        widget.setSizePolicy(W.QSizePolicy.Policy.Expanding,W.QSizePolicy.Policy.Fixed)

    def update(*_):
        replace=e.process_mode.currentIndex()==1;bezier=e.fill_method.currentData()=='bezier'
        form.setRowVisible(e.fill_position,e.fill_scope.currentIndex()==0)
        form.setRowVisible(frames,e.fill_time.currentIndex()==0)
        algorithm.setRowVisible(e.gap,not replace);algorithm.setRowVisible(e.repair_tension,bezier)
        advanced_form.setRowVisible(e.smooth_fill,not replace and not bezier)
        advanced_form.setRowVisible(e.smooth_strength,not replace and not bezier)
    e.update_fill_page=update
    for widget in [e.fill_scope,e.fill_time,e.process_mode,e.fill_method]:widget.currentIndexChanged.connect(update)
    update()
