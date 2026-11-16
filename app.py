import sys, json
import copy
from pathlib import Path
from datetime import datetime
import numpy as np
from PySide6 import QtWidgets as W, QtCore, QtGui
from matplotlib import rcParams
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection
from environment_grid import ground_geometry,units_per_meter
from core import Session
import viewer_axes
from marker_names import display_name,storage_name
from body_model import slot_color,segments
from ui_theme import apply_theme
from player_widgets import Timeline
from pairing_table import PairingPanel
from candidate_pool import CandidatePool
from menu_bar import build_menus
from fill_page import organize_fill_page
from scheme_dialog import SchemeDialog
from runtime_paths import data_dir
rcParams['font.sans-serif']=(['Microsoft YaHei','SimHei','DejaVu Sans'] if sys.platform=='win32' else ['PingFang SC','Heiti TC','Arial Unicode MS','DejaVu Sans'])
rcParams['axes.unicode_minus']=False
rcParams['axes3d.mouserotationstyle']='azel'  # Keep the vertical Z axis upright while orbiting.
rcParams.update({'text.color':'#34445c','axes.labelcolor':'#63738b','xtick.color':'#75839a','ytick.color':'#75839a','axes.edgecolor':'#cdd7e5','axes.spines.top':False,'axes.spines.right':False,'legend.edgecolor':'#dce3ed','legend.fontsize':9})

