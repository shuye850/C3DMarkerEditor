"""UI preferences survive a normal close without depending on a project file."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('MPLCONFIGDIR','/private/tmp/c3d-mpl')
import sys,tempfile,unittest
import shutil,json
import numpy as np
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6 import QtWidgets as W,QtCore
from app import Editor

class LayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=W.QApplication.instance() or W.QApplication([])
    def test_empty_window_menu_states(self):
        window=Editor(persist_layout=False)
        try:
            self.assertTrue(window.commands['open'].isEnabled())
            self.assertTrue(window.commands['display'].isEnabled())
            for key in ['save','export','undo','redo','play','pair_begin']:self.assertFalse(window.commands[key].isEnabled())
        finally:window.close()
    def test_legacy_numpy_camera_does_not_prevent_startup(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'layout.ini'
            shutil.copyfile(Path(__file__).parent/'fixtures'/'legacy_layout.ini',path)
            window=Editor(layout_path=path)
            try:
                self.assertEqual(window.view_mode.currentIndex(),1)
                self.assertEqual(window.zoom.value(),63)
                self.assertNotIn('PyObjectWrapper',path.read_text())
                self.assertTrue(path.with_suffix('.ini.legacy-backup').exists())
                window.ax.view_init(np.float64(27.3),np.float64(-63.7),np.float64(35))
                window.save_layout()
                settings=QtCore.QSettings(str(path),QtCore.QSettings.Format.IniFormat)
                self.assertEqual(json.loads(settings.value('camera')),[27.3,-63.7,0.])
                self.assertNotIn('PyObjectWrapper',path.read_text())
            finally:window.close()
            reopened=Editor(layout_path=path)
            try:
                self.assertAlmostEqual(reopened.ax.elev,27.3)
                self.assertAlmostEqual(reopened.ax.roll,0)
            finally:reopened.close()

    def test_invalid_camera_uses_safe_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'layout.ini';window=Editor(layout_path=path);window.close()
            settings=QtCore.QSettings(str(path),QtCore.QSettings.Format.IniFormat)
            settings.setValue('camera','invalid');settings.sync()
            reopened=Editor(layout_path=path)
            try:self.assertIn('默认布局',reopened.statusBar().currentMessage())
            finally:reopened.close()
    def test_close_and_reopen_restores_layout_and_display_preferences(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'layout.ini'
            first=Editor(layout_path=path)
            first.showNormal();first.resize(780,811)
            first.tabs.setCurrentIndex(1);first.view_mode.setCurrentIndex(1)
            first.review_toggle.setChecked(True);first.advanced_toggle.setChecked(True)
            first.show_numbers.setChecked(True);first.show_isolated.setChecked(False)
            first.point_size.setValue(9);first.ground_span.setValue(12)
            self.app.processEvents()
            first.plot_split.setSizes([420,240]);self.app.processEvents()
            size=first.size();split=first.plot_split.sizes()
            first.close()
            self.assertTrue(path.exists())
            second=Editor(layout_path=path)
            try:
                second.show();self.app.processEvents();self.app.processEvents()
                # Qt clamps a saved window wider than the test screen (800 px).
                screen=self.app.primaryScreen().availableGeometry()
                if size.width()<=screen.width():self.assertEqual(second.width(),size.width())
                else:self.assertLessEqual(second.width(),size.width())
                if size.height()<=screen.height():self.assertEqual(second.height(),size.height())
                else:self.assertLessEqual(second.height(),size.height())
                self.assertEqual(second.tabs.currentIndex(),1)
                self.assertEqual(second.view_mode.currentIndex(),1)
                self.assertEqual(second.plot_split.orientation(),QtCore.Qt.Orientation.Vertical)
                restored=second.plot_split.sizes();total=sum(restored)
                expected_first=max(second.canvas.minimumHeight(),min(total-second.curve_canvas.minimumHeight(),split[0]/sum(split)*total))
                self.assertAlmostEqual(restored[0],expected_first,delta=2)
                self.assertTrue(second.review_toggle.isChecked());self.assertTrue(second.advanced_toggle.isChecked())
                self.assertTrue(second.show_numbers.isChecked());self.assertFalse(second.show_isolated.isChecked())
                self.assertEqual(second.point_size.value(),9);self.assertEqual(second.ground_span.value(),12)
                self.assertTrue(any(a.text()=='显示与环境设置…' for a in second.view_menu.actions()))
            finally:second.close()

    def test_cancelled_close_does_not_save_layout(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'layout.ini';window=Editor(layout_path=path)
            window.show();self.app.processEvents()
            window.confirm_switch=lambda:False
            self.assertFalse(window.close());self.assertFalse(path.exists())
            window.confirm_switch=lambda:True;window.close()

if __name__=='__main__':unittest.main()
