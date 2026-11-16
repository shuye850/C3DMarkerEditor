"""One action registry shared by the application menus and frequent tools."""
from PySide6 import QtWidgets as W,QtGui,QtCore

def build_menus(e,toolbar):
    bar=e.menuBar();bar.clear()
    e.menus={name:bar.addMenu(name) for name in ['文件','编辑','标记','播放','视图']}
    e.view_menu=e.menus['视图'];e.commands={};needs_data=[]
    def action(menu,key,label,callback,shortcut=None,data=False,icon=None):
        a=QtGui.QAction(label,e);menu.addAction(a);e.commands[key]=a
        a.triggered.connect(lambda checked=False,fn=callback:fn())
        if shortcut is not None:a.setShortcut(QtGui.QKeySequence(shortcut))
        if icon is not None:a.setIcon(e.style().standardIcon(icon))
        if data:needs_data.append(a)
        return a
    def check(menu,key,label,widget):
        a=QtGui.QAction(label,e);a.setCheckable(True);a.setChecked(widget.isChecked())
        a.toggled.connect(widget.setChecked);widget.toggled.connect(a.setChecked)
        menu.addAction(a);e.commands[key]=a;return a
    def choices(menu,key,labels,combo):
        group=QtGui.QActionGroup(e);group.setExclusive(True)
        for index,label in enumerate(labels):
            a=QtGui.QAction(label,e);a.setCheckable(True);a.setChecked(index==combo.currentIndex());group.addAction(a);menu.addAction(a)
            a.triggered.connect(lambda checked=False,i=index:combo.setCurrentIndex(i))
            combo.currentIndexChanged.connect(lambda value,item=a,i=index:item.setChecked(value==i))
            e.commands[f'{key}_{index}']=a

    standard=W.QStyle.StandardPixmap;keys=QtGui.QKeySequence.StandardKey
    file=e.menus['文件']
    action(file,'open','打开 C3D…',e.open,keys.Open,icon=standard.SP_DialogOpenButton)
    action(file,'load','打开项目…',e.load,'Ctrl+Shift+O',icon=standard.SP_DirOpenIcon)
    file.addSeparator()
    action(file,'save','保存项目',e.save,keys.Save,True,standard.SP_DialogSaveButton)
    action(file,'save_as','项目另存为…',lambda:e.save(True),keys.SaveAs,True)
    file.addSeparator();action(file,'export','导出 C3D…',e.export,'Ctrl+Shift+E',True,standard.SP_ArrowUp)
    file.addSeparator();action(file,'recover','恢复自动备份…',e.recover)
    file.addSeparator();action(file,'close','关闭窗口',e.close,keys.Close)

    edit=e.menus['编辑']
    action(edit,'undo','撤销',lambda:e.history(False),keys.Undo,True,standard.SP_ArrowBack)
    action(edit,'redo','重做',lambda:e.history(True),keys.Redo,True,standard.SP_ArrowForward)

    mark=e.menus['标记']
    action(mark,'pair_begin','进入配对模式',lambda:(e.tabs.setCurrentIndex(0),e.pairing.begin()),data=True)
    action(mark,'pair_commit','确认本次配对',e.pairing.apply,data=True)
    action(mark,'pair_cancel','取消本次配对',e.pairing.cancel,data=True)
    mark.addSeparator();scope=mark.addMenu('标记范围');choices(scope,'scope',['选区标记','整体标记'],e.calibration_scope)
    selection=mark.addMenu('时间选区')
    action(selection,'select_all','选择全程',e.select_full_trial,data=True)
    action(selection,'select_run','选择当前连续片段',e.select_current_segment,data=True)
    mark.addSeparator();ids=mark.addMenu('标记点编号')
    action(ids,'marker_names','编辑标记点编号…',e.pool.edit,data=True)
    action(ids,'split','在当前帧拆分标记点…',e.pool.split,data=True)
    action(mark,'slot_names','建模方案…',e.template,data=True)

    play=e.menus['播放']
    toggle=action(play,'play','播放 / 暂停',e.toggle,'Space',True);toggle.setAutoRepeat(False)
    play.addSeparator()
    action(play,'prev','上一帧',lambda:e.step(-1),'Left',True)
    action(play,'next','下一帧',lambda:e.step(1),'Right',True)
    action(play,'prev10','后退 10 帧',lambda:e.step(-10),'Shift+Left',True)
    action(play,'next10','前进 10 帧',lambda:e.step(10),'Shift+Right',True)

    view=e.view_menu
    layouts=view.addMenu('窗口布局');choices(layouts,'layout',['并排：三维与曲线','上下：三维与曲线','仅三维','仅曲线'],e.view_mode)
    contents=view.addMenu('显示内容')
    for key,title,widget in [('numbers','标记点编号',e.show_numbers),('model','人体连线',e.show_model),('isolated','孤立点',e.show_isolated),('processed','处理后结果',e.show_processed),('original','原始对照',e.show_original)]:check(contents,key,title,widget)
    contents.addSeparator();check(contents,'candidate_pool','展开候选池',e.pool.fold);check(contents,'candidate_colors','候选池中的彩色点',e.pool.colored)
    action(contents,'show_all','显示全部标记点',e.pool.show_all,data=True)
    camera=view.addMenu('三维视角')
    action(camera,'focus','聚焦人体',e.fit_visible,data=True,icon=standard.SP_DesktopIcon)
    action(camera,'room','环境总览',e.fit_environment,data=True)
    action(camera,'reset_camera','重置视角',e.reset_view,data=True)
    time=view.addMenu('时间轴')
    action(time,'full_time','显示完整时间轴',e.full_time,data=True)
    action(time,'zoom_in','放大时间轴',lambda:e.zoom_time(1/1.5),data=True)
    action(time,'zoom_out','缩小时间轴',lambda:e.zoom_time(1.5),data=True)
    view.addSeparator();action(view,'display','显示与环境设置…',e.open_display_settings)
    view.addSeparator();action(view,'reset_layout','恢复默认布局',e.reset_layout)

    # The toolbar contains shortcuts to shared actions, without a second View menu.
    toolbar.setObjectName('workspaceToolbar');toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    for key in ['open','load','save','export']:toolbar.addAction(e.commands[key])
    toolbar.addSeparator()
    for key in ['undo','redo']:toolbar.addAction(e.commands[key])
    spacer=W.QWidget();spacer.setSizePolicy(W.QSizePolicy.Policy.Expanding,W.QSizePolicy.Policy.Preferred);toolbar.addWidget(spacer)
    label=W.QLabel('布局');label.setProperty('role','hint');toolbar.addWidget(label);toolbar.addWidget(e.view_mode)
    toolbar.addSeparator();toolbar.addAction(e.commands['focus']);toolbar.addAction(e.commands['display'])

    def update():
        loaded=e.s is not None
        for item in needs_data:item.setEnabled(loaded)
        editing=e.pairing.editing
        e.commands['pair_begin'].setEnabled(loaded and not editing)
        e.commands['pair_commit'].setEnabled(loaded and editing);e.commands['pair_cancel'].setEnabled(loaded and editing)
        e.commands['undo'].setEnabled(loaded and (editing or bool(e.s.history)))
        e.commands['redo'].setEnabled(loaded and not editing and bool(e.s.future))
        e.commands['play'].setText('暂停' if e.timer.isActive() else '播放')
    e.update_menu_state=update
    for menu in e.menus.values():menu.aboutToShow.connect(update)
    update()
