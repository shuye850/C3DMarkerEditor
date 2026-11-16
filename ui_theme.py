"""Compact light theme for the motion capture workspace."""
from PySide6 import QtWidgets as W, QtGui, QtCore
from pathlib import Path
import sys

STYLE = '''
QMainWindow, QDialog { background: #eef2f7; }
QWidget { color: #263449; font-size: 13px; }
QToolTip { background: #263449; color: white; padding: 6px; border: none; }
QMenuBar, QToolBar { background: #ffffff; border: none; }
QMenuBar { border-bottom: 1px solid #dce3ed; }
QMenuBar::item { padding: 5px 12px; }
QMenuBar::item:selected, QMenu::item:selected { background: #e6efff; color: #245fcb; }
QMenu { background: white; border: 1px solid #dce3ed; padding: 5px; }
QMenu::item { padding: 7px 22px; }
QToolBar { spacing: 5px; padding: 6px 10px; border-bottom: 1px solid #dce3ed; }
QToolBar QToolButton { padding: 6px 9px; border-radius: 5px; }
QToolButton:hover { background: #e6efff; }
QTabWidget::pane { background: white; border: 1px solid #dce3ed; border-radius: 8px; }
QTabBar::tab { background: #e4eaf3; padding: 8px 22px; margin-right: 3px; border-top-left-radius: 6px; border-top-right-radius: 6px; color: #617087; }
QTabBar::tab:selected { background: #fff; color: #245fcb; font-weight: 600; }
QPushButton { background: #ffffff; border: 1px solid #d6deea; border-radius: 6px; padding: 5px 10px; min-height: 19px; }
QPushButton:hover { background: #f0f5ff; border-color: #8bacdf; }
QPushButton:pressed { background: #dce9ff; }
QPushButton:checked { background: #e4eeff; border-color: #b9cdef; color: #245fcb; }
QPushButton::menu-indicator { image: none; width: 0; }
QScrollArea#calibrationControls, QScrollArea#calibrationControls > QWidget > QWidget { background: white; }
QScrollArea#fillControls, QScrollArea#fillControls > QWidget > QWidget { background: white; }
QPushButton[role="primary"] { background: #2d68d8; border-color: #2d68d8; color: white; font-weight: 600; }
QPushButton[role="primary"]:hover { background: #2357b9; }
QPushButton:disabled { background: #f1f4f8; color: #9aa6b7; border-color: #e2e7ee; }
QComboBox, QSpinBox, QDoubleSpinBox { background: white; border: 1px solid #d6deea; border-radius: 5px; padding: 4px 6px; min-height: 18px; selection-background-color: #dce9ff; selection-color: #214d94; }
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: #5788df; }
QComboBox:disabled { color: #45576f; background: #f7f9fc; border-color: #e4e9f1; }
QComboBox { padding-right: 24px; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 24px; border: none; background: transparent; }
QComboBox::down-arrow { image: url("@ICONS@/down.svg"); width: 14px; height: 14px; }
QSpinBox, QDoubleSpinBox { padding-right: 22px; }
QSpinBox::up-button, QDoubleSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 22px; border: none; background: transparent; }
QSpinBox::down-button, QDoubleSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 22px; border: none; background: transparent; }
QSpinBox::up-button:hover, QSpinBox::down-button:hover, QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover { background: #e6efff; border-radius: 4px; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url("@ICONS@/up.svg"); width: 12px; height: 12px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url("@ICONS@/down.svg"); width: 12px; height: 12px; }
QComboBox QAbstractItemView { background: white; selection-background-color: #e6efff; selection-color: #245fcb; }
QListWidget, QTableWidget { background: white; alternate-background-color: #f6f8fc; border: 1px solid #e0e6ef; border-radius: 5px; outline: 0; gridline-color: #e7ecf3; selection-background-color: #e4eeff; selection-color: #204f9c; }
QListWidget::item { padding: 3px 5px; border-radius: 3px; }
QListWidget::item:hover { background: #f0f5ff; }
QListWidget::item:selected { background: #dfebff; color: #1f55a5; }
QGroupBox { border: 1px solid #dce3ed; border-radius: 6px; margin-top: 8px; padding-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 3px; color: #63738b; }
QHeaderView::section { background: #f0f4fa; color: #62738a; border: none; border-bottom: 1px solid #dce3ed; padding: 7px; font-weight: 600; }
QCheckBox { spacing: 6px; padding: 2px 0; }
QSplitter::handle { background: #e6ebf3; }
QSplitter::handle:hover { background: #b6cdf1; }
QSlider::groove:horizontal { height: 4px; background: #dce3ed; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #5b87dc; border-radius: 2px; }
QSlider::handle:horizontal { background: white; border: 2px solid #5b87dc; width: 12px; margin: -5px 0; border-radius: 7px; }
QScrollBar:horizontal { background: #e7edf5; height: 10px; border-radius: 5px; }
QScrollBar:vertical { background: #f0f3f8; width: 10px; border-radius: 5px; }
QScrollBar::handle { background: #b7c4d6; min-width: 24px; min-height: 24px; border-radius: 5px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QStatusBar { background: #e8eef6; color: #63738b; border-top: 1px solid #d9e2ee; }
QLabel[role="hint"] { color: #75839a; font-size: 12px; }
QLabel[role="context"] { background: #edf3ff; color: #315c99; border-radius: 6px; padding: 8px; }
'''

def apply_theme(editor):
    font=QtGui.QFont('Microsoft YaHei' if sys.platform=='win32' else 'PingFang SC');font.setPointSize(10);editor.setFont(font)
    for widget in [editor.range_hint,editor.mode_note,editor.fill_summary,editor.info]:widget.setProperty('role','hint')
    for widget in [editor.selected_label,editor.repair_context]:widget.setProperty('role','context')
    for widget in editor.findChildren(W.QPushButton):
        if widget.text() in ['确定：放入目标编号','预览当前范围','应用预览','播放 / 暂停']:widget.setProperty('role','primary')
    for listing in [editor.sources,editor.records,editor.gaps]:listing.setAlternatingRowColors(True)
    for combo in editor.findChildren(W.QComboBox):
        combo.setView(W.QListView(combo));combo.setMaxVisibleItems(15)
    for spin in editor.findChildren(W.QAbstractSpinBox):spin.setAccelerated(True)
    editor.gaps.verticalHeader().setDefaultSectionSize(32)
    editor.gaps.verticalHeader().hide()
    for splitter in [editor.main_split,editor.plot_split,editor.work_split]:splitter.setHandleWidth(6)
    icons={'打开 C3D':W.QStyle.StandardPixmap.SP_DialogOpenButton,'加载项目':W.QStyle.StandardPixmap.SP_DirOpenIcon,'保存':W.QStyle.StandardPixmap.SP_DialogSaveButton,'导出 C3D':W.QStyle.StandardPixmap.SP_ArrowUp,'撤销':W.QStyle.StandardPixmap.SP_ArrowBack,'重做':W.QStyle.StandardPixmap.SP_ArrowForward}
    for toolbar in editor.findChildren(W.QToolBar):
        toolbar.setIconSize(QtCore.QSize(16,16));toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        for action in toolbar.actions():
            if action.text() in icons:action.setIcon(editor.style().standardIcon(icons[action.text()]))
    editor.setStyleSheet(STYLE.replace('@ICONS@',(Path(__file__).parent/'icons').as_posix()))