class Editor(W.QMainWindow):
    def __init__(self,persist_layout=True,layout_path=None):
        super().__init__();self.persist_layout=persist_layout;self.layout_path=Path(layout_path) if layout_path else data_dir()/'ui_settings.ini';self._pending_layout=None;self._layout_show_restored=False;self.s=None;self.project_path=None;self.saved_state=None;self.last_recovery_state=None
        self.selected_source=-1;self.hidden_sources=set();self.hidden_markers=set();self.hidden_slots=set();self.raw_visible=[];self.curve_slot_override=None;self.preview_item=None;self.curve_key=None;self.view_revision=0;self._curve_background=None;self._curve_background_view=None
        self.time_view=None;self.span_selector=None;self.press=None;self.dragging=False;self.shift_down=False;self.drag_pointer=None;self.edge_direction=0;self.edge_strength=0;self.view_zoom=1.05
        self.selection_active=True
        self.setWindowTitle('C3D 点位编辑器');self.resize(1500,1000)
        root=W.QWidget();self.setCentralWidget(root);layout=W.QVBoxLayout(root)
        toolbar=self.addToolBar('常用');toolbar.setMovable(False)
        self.info=W.QLabel('选点 → 选区 → 处理');self.info.setMaximumWidth(450);self.info.setMinimumWidth(0);self.statusBar().addPermanentWidget(self.info)
        split=W.QSplitter();self.main_split=split;layout.addWidget(split,1)
        self.tabs=W.QTabWidget();self.tabs.setMinimumWidth(270);self.tabs.setMaximumWidth(340);split.addWidget(self.tabs)
        calibrate=W.QWidget();page_layout=W.QVBoxLayout(calibrate);page_layout.setContentsMargins(8,8,8,8);page_layout.setSpacing(6);self.tabs.addTab(calibrate,'点位校准')
        controls=W.QWidget();left=W.QVBoxLayout(controls);left.setContentsMargins(0,0,0,0);left.setSpacing(5)
        self.calibration_controls=W.QScrollArea();self.calibration_controls.setObjectName('calibrationControls');self.calibration_controls.setWidgetResizable(True);self.calibration_controls.setWidget(controls);self.calibration_controls.setFrameShape(W.QFrame.Shape.NoFrame);self.calibration_controls.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff);self.calibration_controls.setMaximumHeight(340);self.calibration_controls.setMinimumHeight(80);page_layout.addWidget(self.calibration_controls)
        self.selected_label=W.QLabel('① 在三维预览中点击一个点');self.selected_label.setWordWrap(True);left.addWidget(self.selected_label)
        self.sources=W.QListWidget();self.sources.hide();self.sources.currentRowChanged.connect(self.source_selected);self.sources.itemChanged.connect(self.visibility_changed)
        self.pool=CandidatePool(self);left.addWidget(self.pool)
        self.calibration_scope=W.QComboBox();self.calibration_scope.addItems(['选区标记','整体标记']);left.addWidget(self.calibration_scope)
        self.calibration_scope.currentIndexChanged.connect(lambda *_:self.update_selection_actions())
        left.addWidget(W.QLabel('② 在曲线拖动框选时间'))
        frame_row=W.QHBoxLayout();left.addLayout(frame_row);self.start=W.QSpinBox();self.end=W.QSpinBox()
        frame_row.addWidget(W.QLabel('起'));frame_row.addWidget(self.start);frame_row.addWidget(W.QLabel('止'));frame_row.addWidget(self.end)
        for spin in [self.start,self.end]:spin.setMinimumWidth(0);spin.setSizePolicy(W.QSizePolicy.Policy.Ignored,W.QSizePolicy.Policy.Fixed)
        frame_row.setStretch(1,1);frame_row.setStretch(3,1)
        self.select_all_time=W.QPushButton('全程');self.select_all_time.setToolTip('选择整个文件的时间范围');self.select_all_time.clicked.connect(self.select_full_trial);frame_row.addWidget(self.select_all_time)
        self.start.valueChanged.connect(self.range_changed);self.end.valueChanged.connect(self.range_changed)
        self.range_hint=W.QLabel('单击跳转；Shift＋单击选择连续实测片段。');self.range_hint.setWordWrap(True);left.addWidget(self.range_hint)
        left.addWidget(W.QLabel('③ 这段时间应属于哪个位置？'))
        quick=W.QGroupBox('快速交换');quick_layout=W.QVBoxLayout(quick);left.addWidget(quick)
        self.quick_label=W.QLabel('未选中标记点');quick_layout.addWidget(self.quick_label)
        quick_row=W.QHBoxLayout();quick_layout.addLayout(quick_row);self.target=W.QComboBox();quick_row.addWidget(self.target,1)
        self.target.setSizePolicy(W.QSizePolicy.Policy.Ignored,W.QSizePolicy.Policy.Fixed)
        self.quick_confirm=W.QPushButton('确认');self.quick_confirm.setProperty('role','primary');quick_row.addWidget(self.quick_confirm);self.quick_confirm.clicked.connect(self.confirm_quick_pairing)
        note=W.QLabel('有数据则交换，无数据则接入。\n目标位置的编号固定；区间外不变。');note.setWordWrap(True);left.addWidget(note)
        note.hide()
        self.records=W.QListWidget();self.records.hide()
        self.pairing=PairingPanel(self);page_layout.addWidget(self.pairing,1)
        self.pool.fold.toggled.connect(lambda *_:QtCore.QTimer.singleShot(0,self.update_calibration_height))
        filling=W.QWidget();work_layout=W.QVBoxLayout(filling);self.tabs.addTab(filling,'补帧')
        self.exclude_button=W.QPushButton('排除补帧点…');self.exclude_button.clicked.connect(self.edit_fill_exclusions);work_layout.addWidget(self.exclude_button)
        self.repair_context=W.QLabel('选位置、框选时间，再预览处理。');self.repair_context.setWordWrap(True);work_layout.addWidget(self.repair_context)
        form=W.QFormLayout();work_layout.addLayout(form)
        self.fill_scope=W.QComboBox();self.fill_scope.addItems(['当前选中位置','全部已校准位置']);form.addRow('处理对象',self.fill_scope)
        self.fill_position=W.QComboBox();self.fill_position.currentIndexChanged.connect(self.fill_position_selected);form.addRow('当前点',self.fill_position)
        self.fill_time=W.QComboBox();self.fill_time.addItems(['当前框选区间','整个试验']);form.addRow('时间范围',self.fill_time)
        self.fill_start=W.QSpinBox();self.fill_end=W.QSpinBox();range_row=W.QHBoxLayout();range_row.addWidget(self.fill_start);range_row.addWidget(W.QLabel('至'));range_row.addWidget(self.fill_end);form.addRow('选区帧',range_row)
        self.fill_start.valueChanged.connect(self.start.setValue);self.fill_end.valueChanged.connect(self.end.setValue)
        self.process_mode=W.QComboBox();self.process_mode.addItems(['仅补缺失点 · 保留实测','替换整段 · 包含有效点']);form.addRow('处理方式',self.process_mode)
        self.fill_method=W.QComboBox();self.fill_method.addItem('PCHIP 保形插值','pchip');self.fill_method.addItem('线性插值 / 直线','linear');self.fill_method.addItem('贝塞尔曲线','bezier');form.addRow('算法',self.fill_method)
        self.repair_method=self.fill_method
        self.repair_tension=W.QSlider(QtCore.Qt.Orientation.Horizontal);self.repair_tension.setRange(0,100);self.repair_tension.setValue(70);form.addRow('贝塞尔弯曲',self.repair_tension)
        self.gap=W.QDoubleSpinBox();self.gap.setRange(0,10);self.gap.setDecimals(3);self.gap.setSingleStep(.01);self.gap.setValue(.1);self.gap.setSuffix(' 秒');form.addRow('最大缺口',self.gap)
        self.mode_note=W.QLabel('仅填空白，不改实测点。');self.mode_note.setWordWrap(True);work_layout.addWidget(self.mode_note)
        advanced_button=W.QToolButton();self.advanced_toggle=advanced_button;advanced_button.setText('更多参数 ▸');advanced_button.setCheckable(True);work_layout.addWidget(advanced_button)
        advanced=W.QWidget();advanced_form=W.QFormLayout(advanced);advanced.setVisible(False);work_layout.addWidget(advanced)
        advanced_button.toggled.connect(advanced.setVisible)
        self.fill=W.QCheckBox();self.fill.setVisible(False);self.fill.toggled.connect(self.toggle_fill_results)
        self.smooth_fill=W.QCheckBox('平滑缺口衔接');self.smooth_fill.setChecked(True);advanced_form.addRow(self.smooth_fill)
        self.smooth_strength=W.QSpinBox();self.smooth_strength.setRange(0,100);self.smooth_strength.setValue(100);self.smooth_strength.setSuffix(' %');advanced_form.addRow('平滑强度',self.smooth_strength)
        self.smooth_window=W.QSpinBox();self.smooth_window.setRange(3,31);self.smooth_window.setValue(7);self.smooth_window.setSuffix(' 帧');advanced_form.addRow('单侧参考',self.smooth_window)
        self.smooth_fill.toggled.connect(self.smooth_options_changed)
        buttons=W.QHBoxLayout();work_layout.addLayout(buttons)
        b=W.QPushButton('预览当前范围');b.clicked.connect(self.preview_process);buttons.addWidget(b)
        self.commit_button=W.QPushButton('应用预览');self.commit_button.setEnabled(False);self.commit_button.clicked.connect(self.commit_repair);buttons.addWidget(self.commit_button)
        buttons=W.QHBoxLayout();work_layout.addLayout(buttons)
        b=W.QPushButton('取消预览');b.clicked.connect(self.cancel_repair);buttons.addWidget(b)
        b=W.QPushButton('恢复当前范围');b.clicked.connect(self.remove_current_processing);buttons.addWidget(b)
        b=W.QPushButton('批量补帧：全部位置 · 全程');b.clicked.connect(self.batch_fill);work_layout.addWidget(b)
        self.review_toggle=W.QCheckBox('显示检查清单');self.review_toggle.toggled.connect(self.update_review_visibility);work_layout.addWidget(self.review_toggle)
        b=W.QPushButton('扫描当前范围');b.clicked.connect(lambda:self.scan_and_show());work_layout.addWidget(b)
        self.fill_summary=W.QLabel('当前范围可单独处理，也可一键批量。');self.fill_summary.setWordWrap(True);work_layout.addWidget(self.fill_summary)
        work_layout.addStretch()
        self.gap_filter=W.QComboBox();self.gap_filter.addItems(['全部检查项','仅待检查']);self.gap_filter.currentIndexChanged.connect(self.render_gap_rows)
        self.gaps=W.QTableWidget(0,4);self.gaps.setHorizontalHeaderLabels(['位置','帧区间','秒','状态']);self.gaps.setEditTriggers(W.QAbstractItemView.EditTrigger.NoEditTriggers);self.gaps.setSelectionBehavior(W.QAbstractItemView.SelectionBehavior.SelectRows);self.gaps.cellDoubleClicked.connect(self.goto_gap)
        self.fill_method.currentIndexChanged.connect(self.algorithm_options_changed);self.process_mode.currentIndexChanged.connect(self.algorithm_options_changed)
        self.fill_scope.currentIndexChanged.connect(self.cancel_repair);self.fill_time.currentIndexChanged.connect(self.algorithm_options_changed);self.repair_tension.valueChanged.connect(self.cancel_repair)
        viewer=W.QWidget();v=W.QVBoxLayout(viewer);v.setContentsMargins(0,0,0,0);split.addWidget(viewer);split.setSizes([330,1170]);split.setStretchFactor(1,1)
        self.view_mode=W.QComboBox();self.view_mode.addItems(['并排视图','上下视图','三维视图','曲线视图']);self.view_mode.currentIndexChanged.connect(self.change_view_mode)
        self.show_isolated=W.QCheckBox('显示曲线孤立点');self.show_isolated.setChecked(True);self.show_isolated.setToolTip('只控制曲线上孤立有效点的圆点显示，不删除数据、不影响补帧');self.show_isolated.toggled.connect(self.draw)
        self.display_dialog=W.QDialog(self);self.display_dialog.setWindowTitle('显示与环境设置');dialog_layout=W.QVBoxLayout(self.display_dialog)
        settings=W.QWidget();settings_form=W.QFormLayout(settings);dialog_layout.addWidget(settings)
        self.zoom=W.QSlider(QtCore.Qt.Orientation.Horizontal);self.zoom.setRange(50,300);self.zoom.setValue(105);self.zoom.valueChanged.connect(self.change_zoom);settings_form.addRow('三维缩放',self.zoom)
        self.point_size=W.QSlider(QtCore.Qt.Orientation.Horizontal);self.point_size.setRange(3,80);self.point_size.setValue(14);self.point_size.valueChanged.connect(self.draw);settings_form.addRow('点大小',self.point_size)
        self.show_processed=W.QCheckBox('显示处理后结果');self.show_processed.setChecked(True);self.show_original=W.QCheckBox('叠加原始对照');self.show_original.setChecked(True)
        self.show_numbers=W.QCheckBox('显示编号');self.show_model=W.QCheckBox('人体连线')
        for cb in [self.show_processed,self.show_original,self.show_numbers,self.show_model]:cb.toggled.connect(self.draw);settings_form.addRow(cb)
        settings_form.addRow(self.show_isolated)
        self.plane=W.QComboBox();self.plane.addItems(['固定地面','固定天花板','隐藏参考面']);self.plane.currentIndexChanged.connect(self.change_plane);settings_form.addRow('参考面',self.plane)
        self.plane_height=W.QDoubleSpinBox();self.plane_height.setRange(-1e7,1e7);self.plane_height.setDecimals(1);self.plane_height.valueChanged.connect(self.draw);settings_form.addRow('参考高度',self.plane_height)
        self.ground_step=W.QDoubleSpinBox();self.ground_step.setRange(.001,1e7);self.ground_step.setDecimals(3);self.ground_step.setValue(500);self.ground_step.valueChanged.connect(self.draw);settings_form.addRow('地面网格间距',self.ground_step)
        self.ground_span=W.QDoubleSpinBox();self.ground_span.setRange(2,200);self.ground_span.setValue(10);self.ground_span.setSuffix(' m');self.ground_span.valueChanged.connect(self.configure_environment);settings_form.addRow('房间地面边长',self.ground_span)
        close=W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Close);close.rejected.connect(self.display_dialog.hide);dialog_layout.addWidget(close)
        close.button(W.QDialogButtonBox.StandardButton.Close).setText('完成')
        self.work_split=W.QSplitter(QtCore.Qt.Orientation.Vertical);v.addWidget(self.work_split,1)
        self.plot_split=W.QSplitter(QtCore.Qt.Orientation.Horizontal);self.work_split.addWidget(self.plot_split)
        self.fig=Figure();self.canvas=FigureCanvasQTAgg(self.fig);self.ax=self.fig.add_axes([0,.01,1,.97],projection='workspace3d');self.ax.set_proj_type('ortho');self.ax.computed_zorder=False
        self.curve_fig=Figure();self.curve_canvas=FigureCanvasQTAgg(self.curve_fig);self.curve_canvas.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus);self.curve=self.curve_fig.add_subplot(111);self.curve_fig.subplots_adjust(left=.075,right=.985,bottom=.24,top=.80)
        self.plot_split.addWidget(self.canvas);self.plot_split.addWidget(self.curve_canvas);self.plot_split.setSizes([380,790]);self.canvas.setMinimumWidth(240);self.curve_canvas.setMinimumWidth(360);self.curve_canvas.setMinimumHeight(220)
        self.review=W.QWidget();review=self.review;review_layout=W.QVBoxLayout(review);review_layout.setContentsMargins(0,0,0,0)
        review_controls=W.QHBoxLayout();review_layout.addLayout(review_controls);review_controls.addWidget(W.QLabel('缺口检查（双击定位）'));review_controls.addWidget(self.gap_filter)
        for title,fn in [('预览当前项',self.preview_process),('恢复当前项',self.remove_current_processing)]:
            b=W.QPushButton(title);b.clicked.connect(fn);review_controls.addWidget(b)
        review_layout.addWidget(self.gaps);self.work_split.addWidget(review);self.work_split.setSizes([780,180]);review.setVisible(False)
        self.gaps.horizontalHeader().setSectionResizeMode(W.QHeaderView.ResizeMode.Stretch)
        time_controls=W.QHBoxLayout();v.addLayout(time_controls)
        for title,fn in [('时间 −',lambda:self.zoom_time(1.5)),('时间 ＋',lambda:self.zoom_time(1/1.5)),('显示全程',self.full_time)]:
            b=W.QPushButton(title);b.clicked.connect(fn);time_controls.addWidget(b)
        self.time_scroll=W.QScrollBar(QtCore.Qt.Orientation.Horizontal);self.time_scroll.setRange(0,10000);self.time_scroll.valueChanged.connect(self.pan_time);time_controls.addWidget(self.time_scroll,1)
        time_controls.setSpacing(4)
        playback=W.QHBoxLayout();layout.addLayout(playback)
        self.back10=W.QPushButton('');self.back10.setIcon(self.style().standardIcon(W.QStyle.StandardPixmap.SP_MediaSeekBackward));self.back10.setToolTip('后退 10 帧 · Shift＋←');self.back10.clicked.connect(lambda:self.step(-10));playback.addWidget(self.back10)
        self.play=W.QPushButton('');self.play.setProperty('role','primary');self.play.setToolTip('播放 / 暂停 · 空格');self.play.clicked.connect(self.toggle);playback.addWidget(self.play)
        self.forward10=W.QPushButton('');self.forward10.setIcon(self.style().standardIcon(W.QStyle.StandardPixmap.SP_MediaSeekForward));self.forward10.setToolTip('前进 10 帧 · Shift＋→');self.forward10.clicked.connect(lambda:self.step(10));playback.addWidget(self.forward10)
        for button in [self.back10,self.play,self.forward10]:button.setFixedSize(36,32)
        self.slider=Timeline();playback.addWidget(self.slider,1)
        self.slider.selectionCleared.connect(self.clear_selection)
        self.timecode=W.QLabel('00:00.000 / 00:00.000');playback.addWidget(self.timecode)
        self.frame=W.QSpinBox();playback.addWidget(self.frame)
        self.frame.setAccelerated(True);self.frame.setKeyboardTracking(False);self.frame.setMinimumWidth(88);self.frame.setToolTip('当前帧 · 长按加减按钮可加速')
        self.slider.valueChanged.connect(self.frame.setValue);self.frame.valueChanged.connect(self.slider.setValue);self.frame.valueChanged.connect(self.frame_changed)
        self.timer=QtCore.QTimer();self.timer.timeout.connect(self.tick)
        self.edge_timer=QtCore.QTimer(self);self.edge_timer.setInterval(40);self.edge_timer.timeout.connect(self.edge_scroll_tick)
        self.curve_canvas.installEventFilter(self)
        self.tabs.currentChanged.connect(self.update_review_visibility)
        self.algorithm_options_changed()
        self.canvas.mpl_connect('motion_notify_event',self.ground_camera_moved);self.canvas.mpl_connect('button_release_event',self.ground_camera_released)
        self.canvas.mpl_connect('pick_event',self.pick);self.canvas.mpl_connect('scroll_event',self.scroll_3d)
        self.curve_canvas.mpl_connect('draw_event',self.curve_drawn)
        self.curve_canvas.mpl_connect('resize_event',self.curve_resized)
        self.curve_canvas.mpl_connect('button_press_event',self.curve_press);self.curve_canvas.mpl_connect('button_release_event',self.curve_release);self.curve_canvas.mpl_connect('motion_notify_event',self.curve_motion);self.curve_canvas.mpl_connect('key_press_event',self.curve_key_press);self.curve_canvas.mpl_connect('key_release_event',self.curve_key_release);self.curve_canvas.mpl_connect('scroll_event',self.curve_scroll)
        organize_fill_page(self,filling)
        build_menus(self,toolbar)
        apply_theme(self)
        for widget in [self.selected_label,self.range_hint,self.repair_context,self.mode_note,self.fill_summary]:widget.hide()
        for label in calibrate.findChildren(W.QLabel):
            if label.text().startswith(('②','③')):label.hide()
        self.update_transport()
        self.restore_layout()

    def open_display_settings(self):
        self.display_dialog.show();self.display_dialog.raise_();self.display_dialog.activateWindow()
    def update_calibration_height(self):
        if not hasattr(self,'pairing'):return
        preferred=self.calibration_controls.widget().sizeHint().height()+4
        available=max(80,self.tabs.height()-self.pairing.minimumSizeHint().height()-38)
        self.calibration_controls.setFixedHeight(max(80,min(preferred,340,available)))
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'pairing'):QtCore.QTimer.singleShot(0,self.update_calibration_height)
    def layout_settings(self):
        # Older versions saved NumPy camera scalars as Python object variants.
        # QSettings parses the entire INI on its first value() call, so remove
        # these obsolete values before asking Qt to deserialize any setting.
        if self.layout_path.exists():
            content=self.layout_path.read_text(encoding='utf-8')
            lines=content.splitlines(keepends=True)
            safe=[line for line in lines if 'PySide::PyObjectWrapper' not in line]
            if safe!=lines:
                backup=self.layout_path.with_suffix('.ini.legacy-backup')
                if not backup.exists():backup.write_text(content,encoding='utf-8')
                self.layout_path.write_text(''.join(safe),encoding='utf-8')
        return QtCore.QSettings(str(self.layout_path),QtCore.QSettings.Format.IniFormat)
    def save_layout(self):
        if not self.persist_layout:return
        settings=self.layout_settings()
        settings.setValue('geometry',self.saveGeometry())
        for key,splitter in [('sidebar',self.main_split),('views',self.plot_split),('review',self.work_split)]:settings.setValue(key,splitter.saveState())
        for key,widget in [('tab',self.tabs),('view_mode',self.view_mode),('gap_filter',self.gap_filter),('pairing_mode',self.pairing.mode),('calibration_scope',self.calibration_scope)]:settings.setValue(key,widget.currentIndex())
        for key,widget in [('review_open',self.review_toggle),('advanced_open',self.advanced_toggle),('isolated',self.show_isolated),('processed',self.show_processed),('original',self.show_original),('numbers',self.show_numbers),('model',self.show_model)]:settings.setValue(key,widget.isChecked())
        settings.setValue('point_size',self.point_size.value());settings.setValue('zoom',self.zoom.value())
        settings.setValue('pool_open',self.pool.fold.isChecked());settings.setValue('pool_colored',self.pool.colored.isChecked())
        settings.setValue('camera',json.dumps([float(self.ax.elev),float(self.ax.azim),0.]));settings.setValue('ground_span',self.ground_span.value());settings.setValue('plane_mode',self.plane.currentIndex())
        if self.s and self.meter_factor:
            settings.setValue('ground_step_m',self.ground_step.value()/self.meter_factor);settings.setValue('plane_height_m',self.plane_height.value()/self.meter_factor)
        settings.sync()
        if settings.status()!=QtCore.QSettings.Status.NoError:self.statusBar().showMessage('布局保存失败，请检查配置文件写入权限。')
    def restore_layout(self):
        if not self.persist_layout:return
        try:self.restore_layout_values()
        except (RuntimeError,ValueError,TypeError,OSError):
            self._pending_layout=None
            self.statusBar().showMessage('部分布局配置无法读取，已使用默认布局；项目数据不受影响。')
    def restore_layout_values(self):
        settings=self.layout_settings()
        if not settings.contains('geometry'):
            self.setWindowState(self.windowState()|QtCore.Qt.WindowState.WindowMaximized);return
        self.restoreGeometry(settings.value('geometry'))
        self.tabs.setCurrentIndex(settings.value('tab',0,type=int));self.view_mode.setCurrentIndex(settings.value('view_mode',0,type=int));self.gap_filter.setCurrentIndex(settings.value('gap_filter',0,type=int))
        self.pairing.mode.setCurrentIndex(settings.value('pairing_mode',0,type=int))
        self.calibration_scope.setCurrentIndex(settings.value('calibration_scope',0,type=int))
        self.pool.fold.setChecked(settings.value('pool_open',True,type=bool));self.pool.colored.setChecked(settings.value('pool_colored',True,type=bool))
        for key,widget,default in [('review_open',self.review_toggle,False),('advanced_open',self.advanced_toggle,False),('isolated',self.show_isolated,True),('processed',self.show_processed,True),('original',self.show_original,True),('numbers',self.show_numbers,False),('model',self.show_model,False)]:widget.setChecked(settings.value(key,default,type=bool))
        self.point_size.setValue(settings.value('point_size',14,type=int));self.zoom.setValue(settings.value('zoom',105,type=int));self.ground_span.setValue(settings.value('ground_span',10.,type=float));self.plane.setCurrentIndex(settings.value('plane_mode',0,type=int))
        camera=settings.value('camera','[30,-60,0]')
        if isinstance(camera,str):camera=json.loads(camera)
        camera=[float(x) for x in camera]
        if len(camera)!=3 or not all(np.isfinite(camera)):raise ValueError('Invalid camera')
        # Older layouts may contain an arcball roll. Preserve their viewing
        # direction but reset roll so the ground remains level.
        self.ax.view_init(camera[0],camera[1],roll=0)
        self._pending_layout={key:settings.value(key) for key in ['sidebar','views','review']}
        self.update_review_visibility()
    def showEvent(self,event):
        super().showEvent(event)
        if self._pending_layout and not self._layout_show_restored:
            self._layout_show_restored=True;QtCore.QTimer.singleShot(0,self.restore_splitters)
    def restore_splitters(self):
        if not self._pending_layout:return
        for key,splitter in [('sidebar',self.main_split),('views',self.plot_split),('review',self.work_split)]:
            if self._pending_layout.get(key) is not None:splitter.restoreState(self._pending_layout[key])
        self._pending_layout=None
    def reset_layout(self):
        self.tabs.setCurrentIndex(0);self.view_mode.setCurrentIndex(0);self.review_toggle.setChecked(False);self.advanced_toggle.setChecked(False)
        self.main_split.setSizes([300,1200]);self.plot_split.setSizes([380,790]);self.work_split.setSizes([780,180]);self.showMaximized()
    def environment_preference(self,key,default):
        if not self.persist_layout:return default
        try:return self.layout_settings().value(key,default,type=float)
        except (RuntimeError,ValueError,TypeError,OSError):return default

    def edit_fill_exclusions(self):
        if not self.s:return
        dialog=W.QDialog(self);dialog.setWindowTitle('排除补帧点');dialog.resize(400,540)
        layout=W.QVBoxLayout(dialog);layout.addWidget(W.QLabel('勾选＝不补帧、不替换。实测保留；已有生成结果停止应用。'))
        listing=W.QListWidget();layout.addWidget(listing)
        for name in self.s.slots:
            item=W.QListWidgetItem(display_name(name));item.setData(QtCore.Qt.ItemDataRole.UserRole,name)
            item.setFlags(item.flags()|QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.CheckState.Checked if name in self.s.fill_excluded else QtCore.Qt.CheckState.Unchecked);listing.addItem(item)
        reset=W.QPushButton('恢复默认排除');reset.setToolTip('默认排除当前方案人体点之外的附加标记点');layout.addWidget(reset)
        def defaults():
            for i in range(listing.count()):
                item=listing.item(i);item.setCheckState(QtCore.Qt.CheckState.Checked if item.data(QtCore.Qt.ItemDataRole.UserRole) in self.s.default_fill_exclusions() else QtCore.Qt.CheckState.Unchecked)
        reset.clicked.connect(defaults)
        buttons=W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Ok|W.QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
        buttons.button(W.QDialogButtonBox.StandardButton.Ok).setText('确定');buttons.button(W.QDialogButtonBox.StandardButton.Cancel).setText('取消')
        if dialog.exec()!=W.QDialog.DialogCode.Accepted:return
        names=[listing.item(i).data(QtCore.Qt.ItemDataRole.UserRole) for i in range(listing.count()) if listing.item(i).checkState()==QtCore.Qt.CheckState.Checked]
        self.s.set_fill_excluded(names);self.refresh()
        if self.batch_review:self.scan_gaps(True)
        else:self.all_gap_rows=[];self.render_gap_rows()
    def sync_fill_range(self):
        for source,target in [(self.start,self.fill_start),(self.end,self.fill_end)]:
            target.blockSignals(True);target.setRange(source.minimum(),source.maximum());target.setValue(source.value());target.blockSignals(False)
    def algorithm_options_changed(self,*_):
        if not hasattr(self,'process_mode'):return
        replace=self.process_mode.currentIndex()==1;bezier=self.fill_method.currentData()=='bezier'
        if replace and self.fill_time.currentIndex()!=0:self.fill_time.setCurrentIndex(0)
        self.fill_time.setEnabled(not replace);self.gap.setEnabled(not replace)
        self.fill_start.setEnabled(self.fill_time.currentIndex()==0);self.fill_end.setEnabled(self.fill_time.currentIndex()==0)
        self.repair_tension.setEnabled(bezier);self.smooth_fill.setEnabled(not replace and not bezier);self.smooth_strength.setEnabled(not replace and not bezier and self.smooth_fill.isChecked())
        self.mode_note.setText('替换选区内部的有效点和缺失点；两端可靠点保留，需预览后应用。' if replace else '只填缺失点，保留所有实测点；当前点/选区和全部点/全程都可处理。')
        self.cancel_repair()
    def update_review_visibility(self,*_):
        if hasattr(self,'review'):self.review.setVisible(self.tabs.currentIndex()==1 and self.review_toggle.isChecked())
    def scan_and_show(self):
        self.scan_gaps(False);self.review_toggle.setChecked(True);self.update_review_visibility()
    def change_view_mode(self,*_):
        if not hasattr(self,'plot_split'):return
        mode=self.view_mode.currentIndex()
        self.canvas.setVisible(mode!=3);self.curve_canvas.setVisible(mode!=2)
        self.plot_split.setOrientation(QtCore.Qt.Orientation.Vertical if mode==1 else QtCore.Qt.Orientation.Horizontal)
        self.plot_split.setSizes([520,280] if mode==1 else [380,790])
        QtCore.QTimer.singleShot(0,self.fit_visible)
    def processing_arguments(self):
        names,start,end=self.fill_parameters()
        return dict(slots=names,start=start,end=end,method=self.fill_method.currentData(),max_gap_seconds=self.gap.value(),smooth_strength=self.smooth_strength.value()/100 if self.smooth_fill.isChecked() else 0.,smooth_window=self.smooth_window.value(),tension=self.repair_tension.value()/100)
    def preview_process(self):
        if not self.s:return
        def run():
            settings=self.processing_arguments();names=settings['slots'];start,end=settings['start'],settings['end']
            replace=self.process_mode.currentIndex()==1
            if replace:
                items=[];result=tuple(array.copy() for array in self.built)
                for name in names:
                    try:item=self.s.repair_preview(name,start,end,settings['method'],settings['tension'],settings['smooth_window'])
                    except ValueError as error:raise ValueError(display_name(name)+'：'+str(error))
                    items.append(item);j=self.s.slots.index(name);lo,hi=item['start'],item['end']
                    result[0][:,j,lo:hi+1]=np.asarray(item['values']);result[1][j,lo:hi+1]=3;result[2][j,lo:hi+1]=-1
                plan=dict(kind='replace',items=items,start=min(item['start'] for item in items),end=max(item['end'] for item in items),settings=settings)
            else:
                clone=copy.copy(self.s);clone.fill_jobs=copy.deepcopy(self.s.fill_jobs);clone.history=[];clone.future=[]
                clone.add_fill_job(**settings);result=clone.build();plan=dict(kind='gaps',start=start,end=end,settings=settings)
            self.preview_item=plan;self.preview_result=result;self.commit_button.setEnabled(True);self.curve_key=None;self.show_processed.setChecked(True)
            self.repair_context.setText(f"预览：{len(names)} 个位置，帧 {plan['start']+self.s.first}–{plan['end']+self.s.first}，{self.fill_method.currentText()}。{'包含有效点替换' if replace else '仅补缺失'}，尚未应用。")
            self.draw()
        self.guard(run)
    def commit_process_plan(self):
        plan=self.preview_item
        if plan['kind']=='gaps':self.s.add_fill_job(**plan['settings'])
        else:
            self.s.checkpoint()
            if any(item['slot'] in self.s.fill_excluded for item in plan['items']):raise ValueError('预览中的位置已排除补帧')
            if self.s.fill_enabled and self.s.fill_jobs is None:self.s.fill_jobs=copy.deepcopy(self.s.fill_plans())
            self.s.repairs.extend(copy.deepcopy(plan['items']));self.s.fill_method=plan['settings']['method'];self.s.fill_tension=plan['settings']['tension']
        self.refresh();self.scan_gaps(self.batch_review)
        self.repair_context.setText('处理已应用。同色系浅色实线为处理结果，可撤销。')
    def remove_current_processing(self):
        if not self.s:return
        def run():
            names,start,end=self.fill_parameters();clone=copy.copy(self.s);clone.history=[];clone.future=[]
            clone.fill_jobs=copy.deepcopy(self.s.fill_jobs);clone.repairs=copy.deepcopy(self.s.repairs)
            clone.remove_fill_range(names,start,end)
            for name in names:clone.remove_repairs(name,start,end)
            self.s.checkpoint();self.s.fill_jobs=clone.fill_jobs;self.s.repairs=clone.repairs
            self.refresh();self.scan_gaps(self.batch_review)
        self.guard(run)
    def guard(self,fn):
        try:return fn()
        except Exception as e:W.QMessageBox.critical(self,'操作失败',str(e))
    def choose(self,title,kind,save=False,initial_path=None):
        fn=W.QFileDialog.getSaveFileName if save else W.QFileDialog.getOpenFileName
        return fn(self,title,str(initial_path or ''),kind)[0]
    def open(self):
        p=self.choose('打开原始文件','C3D (*.c3d)')
        if p and self.confirm_switch():self.guard(lambda:self.set_session(Session(p)))
    def load(self):
        p=self.choose('打开项目','JSON (*.json)')
        if p and self.confirm_switch():self.guard(lambda:self.set_session(Session.load_project(p),p))
    def save(self,save_as=False):
        if not self.s:return False
        if self.pairing.has_pending():self.statusBar().showMessage('请先点击“确定配对”或取消本次配对模式，再保存项目。');return False
        if self.preview_item is not None:
            W.QMessageBox.information(self,'尚在预览','请先应用或取消修复预览，再保存。');return False
        p=None if save_as else self.project_path
        if not p:p=self.choose('保存完整项目（包含所有已确认配对）','JSON (*.json)',True,self.s.path.with_suffix('.project.json'))
        if not p:return False
        p=str(p)
        if not p.lower().endswith('.json'):p+='.json'
        try:
            self.s.save_project(p)
            verified=Session.load_project(p)
            if verified.snapshot()!=self.s.snapshot():raise IOError('重新加载核验失败')
            self.project_path=Path(p).resolve();self.saved_state=self.s.snapshot();self.update_save_status()
            count=len(self.s.assignments);slots=len({a['slot'] for a in self.s.assignments})
            self.statusBar().showMessage(f'保存成功并核验：{slots} 个已配对槽位 / {count} 条轨迹片段 / {len(self.s.identity_edits)} 次编号修正 / {len(self.s.repairs)} 次整段修复 | {self.project_path}')
            return True
        except Exception as e:
            W.QMessageBox.critical(self,'保存失败',str(e));return False
    def confirm_switch(self):
        if not self.s or (self.s.snapshot()==self.saved_state and not self.pairing.has_pending()):return True
        answer=W.QMessageBox.question(self,'存在未保存配对','是否先保存当前项目？',
            W.QMessageBox.StandardButton.Save|W.QMessageBox.StandardButton.Discard|W.QMessageBox.StandardButton.Cancel,
            W.QMessageBox.StandardButton.Save)
        if answer==W.QMessageBox.StandardButton.Save:
            if self.pairing.editing and not self.pairing.apply():return False
            return self.save()
        return answer==W.QMessageBox.StandardButton.Discard
    def closeEvent(self,event):
        if self.confirm_switch():self.timer.stop();self.edge_timer.stop();self.save_layout();event.accept()
        else:event.ignore()
    def update_save_status(self):
        dirty=self.s is not None and (self.s.snapshot()!=self.saved_state or self.pairing.has_pending())
        name=Path(self.project_path).name if self.project_path else '尚未保存项目'
        count=len(self.s.assignments) if self.s else 0
        slots=len({a['slot'] for a in self.s.assignments}) if self.s else 0
        self.setWindowTitle(f"C3D 标记点编辑器 · {name}{' *' if dirty else ''} · 已配对 {slots} 点 / {count} 片段 / {len(self.s.identity_edits) if self.s else 0} 次编号修正 / {len(self.s.repairs) if self.s else 0} 次整段修复")
        if hasattr(self,'update_menu_state'):self.update_menu_state()
    def write_recovery(self):
        state=self.s.snapshot()
        if state==self.last_recovery_state:return
        try:
            folder=data_dir()/'自动恢复';folder.mkdir(exist_ok=True)
            target=folder/(self.s.path.stem+'_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.json')
            self.s.save_project(target);self.last_recovery_state=state
        except Exception as e:
            self.statusBar().showMessage('自动恢复副本保存失败，请手动保存：'+str(e))
    def recover(self):
        folder=data_dir()/'自动恢复';folder.mkdir(exist_ok=True)
        p=W.QFileDialog.getOpenFileName(self,'选择恢复副本（按时间选择）',str(folder),'JSON (*.json)')[0]
        if p and self.confirm_switch():
            self.guard(lambda:self.set_session(Session.load_project(p)))
            if self.s:self.saved_state=None;self.update_save_status()
    def export(self):
        if not self.s:return
        if self.pairing.has_pending():self.statusBar().showMessage('请先确定或取消本次配对，再导出。');return
        if self.preview_item is not None:
            W.QMessageBox.information(self,'尚在预览','请先应用或取消预览，再导出。');return
        p=self.choose('导出（另存为）','C3D (*.c3d)',True,self.s.path.with_name(self.s.path.stem+'_edited.c3d'))
        if p:
            def run():
                target=p if p.lower().endswith('.c3d') else p+'.c3d'
                self.s.export(target)
                W.QMessageBox.information(self,'完成','已导出 C3D、项目 JSON 和补帧来源 NPZ。未分配的有效原始片段保留为 RAW 点。')
            self.guard(run)
    def set_session(self,s,project_path=None):
        self.pairing._leave()
        self.timer.stop();self.edge_timer.stop();self.press=None;self.dragging=False;self.drag_pointer=None
        if hasattr(self,'built'):del self.built
        self.preview_item=None;self.curve_key=None
        self.s=s;self.project_path=Path(project_path).resolve() if project_path else None
        self.selection_active=True
        self.pool.selected=None
        self.hidden_markers.clear()
        self.slider.first_frame=s.first;self.slider.rate=s.rate
        self.batch_review=False;self.all_gap_rows=[];self.gap_rows=[];self.gaps.setRowCount(0)
        self.saved_state=s.snapshot();self.last_recovery_state=s.snapshot();self.hidden_sources=set();self.selected_source=-1;self.curve_slot_override=None
        for widget in [self.start,self.end,self.frame,self.slider,self.fill_start,self.fill_end]:
            widget.blockSignals(True);widget.setRange(s.first,s.first+s.frames-1);widget.setValue(s.first);widget.blockSignals(False)
        for widget in [self.start,self.end,self.fill_start,self.fill_end]:widget.setMinimum(s.first-1);widget.setSpecialValueText('—')
        self.end.setValue(s.first+s.frames-1)
        self.time_view=(0,max((s.frames-1)/s.rate,1/s.rate))
        measured=s.points[:3,:, :][:,s.valid];self.ceiling=float(measured[2].max()+50) if measured.size else 2000.
        self.coordinate_unit=str((s.c3d['parameters']['POINT']['UNITS']['value'] or ['单位'])[0]);self.meter_factor=units_per_meter(self.coordinate_unit)
        self.plane_height.setSuffix(' '+self.coordinate_unit)
        self.ground_step.blockSignals(True);self.ground_step.setValue(self.environment_preference('ground_step_m',.5)*self.meter_factor if self.meter_factor else 100);self.ground_step.setSuffix(' '+self.coordinate_unit);self.ground_step.blockSignals(False)
        self.ground_span.setEnabled(self.meter_factor is not None);self.configure_environment()
        self.change_plane()
        if self.meter_factor:self.plane_height.setValue(self.environment_preference('plane_height_m',self.plane_height.value()/self.meter_factor)*self.meter_factor)
        self.refresh();self.fit_visible()
        self.info.setText(f'{s.path.name} · {s.frames} 帧 · {s.rate:g} Hz')
        self.update_transport()
    def refresh(self):
        if not self.s:return
        if self.pool.selected is not None and self.pool.selected>=len(self.s.markers):self.pool.selected=None
        self.hidden_markers.intersection_update(range(len(self.s.markers)))
        self.pairing.refresh()
        self.exclude_button.setText(f'排除补帧点…（已排除 {len(self.s.fill_excluded)} 个）')
        self.preview_item=None;self.commit_button.setEnabled(False);self.view_revision+=1;self.curve_key=None
        self.measured_built=self.s.build(fill=False,repair=False);self.built=self.s.build();self.sources.blockSignals(True);self.sources.clear()
        for i,name in enumerate(self.s.labels):
            label=self.point_name(i)
            item=W.QListWidgetItem(label);item.setFlags(item.flags()|QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.CheckState.Unchecked if i in self.hidden_sources else QtCore.Qt.CheckState.Checked)
            self.sources.addItem(item)
        self.sources.setCurrentRow(self.selected_source);self.sources.blockSignals(False)
        old=self.target.currentData();self.target.clear()
        for number,name in enumerate(self.s.slots,1):self.target.addItem(f'{number:02d} · {display_name(name)}',name)
        i=self.target.findData(old);self.target.setCurrentIndex(max(i,0))
        self.records.clear()
        for number,name in enumerate(self.s.slots,1):
            used=any(a['slot']==name for a in self.s.assignments)
            item=W.QListWidgetItem(f'{number:02d} · {display_name(name)}'+(' ✓' if used else '（空）'))
            item.setData(QtCore.Qt.ItemDataRole.UserRole,name);self.records.addItem(item)

        self.fill_position.blockSignals(True);self.fill_position.clear();self.fill_position.addItem('请选择位置 / 在三维图点选',None)
        for name in dict.fromkeys(a['slot'] for a in self.s.assignments):self.fill_position.addItem(display_name(name),name)
        self.fill_position.blockSignals(False);self.sync_fill_position()
        self.fill.blockSignals(True);self.fill.setChecked(self.s.fill_enabled);self.fill.blockSignals(False)
        self.gap.setValue(self.s.max_gap_seconds);self.fill_method.setCurrentIndex(max(0,self.fill_method.findData(self.s.fill_method)))
        new_settings=not self.s.fill_enabled and self.s.fill_jobs is None
        self.smooth_fill.blockSignals(True);self.smooth_fill.setChecked(new_settings or self.s.fill_smoothing>0);self.smooth_fill.blockSignals(False)
        self.smooth_strength.setValue(100 if new_settings else round(self.s.fill_smoothing*100));self.smooth_window.setValue(self.s.fill_smooth_window)
        self.smooth_strength.setEnabled(self.smooth_fill.isChecked());self.smooth_window.setEnabled(self.smooth_fill.isChecked())
        self.repair_tension.blockSignals(True);self.repair_tension.setValue(round(self.s.fill_tension*100));self.repair_tension.blockSignals(False)
        self.sync_fill_range()
        self.fill_summary.setText(f'补缺失 {int(np.count_nonzero(self.built[1]==2))} 帧，整段修复 {int(np.count_nonzero(self.built[1]==3))} 帧（均为各位置累计）。')
        self.draw();self.write_recovery();self.update_save_status()
        self.pool.refresh()
        self.sync_marker_selection()
    def point_name(self,index):
        marker=self.s.public_marker_for(index,self.frame.value()-self.s.first)
        if marker is not None:return self.s.markers[marker]['label']
        names=list(dict.fromkeys(a['slot'] for a in self.s.assignments if a['source']==index))
        if names:return f'R{index} · '+ ' / '.join(display_name(name) for name in names)
        if index>=len(self.s.base_labels):return f'R{index}（未配对）'
        return f'原始 R{index} · {self.s.labels[index]}'
    def sync_fill_position(self):
        self.fill_position.blockSignals(True);self.fill_position.setCurrentIndex(max(0,self.fill_position.findData(self.selected_slot())));self.fill_position.blockSignals(False)
    def fill_position_selected(self,*_):
        if not self.s:return
        name=self.fill_position.currentData()
        if name in self.s.slots:self.position_selected(self.records.item(self.s.slots.index(name)))
    def source_selected(self,row,marker_override=None):
        if not self.s or row<0:return
        self.cancel_repair(redraw=False)
        self.selected_source=row;self.curve_slot_override=None
        marker=marker_override if marker_override is not None else self.s.public_marker_for(row,self.frame.value()-self.s.first)
        if marker is not None:self.pool.selected=marker
        self.sync_fill_position()
        self.selected_label.setText('① 已选 '+self.point_name(row))
        self.repair_context.setText(f'当前：{display_name(self.selected_slot()) if self.selected_slot() else self.point_name(row)}，选区 {self.start.value()}–{self.end.value()} 帧。')
        self.draw()
        self.pairing.preview_selected(row)
        self.pool.fold.setChecked(True)
        self.sync_marker_selection()

    def calibration_range(self):
        if self.calibration_scope.currentIndex()==1:return 0,self.s.frames-1
        if not self.selection_active:raise ValueError('当前没有选区，请先框选时间范围。')
        return self.start.value()-self.s.first,self.end.value()-self.s.first
    def select_public_marker(self,marker):
        if not self.s or not 0<=marker<len(self.s.markers):return
        self.pool.selected=marker;m=self.s.markers[marker];frame=self.frame.value()-self.s.first
        if not m['start']<=frame<=m['end']:self.frame.setValue(m['start']+self.s.first)
        source=self.s.marker_source(marker,self.frame.value()-self.s.first)
        if source is not None:
            self.sources.blockSignals(True);self.sources.setCurrentRow(source);self.sources.blockSignals(False)
            self.source_selected(source,marker)
        else:self.selected_source=-1;self.sync_marker_selection();self.draw()
    def sync_marker_selection(self):
        if not self.s or self.pool.selected is None:return
        marker=self.pool.selected
        if marker>=len(self.s.markers):self.pool.selected=None;return
        self.pool.sync_selection()
        self.pairing.select_marker(marker)
        frame=self.frame.value()-self.s.first;matrix=self.pairing.matrix
        matches=(matrix[:,frame]==marker).nonzero()[0] if matrix is not None else []
        name=self.s.slots[int(matches[0])] if len(matches) else None
        self.quick_label.setText(self.s.markers[marker]['label']+' · '+(display_name(name) if name else '未配对'))
        self.target.setCurrentIndex(max(0,self.target.findData(name)))
    def apply_marker_pairing(self,marker,slot):
        if not self.s:return
        if self.pairing.editing:self.pairing.stage_pair(marker,slot);return
        def run():
            start,end=self.calibration_range();self.s.exchange_marker(marker,slot,start,end)
            self.pool.selected=marker;self.curve_slot_override=None;self.refresh();self.select_public_marker(marker)
            self.statusBar().showMessage(f'已交换 {start+self.s.first}–{end+self.s.first} 帧的配对，可撤销。')
        self.guard(run)
    def confirm_quick_pairing(self):
        if self.pool.selected is None:self.statusBar().showMessage('请先选择标记点。');return
        self.apply_marker_pairing(self.pool.selected,self.target.currentData())
    def position_selected(self,item):
        self.cancel_repair(redraw=False)
        name=item.data(QtCore.Qt.ItemDataRole.UserRole)
        if self.pairing.mode.currentIndex()==0:self.pairing.table.selectRow(self.s.slots.index(name))
        frame=self.frame.value()-self.s.first;marker=int(self.pairing.matrix[self.s.slots.index(name),frame])
        source=self.s.marker_source(marker,frame) if marker>=0 else None
        if source is None:self.statusBar().showMessage('此位置尚未归类轨迹。');return
        self.select_public_marker(marker);self.selected_source=source;self.curve_slot_override=name
        self.sync_fill_position()
        self.selected_label.setText('① 已选 '+display_name(name));self.repair_context.setText(f'当前：{display_name(name)}，选区 {self.start.value()}–{self.end.value()} 帧。');self.draw()
    def place_selected(self):
        if not self.s:return
        def run():
            if self.selected_source<0:raise ValueError('先在三维图点击一个点')
            channel=self.s.place_interval(self.selected_source,self.target.currentData(),self.start.value()-self.s.first,self.end.value()-self.s.first)
            self.selected_source=channel;self.refresh();self.source_selected(channel)
            self.statusBar().showMessage(f'完成：帧 {self.start.value()}–{self.end.value()} 放入 {display_name(self.target.currentData())}（固定位置编号 {self.s.slots.index(self.target.currentData())+1:02d}）；原有数据已交换，可撤销。')
        self.guard(run)
    def history(self,redo):
        if self.pairing.editing:self.pairing.cancel();return
        if self.s:
            (self.s.redo if redo else self.s.undo)()
            if self.selected_source>=len(self.s.labels):self.selected_source=-1
            self.refresh()
            if self.batch_review or self.selected_slot() is not None:self.scan_gaps(self.batch_review)
            else:self.all_gap_rows=[];self.render_gap_rows()
    def preview_repair(self):
        if not self.s:return
        def run():
            name=self.selected_slot()
            if name is None:raise ValueError('先选择一个已归类的位置')
            self.timer.stop()
            item=self.s.repair_preview(name,self.start.value()-self.s.first,self.end.value()-self.s.first,self.repair_method.currentData(),self.repair_tension.value()/100)
            result=tuple(array.copy() for array in self.built);j=self.s.slots.index(name);lo,hi=item['start'],item['end']
            result[0][:,j,lo:hi+1]=np.asarray(item['values']);result[1][j,lo:hi+1]=3;result[2][j,lo:hi+1]=-1
            self.preview_item=item;self.commit_button.setEnabled(True);self.preview_result=result;self.curve_key=None;self.show_processed.setChecked(True)
            self.repair_context.setText(f"预览 {display_name(name)}：端点 {item['left']+self.s.first}、{item['right']+self.s.first} 帧；替换内部 {hi-lo+1} 帧，含有效点。偏离直线最大 {item.get('deviation',0):.3f}；{item.get('reference_note','')} 尚未应用。")
            self.draw()
        self.guard(run)
    def commit_repair(self):
        if self.preview_item is not None and 'kind' in self.preview_item:
            self.commit_process_plan();return
        if self.preview_item is None:self.statusBar().showMessage('请先生成并检查修复预览。');return
        if self.preview_item['slot'] in self.s.fill_excluded:
            self.statusBar().showMessage('此位置已排除补帧。');return
        self.s.apply_repair(self.preview_item);self.refresh();self.scan_gaps(self.batch_review)
        self.repair_context.setText('修复已应用，浅色实线为处理结果；支持撤销。')
    def remove_selected_repair(self):
        if not self.s:return
        def run():
            name=self.selected_slot()
            if name is None:raise ValueError('先选择已归类的位置')
            self.s.remove_repairs(name,self.start.value()-self.s.first,self.end.value()-self.s.first)
            self.refresh();self.scan_gaps(self.batch_review)
        self.guard(run)
    def cancel_repair(self,*_,redraw=True):
        had_preview=self.preview_item is not None
        self.preview_item=None
        if had_preview:self.curve_key=None
        if hasattr(self,'commit_button'):self.commit_button.setEnabled(False)
        if had_preview and hasattr(self,'repair_context'):self.repair_context.setText('预览已取消。调整区间或方法后重新预览。')
        if redraw and hasattr(self,'ax'):self.draw()
    def displayed_result(self):
        if not self.show_processed.isChecked():return self.measured_built
        return self.preview_result if self.preview_item is not None else self.built

    def smooth_options_changed(self,enabled):
        self.smooth_strength.setEnabled(enabled);self.smooth_window.setEnabled(enabled)
        if enabled and self.smooth_strength.value()==0:self.smooth_strength.setValue(100)
    def selected_slot(self):
        if self.curve_slot_override is not None and self.s and self.curve_slot_override in self.s.slots:return self.curve_slot_override
        if not self.s or self.selected_source<0:return None
        if self.pool.selected is not None and self.pairing.matrix is not None:
            matrix=self.pairing.base_matrix if self.pairing.editing else self.pairing.matrix
            matches=(matrix[:,self.frame.value()-self.s.first]==self.pool.selected).nonzero()[0]
            return self.s.slots[int(matches[0])] if len(matches) else None
        names=list(dict.fromkeys(a['slot'] for a in self.s.assignments if a['source']==self.selected_source))
        return names[0] if len(names)==1 else None
    def fill_parameters(self):
        if not self.s:raise ValueError('先打开文件')
        if self.fill_time.currentIndex()==0 and not self.selection_active:raise ValueError('当前没有选区，请先框选时间范围。')
        if self.fill_scope.currentIndex()==0:
            name=self.selected_slot()
            if not name:raise ValueError('当前点尚未归类或对应多个位置。请先在点位校准页归类，或选择已归类的位置。')
            names=[name]
        else:names=list(dict.fromkeys(a['slot'] for a in self.s.assignments))
        names=[name for name in names if name not in self.s.fill_excluded]
        if not names:raise ValueError('所选位置已排除补帧，或没有已校准位置；可在排除清单中调整')
        start,end=(self.start.value()-self.s.first,self.end.value()-self.s.first) if self.fill_time.currentIndex()==0 else (0,self.s.frames-1)
        if start>end:raise ValueError('起止帧范围无效')
        return names,start,end
    def toggle_fill_results(self,enabled):
        if not self.s:return
        self.s.checkpoint()
        if enabled and not self.s.fill_enabled and self.s.fill_jobs is None:self.s.fill_jobs=[]
        self.s.fill_enabled=enabled;self.refresh()
    def batch_fill(self):
        if not self.s:return
        self.cancel_repair(redraw=False);self.process_mode.setCurrentIndex(0)
        self.fill_scope.setCurrentIndex(1);self.fill_time.setCurrentIndex(1);self.batch_review=True
        self.review_toggle.setChecked(True)
        self.gap_filter.setCurrentIndex(1)
        if not self.apply_fill():return
        if hasattr(self,'all_gap_rows'):
            issues=sum(not r['status'].startswith('已补') or '边界' in r['status'] for r in self.all_gap_rows)
            self.statusBar().showMessage(f'批量补帧完成：全部已校准位置 / 全程；{issues} 个缺口待检查，双击列表可局部修改。可一次撤销。')
    def render_gap_rows(self,*_):
        if not hasattr(self,'all_gap_rows'):return
        if hasattr(self,'built'):
            for row in self.all_gap_rows:
                j=self.s.slots.index(row['slot'])
                if np.all(self.built[1][j,row['start']:row['end']+1]>=2):row['status']='已补（整段修复）' if np.any(self.built[1][j,row['start']:row['end']+1]==3) else row['status']
        rows=self.all_gap_rows
        if self.gap_filter.currentIndex()==1:rows=[r for r in rows if not r['status'].startswith('已补') or '边界' in r['status']]
        self.gap_rows=rows;self.gaps.setRowCount(len(rows))
        for row,data in enumerate(rows):
            values=[display_name(data['slot']),f"{data['start']+self.s.first}–{data['end']+self.s.first}",f"{data['seconds']:.3f}",data['status']]
            for col,value in enumerate(values):self.gaps.setItem(row,col,W.QTableWidgetItem(value))
    def apply_fill(self):
        if not self.s:return
        def run():
            names,start,end=self.fill_parameters()
            self.s.add_fill_job(names,start,end,self.fill_method.currentData(),self.gap.value(),self.smooth_strength.value()/100 if self.smooth_fill.isChecked() else 0.,self.smooth_window.value(),self.repair_tension.value()/100)
            self.refresh();self.scan_gaps(self.batch_review)
            total=int(np.count_nonzero(self.built[1]==2))
            self.statusBar().showMessage(f'补帧完成：当前 {total} 个插值采样，曲线用同色系浅色实线连接；实测坐标未修改。')
            return True
        return self.guard(run)
    def remove_fill(self):
        def run():
            names,start,end=self.fill_parameters();self.s.remove_fill_range(names,start,end);self.refresh();self.scan_gaps(self.batch_review)
        if self.s:self.guard(run)
    def scan_gaps(self,full=False):
        self.batch_review=full
        def run():
            names,start,end=(list(dict.fromkeys(a['slot'] for a in self.s.assignments)),0,self.s.frames-1) if full else self.fill_parameters()
            rows=self.s.gap_report(names,start,end,self.gap.value(),self.measured_built,self.built);self.all_gap_rows=rows
            self.render_gap_rows()
            done=sum(r['status'].startswith('已补') for r in rows);eligible=sum(r['status'].startswith('可补') for r in rows)
            warnings=sum('边界' in r['status'] for r in rows)
            self.fill_summary.setText(f"{'全程清单' if full else '范围内'} {len(rows)} 个检查项：已补 {done}，可补 {eligible}；{warnings} 处实测边界需复核。双击定位。")
        if self.s:self.guard(run)
    def goto_gap(self,row,col):
        if not hasattr(self,'gap_rows') or row>=len(self.gap_rows):return
        data=self.gap_rows[row];name=data['slot'];source=next((a['source'] for a in self.s.assignments if a['slot']==name),None)
        self.fill_scope.setCurrentIndex(0);self.fill_time.setCurrentIndex(0)
        if source is None:source=next((a['source'] for a in self.s.assignments if a['slot']==name),None)
        if source is not None:self.sources.setCurrentRow(source)
        self.curve_slot_override=name;self.tabs.setCurrentIndex(1);self.process_mode.setCurrentIndex(1 if '孤立' in data['status'] else 0)
        self.select_frames(data['start'],data['end']);self.frame.setValue(data['start']+self.s.first)
        padding=max(10,(data['end']-data['start']+1)*.5)
        self.set_time_view((data['start']-padding)/self.s.rate,(data['end']+padding)/self.s.rate)
    def template(self):
        if not self.s:return
        if self.pairing.editing:self.statusBar().showMessage('请先确认或取消本次配对模式，再切换建模方案。');return
        dialog=SchemeDialog(self)
        if dialog.exec()!=W.QDialog.DialogCode.Accepted:return
        def run():
            retained=self.s.apply_model_scheme(dialog.result_scheme);self.curve_slot_override=None;self.refresh()
            self.all_gap_rows=[];self.gap_rows=[];self.render_gap_rows()
            self.statusBar().showMessage(f'已应用方案：{self.s.model_scheme["name"]}；保留附加点 {len(retained)} 个，可撤销。')
        self.guard(run)
    def visibility_changed(self,item):
        index=self.sources.row(item)
        if item.checkState()==QtCore.Qt.CheckState.Unchecked:self.hidden_sources.add(index)
        else:self.hidden_sources.discard(index)
        self.draw()
    def show_all(self):self.hidden_sources.clear();self.refresh()
    def pick(self,event):
        if event.artist is getattr(self,'reconstructed_cloud',None) and len(event.ind):
            j=int(self.reconstructed_indices[event.ind[0]]);self.position_selected(self.records.item(j));return
        if event.artist is self.cloud and len(event.ind):
            source=int(self.raw_visible[event.ind[0]]);marker=self.s.public_marker_for(source,self.frame.value()-self.s.first)
            if marker is not None:self.select_public_marker(marker)
            else:self.source_selected(source)
    def toggle(self):
        if not self.s or self.press is not None:return
        if self.timer.isActive():self.timer.stop()
        else:self.timer.start(40)
        self.update_transport()
    def update_transport(self):
        if hasattr(self,'update_menu_state'):self.update_menu_state()
        self.play.setIcon(self.style().standardIcon(W.QStyle.StandardPixmap.SP_MediaPause if self.timer.isActive() else W.QStyle.StandardPixmap.SP_MediaPlay))
        if self.s:
            def stamp(seconds):return f'{int(seconds)//60:02d}:{seconds%60:06.3f}'
            self.timecode.setText(stamp((self.frame.value()-self.s.first)/self.s.rate)+' / '+stamp((self.s.frames-1)/self.s.rate))
    def tick(self):
        value=self.frame.value()+max(1,round(self.s.rate*.04))
        self.frame.setValue(self.s.first if value>self.frame.maximum() else value)
    def step(self,delta):
        if self.s:self.timer.stop();self.frame.setValue(self.frame.value()+delta)
        self.update_transport()
    def frame_changed(self,*_):
        if not self.s:return
        self.update_transport()
        marker=self.pool.selected
        if marker is not None and marker<len(self.s.markers):
            key=(self.view_revision,marker)
            if getattr(self,'_selected_owner_key',None)!=key:self._selected_owner_key=key;self._selected_owners=self.s.marker_sources(marker)
            source=int(self._selected_owners[self.frame.value()-self.s.first])
            if source>=0:
                self.selected_source=source;self.sources.blockSignals(True);self.sources.setCurrentRow(source);self.sources.blockSignals(False)
        self.pairing.sync_frame();self.pool.refresh();self.sync_marker_selection()
        t=(self.frame.value()-self.s.first)/self.s.rate
        if self.time_view and not self.time_view[0]<=t<=self.time_view[1]:
            width=self.time_view[1]-self.time_view[0];self.set_time_view(t-width*.2,t+width*.8,redraw=False)
        self.draw()
    def range_changed(self,*_):
        if self.s:
            if not self.selection_active:
                entered=next((w.value() for w in [self.start,self.end] if w.value()>=self.s.first),None)
                if entered is None:return
                for widget in [self.start,self.end]:
                    if widget.value()<self.s.first:widget.blockSignals(True);widget.setValue(entered);widget.blockSignals(False)
            if self.start.value()<self.s.first or self.end.value()<self.s.first:self.clear_selection();return
        self.selection_active=True;self.update_selection_actions()
        self.sync_fill_range()
        self.cancel_repair(redraw=False)
        if self.s:
            if hasattr(self,'repair_context'):self.repair_context.setText(f'{display_name(self.selected_slot()) if self.selected_slot() else "未选择位置"}，选区 {self.start.value()}–{self.end.value()} 帧；'+('只补缺失点。' if self.process_mode.currentIndex()==0 else '两端向外吸附，整段替换。'))
            self.range_hint.setText(f'选区 {self.start.value()}–{self.end.value()} 帧（含两端）；Shift＋单击可选连续段。');self.draw()
    def select_frames(self,start,end):
        self.selection_active=True
        self.start.blockSignals(True);self.end.blockSignals(True)
        self.start.setValue(start+self.s.first);self.end.setValue(end+self.s.first)
        self.start.blockSignals(False);self.end.blockSignals(False);self.range_changed()
    def update_selection_actions(self):
        if hasattr(self,'quick_confirm'):self.quick_confirm.setEnabled(self.s is not None and (self.selection_active or self.calibration_scope.currentIndex()==1))
    def clear_selection(self):
        if not self.s:return
        self.selection_active=False;self.press=None;self.dragging=False;self.drag_pointer=None;self.edge_timer.stop();self.edge_direction=0
        for widget in [self.start,self.end,self.fill_start,self.fill_end]:
            widget.blockSignals(True);widget.setValue(self.s.first-1);widget.blockSignals(False)
        self.cancel_repair(redraw=False);self.update_selection_actions()
        if hasattr(self,'selection_patch'):self.selection_patch.set_visible(False)
        self.range_hint.setText('未选择时间区间');self.draw();self.statusBar().showMessage('已清空选区；拖动或 Shift＋单击可重新选择。')
    def select_curve_span(self,a,b):
        if not self.s or not np.isfinite([a,b]).all():return
        lo,hi=sorted((a,b));start=max(0,int(np.ceil(lo*self.s.rate-1e-7)));end=min(self.s.frames-1,int(np.floor(hi*self.s.rate+1e-7)))
        if start<=end:self.select_frames(start,end)
    def select_continuous(self,time):
        if self.selected_source<0:return
        name=self.selected_slot()
        mask=self.measured_built[1][self.s.slots.index(name)]==1 if name is not None else self.s.valid[self.selected_source]
        index=int(np.clip(round(time*self.s.rate),0,self.s.frames-1))
        if not mask[index]:self.statusBar().showMessage('这里是缺失区间，请 Shift＋单击有数据的片段。');return
        lo=hi=index
        while lo>0 and mask[lo-1]:lo-=1
        while hi+1<len(mask) and mask[hi+1]:hi+=1
        self.select_frames(lo,hi)
    def curve_key_press(self,event):
        if event.key and 'shift' in str(event.key).lower():self.shift_down=True
    def curve_key_release(self,event):
        if event.key and 'shift' in str(event.key).lower():self.shift_down=False
    def shift_pressed(self,event):
        qt_shift=bool(W.QApplication.keyboardModifiers()&QtCore.Qt.KeyboardModifier.ShiftModifier)
        return qt_shift or self.shift_down or 'shift' in str(getattr(event,'key','')).lower() or 'shift' in getattr(event,'modifiers',())
    def select_current_segment(self):
        if self.s:
            if self.selected_source<0:self.statusBar().showMessage('请先在三维图或点列表选择一个点。')
            else:self.select_continuous((self.frame.value()-self.s.first)/self.s.rate)
    def select_full_trial(self):
        if self.s:
            self.select_frames(0,self.s.frames-1)
            self.full_time()
    def curve_press(self,event):
        self.press=None
        if getattr(event,'dblclick',False) and event.button==1:self.clear_selection();return
        if event.inaxes is self.curve and event.button==1 and event.xdata is not None:
            self.timer.stop();self.curve_canvas.setFocus()
            self.edge_timer.stop();self.drag_pointer=(event.x,event.y)
            self.press=(event.x,event.y,event.xdata,self.shift_pressed(event));self.dragging=False
    def event_time(self,event):
        time=event.xdata if event.inaxes is self.curve and event.xdata is not None else self.curve.transData.inverted().transform((event.x,event.y))[0]
        return float(np.clip(time,*self.time_view))
    def curve_motion(self,event):
        if not self.press or not self.s:return
        if (event.x-self.press[0])**2+(event.y-self.press[1])**2<=(6*self.curve_canvas.devicePixelRatioF())**2 and not self.dragging:return
        self.dragging=True;self.drag_pointer=(event.x,event.y);self.update_edge_scroll()
        time=self.event_time(event)
        lo,hi=sorted((self.press[2],time))
        start=max(0,int(np.ceil(lo*self.s.rate-1e-7)));end=min(self.s.frames-1,int(np.floor(hi*self.s.rate+1e-7)))
        if start<=end:
            self.selection_active=True;self.update_selection_actions()
            self.start.blockSignals(True);self.end.blockSignals(True)
            self.start.setValue(start+self.s.first);self.end.setValue(end+self.s.first)
            self.start.blockSignals(False);self.end.blockSignals(False)
            self.range_hint.setText(f'选区 {self.start.value()}–{self.end.value()} 帧；画面跟随拖动位置。')
        frame=self.s.first+int(np.clip(round(time*self.s.rate),0,self.s.frames-1))
        if self.frame.value()==frame:self.draw()
        else:self.frame.setValue(frame)
    def curve_release(self,event):
        press=self.press
        if not press:return
        if self.dragging:self.curve_motion(event)
        self.edge_timer.stop();self.edge_direction=0;self.drag_pointer=None
        dragged=self.dragging;self.press=None;self.dragging=False
        if dragged:self.range_changed();return
        if event.inaxes is self.curve and event.button==1:
            frame=self.s.first+int(np.clip(round(press[2]*self.s.rate),0,self.s.frames-1))
            self.frame.setValue(frame)
            if press[3]:
                if self.selected_source<0:self.statusBar().showMessage('请先在三维图或点列表选择一个点。')
                else:self.select_continuous(press[2])
            else:self.draw()
    def curve_resized(self,event=None):
        ratio=self.curve_canvas.devicePixelRatioF();width=max(self.curve_fig.bbox.width,1);height=max(self.curve_fig.bbox.height,1)
        self.curve_fig.subplots_adjust(left=min(.20,64*ratio/width),right=1-min(.10,16*ratio/width),bottom=min(.28,48*ratio/height),top=1-min(.22,40*ratio/height))
        self._curve_background=None;self.curve_canvas.draw_idle()
    def curve_drawn(self,event):
        if not hasattr(self,'selection_patch') or self.selection_patch.axes is not self.curve:return
        self._curve_background=self.curve_canvas.copy_from_bbox(self.curve.bbox)
        self._curve_background_view=(tuple(self.curve.get_xlim()),tuple(self.curve.bbox.bounds))
        self.curve.draw_artist(self.selection_patch);self.curve.draw_artist(self.playhead_line)
    def update_drag_overlay(self):
        self.sync_fill_range()
        if hasattr(self,'selection_patch'):
            self.selection_patch.set_visible(self.selection_active)
            if tuple(self.curve.get_xlim())!=tuple(self.time_view):self.curve.set_xlim(*self.time_view)
            left=(self.start.value()-self.s.first-.5)/self.s.rate;right=(self.end.value()-self.s.first+.5)/self.s.rate
            self.selection_patch.set_x(left);self.selection_patch.set_width(right-left)
            time=(self.frame.value()-self.s.first)/self.s.rate;self.playhead_line.set_xdata([time,time])
            key=(tuple(self.curve.get_xlim()),tuple(self.curve.bbox.bounds))
            if self._curve_background is not None and self._curve_background_view==key:
                self.curve_canvas.restore_region(self._curve_background)
                self.curve.draw_artist(self.selection_patch);self.curve.draw_artist(self.playhead_line)
                self.curve_canvas.blit(self.curve.bbox)
            else:self.curve_canvas.draw_idle()
    def duration(self):return max((self.s.frames-1)/self.s.rate,1/self.s.rate)
    def set_time_view(self,lo,hi,redraw=True):
        total=self.duration();width=min(total,max(5/self.s.rate,hi-lo));lo=min(max(0,lo),max(0,total-width));self.time_view=(lo,lo+width)
        self.time_scroll.blockSignals(True);self.time_scroll.setValue(round(10000*lo/(total-width)) if total>width else 0)
        self.time_scroll.setEnabled(total>width);self.time_scroll.blockSignals(False)
        self.curve.set_xlim(*self.time_view)
        if redraw:self.draw()
    def zoom_time(self,factor,anchor=None):
        if not self.s:return
        lo,hi=self.time_view;anchor=(self.frame.value()-self.s.first)/self.s.rate if anchor is None else anchor
        anchor=float(np.clip(anchor,lo,hi));ratio=(anchor-lo)/(hi-lo);width=(hi-lo)*factor
        self.set_time_view(anchor-ratio*width,anchor+(1-ratio)*width)
    def full_time(self):
        if self.s:self.set_time_view(0,self.duration())
    def pan_time(self,value):
        if self.s:
            width=self.time_view[1]-self.time_view[0];lo=(self.duration()-width)*value/10000;self.time_view=(lo,lo+width);self.draw()
    def curve_scroll(self,event):
        if not self.s or event.inaxes is not self.curve:return
        if self.shift_pressed(event):
            lo,hi=self.time_view;shift=(hi-lo)*.12*(1 if event.button=='down' else -1);self.set_time_view(lo+shift,hi+shift)
        else:self.zoom_time(1/1.3 if event.button=='up' else 1.3,event.xdata)
    def eventFilter(self,watched,event):
        if watched is getattr(self,'curve_canvas',None) and event.type()==QtCore.QEvent.Type.Wheel and self.s:
            pixel=event.pixelDelta();angle=event.angleDelta()
            horizontal=(abs(pixel.x())>abs(pixel.y()) if not pixel.isNull() else abs(angle.x())>abs(angle.y()))
            if horizontal:
                lo,hi=self.time_view
                shift=-(pixel.x()/max(self.curve_canvas.width(),1))*(hi-lo) if pixel.x() else -(angle.x()/120)*.12*(hi-lo)
                self.set_time_view(lo+shift,hi+shift);event.accept();return True
        return super().eventFilter(watched,event)
    def update_edge_scroll(self):
        if not self.dragging or not self.press or not self.drag_pointer:
            self.edge_timer.stop();return
        x,y=self.drag_pointer;box=self.curve.bbox;margin=28*self.curve_canvas.devicePixelRatioF()
        if x<box.x0+margin:
            self.edge_direction=-1;self.edge_strength=min(2.,max(.2,(box.x0+margin-x)/margin))
        elif x>box.x1-margin:
            self.edge_direction=1;self.edge_strength=min(2.,max(.2,(x-(box.x1-margin))/margin))
        else:
            self.edge_direction=0;self.edge_timer.stop();return
        if not self.edge_timer.isActive():self.edge_timer.start()
    def edge_scroll_tick(self):
        if not self.s or not self.press or not self.dragging or not self.drag_pointer:
            self.edge_timer.stop();return
        lo,hi=self.time_view;step=max(1/self.s.rate,(hi-lo)*.022*self.edge_strength)*self.edge_direction
        self.set_time_view(lo+step,hi+step,redraw=False)
        if abs(self.time_view[0]-lo)<1e-12:
            self.edge_timer.stop();return
        # Re-evaluate a stationary pointer in the newly scrolled time window.
        from types import SimpleNamespace
        self.curve_motion(SimpleNamespace(x=self.drag_pointer[0],y=self.drag_pointer[1],xdata=None,inaxes=None))

    def change_zoom(self,value):
        self.view_zoom=value/100;self.ax.set_box_aspect(self.ax._box_aspect,zoom=self.view_zoom);self.draw()
    def scroll_3d(self,event):self.zoom.setValue(self.zoom.value()+(5 if event.button=='up' else -5))
    def change_plane(self,*_):
        if self.s:
            self.plane_height.setEnabled(self.plane.currentIndex()!=2);self.plane_height.setValue(self.ceiling if self.plane.currentIndex()==1 else 0);self.draw()
    def ground_camera_moved(self,event):
        if event.inaxes is self.ax and event.button is not None:self.lock_ground_horizon()
    def ground_camera_released(self,event):
        if event.inaxes is self.ax:self.lock_ground_horizon()
    def lock_ground_horizon(self):
        if abs(float(self.ax.roll))>1e-9:self.ax.view_init(self.ax.elev,self.ax.azim,roll=0)
        self.draw()
    def configure_environment(self,*_):
        if not self.s:return
        points=self.s.points[:3,:, :][:,self.s.valid]
        side=self.ground_span.value()*self.meter_factor if self.meter_factor else 1000.
        self.environment_bounds=(np.full(2,-side/2),np.full(2,side/2))
        self.draw()
    def fit_environment(self):
        if not self.s:return
        lo,hi=self.environment_bounds;self.ax.set_xlim(lo[0],hi[0]);self.ax.set_ylim(lo[1],hi[1])
        measured=self.s.points[:3,:, :][:,self.s.valid]
        low=min(self.plane_height.value(),float(measured[2].min()) if measured.size else 0.)
        high=max(float(measured[2].max()) if measured.size else low+1,low+(self.meter_factor or 1000))
        self.ax.set_zlim(low,high);self.ax.set_box_aspect((hi[0]-lo[0],hi[1]-lo[1],high-low),zoom=self.view_zoom)
        self.ax.view_init(55,-60);self.ax.set_autoscale_on(False);self.draw()
    def draw_environment(self,xyz,status,frame):
        if self.plane.currentIndex()==2:return ''
        z=self.plane_height.value();geometry=ground_geometry(self.ax,z,self.environment_bounds,self.ground_step.value());self.ground_geometry=geometry
        self.ax.add_collection3d(Poly3DCollection([geometry['polygon']],facecolors='#f2f5f8',edgecolors='none',alpha=.5,zorder=-20))
        border=geometry['polygon']+[geometry['polygon'][0]]
        self.ax.add_collection3d(Line3DCollection([border],colors='#76899c',linewidths=1.4,zorder=-18))
        colors=['#b3bfca' if major else '#d1dae3' for major in geometry['major']]
        self.ax.add_collection3d(Line3DCollection(geometry['lines'],colors=colors,linewidths=[.7 if major else .4 for major in geometry['major']],zorder=-19))
        length=self.meter_factor or self.ground_step.value()*2
        axes=[[(0,0,z),(length,0,z)],[(0,0,z),(0,length,z)]]
        self.ax.add_collection3d(Line3DCollection(axes,colors=['#c84b43','#33845a'],linewidths=1.8,zorder=-18))
        label='1 m' if self.meter_factor else f'{length:g} {self.coordinate_unit}'
        self.ax.text(0,0,z,'O (0,0)',fontsize=8,color='#333333')
        self.ax.text(length,0,z,'X '+label,fontsize=8,color='#a83d36');self.ax.text(0,length,z,'Y '+label,fontsize=8,color='#236c45')
        names=['LASI','RASI','LPSI','RPSI'];centers=[xyz[:,self.s.slots.index(name),frame] for name in names if name in self.s.slots and status[self.s.slots.index(name),frame]>0]
        if len(centers)>=2:
            center=np.mean(centers,axis=0)
            if self.meter_factor:return f'骨盆参考 X={center[0]/self.meter_factor:.2f} m  Y={center[1]/self.meter_factor:.2f} m'
            return f'骨盆参考 X={center[0]:.1f} Y={center[1]:.1f} {self.coordinate_unit}'
        return ''
    def fit_visible(self):
        if not self.s:return
        f=self.frame.value()-self.s.first;mask=self.s.valid[:,f].copy()
        for i in self.hidden_sources:
            if i<len(mask):mask[i]=False
        for source in np.flatnonzero(mask):
            if self.s.public_marker_for(int(source),f) in self.hidden_markers:mask[source]=False
        p=self.s.points[:3,mask,f]
        if not p.size:return
        lo=p.min(axis=1);hi=p.max(axis=1);pad=np.maximum((hi-lo)*.08,30);lo-=pad;hi+=pad
        if self.plane.currentIndex()!=2:lo[2]=min(lo[2],self.plane_height.value());hi[2]=max(hi[2],self.plane_height.value())
        for d,fn in enumerate([self.ax.set_xlim,self.ax.set_ylim,self.ax.set_zlim]):fn(lo[d],hi[d])
        self.ax.set_box_aspect(hi-lo,zoom=self.view_zoom);self.ax.set_autoscale_on(False);self.draw()
    def reset_view(self):self.ax.view_init(20,-60);self.fit_visible()
    def selected_fill_runs(self):
        if not self.s or self.selected_source<0:return []
        name=self.selected_slot()
        if name is None:return []
        j=self.s.slots.index(name);xyz,status,origin=self.displayed_result();result=[]
        for start,end in self.s._runs(status[j]>=2):
            left,right=max(0,start-1),min(self.s.frames-1,end+1)
            result.append((left,right,xyz[:,j,left:right+1]))
        return result

    def draw(self,*_):
        if not self.s or not hasattr(self,'built'):return
        s=self.s;f=self.frame.value()-s.first
        if not 0<=f<s.frames:return
        for artist in list(self.ax.collections)+list(self.ax.lines)+list(self.ax.texts):artist.remove()
        mask=s.valid[:,f].copy()
        for i in self.hidden_sources:
            if i<len(mask):mask[i]=False
        for source in np.flatnonzero(mask):
            if s.public_marker_for(int(source),f) in self.hidden_markers:mask[source]=False
        size=self.point_size.value()
        colors=np.tile([.52,.57,.62],(len(s.labels),1));xyz,status,origin=self.displayed_result()
        visible_status=status.copy()
        for j,name in enumerate(s.slots):
            src=origin[j,f]
            if src>=0:colors[src]=slot_color(name)
            if src in self.hidden_sources or s.slot_channels.get(name) in self.hidden_sources or self.measured_built[2][j,f] in self.hidden_sources:visible_status[j,f]=0
            if self.pairing.matrix is not None and int(self.pairing.matrix[j,f]) in self.hidden_markers:visible_status[j,f]=0
        for j in np.flatnonzero(status[:,f]==3):
            source=self.measured_built[2][j,f]
            if source>=0:mask[source]=False
        self.raw_visible=np.flatnonzero(mask);p=s.points[:3,mask,f]
        self.cloud=self.ax.scatter(*p,c=colors[mask],s=size,picker=8)
        if self.show_numbers.isChecked():
            for i in self.raw_visible:self.ax.text(*s.points[:3,i,f],self.point_name(i),fontsize=9)
        if self.selected_source in self.raw_visible and (self.pool.selected is None or s.public_marker_for(self.selected_source,f)==self.pool.selected):self.ax.scatter(*s.points[:3,self.selected_source,f],facecolors='none',edgecolors='black',s=size*3)
        filled=np.flatnonzero(visible_status[:,f]>=2)
        self.reconstructed_indices=filled;self.reconstructed_cloud=None
        if len(filled):
            self.reconstructed_cloud=self.ax.scatter(*xyz[:,filled,f],facecolors='none',edgecolors='orange',s=size*2,picker=8)
            name=self.selected_slot()
            if name is not None and self.s.slots.index(name) in filled:self.ax.scatter(*xyz[:,self.s.slots.index(name),f],facecolors='none',edgecolors='black',s=size*3)
        if self.show_model.isChecked():
            lines,col=segments(s.slots,xyz,visible_status,f,body_slots=s.slots if s.model_scheme.get('connections') else s.model_scheme['body_slots'],connections=s.model_scheme.get('connections'))
            if lines:self.ax.add_collection3d(Line3DCollection(lines,colors=col,linewidths=1.5))
        position_note=self.draw_environment(xyz,visible_status,f)
        spacing=self.ground_geometry['spacing'] if self.plane.currentIndex()!=2 else None
        scale_note=(f'网格 {spacing/self.meter_factor:g} m' if self.meter_factor else f'网格 {spacing:g} {self.coordinate_unit}') if spacing is not None else ''
        self.ax.set_axis_off();self.ax.text2D(.02,.98,f"第 {self.frame.value()} 帧{' · 预览未应用' if self.preview_item is not None else ''}\n{position_note}\n{scale_note}",transform=self.ax.transAxes,va='top',fontsize=9)
        self.ax.set_autoscale_on(False);self.canvas.draw_idle()
        key=(self.view_revision,self.selected_source,self.selected_slot(),id(self.preview_item),self.show_processed.isChecked(),self.show_original.isChecked(),self.show_isolated.isChecked())
        if self.curve_key==key:
            self.update_drag_overlay();return
        self.curve_key=key
        self._curve_background=None
        self.curve.clear();t=np.arange(s.frames)/s.rate
        if 0<=self.selected_source<len(s.labels):
            name=self.selected_slot()
            if name is not None:
                j=s.slots.index(name);values=xyz[:,j].copy();values[:,status[j]!=1]=np.nan
            else:
                marker=self.pool.selected
                if marker is not None and marker<len(s.markers):
                    owners=s.marker_sources(marker);values=np.full((3,s.frames),np.nan)
                    for source in np.unique(owners[owners>=0]):
                        valid=(owners==source)&s.valid[source];values[:,valid]=s.points[:3,source,valid]
                else:
                    values=s.points[:3,self.selected_source].copy();values[:,~s.valid[self.selected_source]]=np.nan
            for dim,color in enumerate(['#d34a42','#2d9852','#326bca']):
                self.curve.plot(t,values[dim],color,label='XYZ'[dim],linewidth=1)
                good=np.isfinite(values[dim]);isolated=np.zeros(s.frames,dtype=bool)
                for lo,hi in s._runs(good):
                    if hi-lo<2:isolated[lo:hi+1]=True
                if self.show_isolated.isChecked() and isolated.any():self.curve.scatter(t[isolated],values[dim,isolated],c=color,s=16,zorder=4)
            if name is not None and self.show_original.isChecked() and np.any(status[j]==3):
                original=self.measured_built[0][:,j].copy();original[:,self.measured_built[1][j]!=1]=np.nan
                for dim in range(3):self.curve.plot(t,original[dim],color='gray',alpha=.45,linewidth=.8,marker='.' if self.show_isolated.isChecked() else None,markersize=3,label='修复前' if dim==0 else '_nolegend_')
            self.fill_lines=[];runs=self.selected_fill_runs()
            for dim,color in enumerate(['#ec827a','#6fbd8a','#7fa2de']):
                if not runs:continue
                xs=[];ys=[]
                for lo,hi,filled_xyz in runs:xs.extend(t[lo:hi+1]);xs.append(np.nan);ys.extend(filled_xyz[dim]);ys.append(np.nan)
                line,=self.curve.plot(xs,ys,color=color,linestyle='-',linewidth=1.4,label='浅色：补帧 / 修复' if dim==0 else '_nolegend_')
                self.fill_lines.append(line)
            title=display_name(name)+'（完整位置轨迹）' if name else self.point_name(self.selected_source)
            self.curve.legend(loc='upper right');self.curve.set_title(title,fontsize=10)
        else:self.curve.set_title('轨迹曲线',fontsize=10)
        if self.preview_item is not None:
            self.curve.axvspan((self.preview_item['start']-.5)/s.rate,(self.preview_item['end']+.5)/s.rate,color='#bcb1f0',alpha=.2)
        left=(self.start.value()-s.first)/s.rate;right=(self.end.value()-s.first)/s.rate
        self.selection_patch=self.curve.axvspan(left-.5/s.rate,right+.5/s.rate,color='#e9b24c',alpha=.22)
        self.selection_patch.set_visible(self.selection_active)
        self.playhead_line=self.curve.axvline((self.frame.value()-s.first)/s.rate,color='black',linewidth=1.2)
        self.selection_patch.set_animated(True);self.playhead_line.set_animated(True)
        self.curve.set_xlim(*self.time_view);self.curve.set_xlabel('时间 (s)')
        self.curve.set_ylabel(str((s.c3d['parameters']['POINT']['UNITS']['value'] or ['单位'])[0]))
        self.curve_canvas.draw_idle()

if __name__=='__main__':
    app=W.QApplication(sys.argv);window=Editor()
    if len(sys.argv)>1:window.guard(lambda:window.set_session(Session(sys.argv[1])))
    window.show();sys.exit(app.exec())
