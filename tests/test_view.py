"""Regression checks for playback camera preservation and marker visualization."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('MPLCONFIGDIR','/private/tmp/c3d-mpl')
import sys,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import ezc3d
from PySide6.QtWidgets import QApplication
from matplotlib import rcParams
from app import Editor
from core import Session
from body_model import segments,slot_color

class ViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();path=Path(self.tmp.name)/'markers.c3d'
        c=ezc3d.c3d();c['parameters']['POINT']['RATE']['value']=[200.];c['parameters']['POINT']['UNITS']['value']=['mm']
        c['parameters']['POINT']['LABELS']['value']=['shoulder','elbow','wristA','wristB','other']
        points=np.zeros((4,5,30));points[:3]=np.array([[0,0,1500],[100,0,1200],[200,-20,1000],[200,20,1000],[300,0,500]]).T[:,:,None]
        points[0]+=np.arange(30)[None,:]*2
        c['data']['points']=points;c.write(str(path))
        self.w=Editor(persist_layout=False);self.w.write_recovery=lambda:None;self.w.set_session(Session(path))
        for name,src in [('LSHO',0),('LELB',1),('LWRA',2),('LWRB',3)]:self.w.s.assign(name,src,0,29)
        self.w.refresh()
    def tearDown(self):
        if self.w.pairing.editing:self.w.pairing.cancel()
        self.w.saved_state=self.w.s.snapshot();self.w.close();self.tmp.cleanup()
    def test_candidate_pool_filters_and_splits_original_public_id(self):
        from PySide6 import QtWidgets as W
        w=self.w;s=w.s
        self.assertEqual(w.pool.list.count(),len(s.base_labels))
        w.pool.colored.setChecked(False);self.assertEqual(w.pool.list.count(),1)
        w.pool.colored.setChecked(True);w.pool.selected=0;w.frame.setValue(s.first+15)
        with patch.object(W.QInputDialog,'getText',return_value=('R0_B',True)):w.pool.split()
        self.assertEqual(len(s.markers),len(s.base_labels)+1)
        self.assertEqual(w.pool.list.count(),len(s.markers))
        self.assertEqual(s.markers[0]['end'],14)
        w.pairing.mode.setCurrentIndex(1)
        self.assertEqual(w.pairing.table.rowCount(),len(s.markers))
        self.assertEqual(w.pairing.table.item(len(s.markers)-1,0).text(),'R0_B')
    def test_pairing_table_fixed_marker_confirm_unpair_and_roundtrip(self):
        w=self.w;s=w.s;p=w.pairing;p.mode.setCurrentIndex(1)
        p.confirm.click()
        before=s.points.copy();state=s.snapshot()
        p.table.selectRow(0);combo=p.table.cellWidget(0,1);combo.setCurrentIndex(combo.findData('LELB'))
        self.assertEqual(s.snapshot(),state)  # dropdown edits are staged
        p.confirm.click()
        np.testing.assert_array_equal(s.points,before)
        self.assertEqual(next(a['source'] for a in s.assignments if a['slot']=='LELB'),0)
        self.assertEqual(next(a['source'] for a in s.assignments if a['slot']=='LSHO'),1)
        path=Path(self.tmp.name)/'pairs.json';s.save_project(path)
        loaded=Session.load_project(path);self.assertEqual(loaded.snapshot(),s.snapshot())
        p.table.selectRow(0);p.remove.click()
        self.assertFalse(any(a['source']==0 for a in s.assignments))
        np.testing.assert_array_equal(s.points,before)
        w.history(False);self.assertTrue(any(a['source']==0 for a in s.assignments))

    def test_rebuilt_menus_share_actions_and_synchronize_view_state(self):
        from PySide6 import QtWidgets as W
        w=self.w;c=w.commands
        self.assertEqual(list(w.menus),['文件','编辑','标记','播放','视图'])
        toolbar=w.findChild(W.QToolBar,'workspaceToolbar')
        self.assertIn(c['save'],toolbar.actions());self.assertIn(c['display'],toolbar.actions())
        self.assertFalse(any(button.text()=='视图' for button in toolbar.findChildren(W.QToolButton)))
        self.assertTrue(c['save'].isEnabled())
        c['model'].trigger();self.assertEqual(w.show_model.isChecked(),c['model'].isChecked())
        w.show_model.setChecked(False);self.assertFalse(c['model'].isChecked())
        c['layout_1'].trigger();self.assertEqual(w.view_mode.currentIndex(),1)
        w.view_mode.setCurrentIndex(3);self.assertTrue(c['layout_3'].isChecked());self.assertFalse(c['layout_1'].isChecked())
        c['scope_1'].trigger();self.assertEqual(w.calibration_scope.currentIndex(),1)
        self.assertFalse(c['pair_cancel'].isEnabled());c['pair_begin'].trigger()
        self.assertTrue(w.pairing.editing);self.assertTrue(c['pair_cancel'].isEnabled());self.assertFalse(c['pair_begin'].isEnabled())
        c['pair_cancel'].trigger();self.assertFalse(w.pairing.editing)
        current=w.frame.value();c['next10'].trigger();self.assertEqual(w.frame.value(),current+10)

    def test_fill_fields_remain_visible_with_native_mac_form_growth_policy(self):
        from PySide6 import QtWidgets as W,QtTest,QtCore
        w=self.w;w.tabs.setCurrentIndex(1);w.resize(1200,850);w.show();self.app.processEvents()
        # Fill fields must not rely on the native macOS form-growth policy.
        forms=w.tabs.widget(1).findChildren(W.QFormLayout)
        self.assertEqual(forms,[])
        for form in forms:form.setFieldGrowthPolicy(W.QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        self.app.processEvents()
        for field in [w.fill_scope,w.fill_position,w.fill_time,w.fill_start,w.fill_end,w.process_mode,w.fill_method,w.gap]:
            self.assertTrue(field.isVisible());self.assertGreaterEqual(field.width(),52)
        for combo in [w.fill_scope,w.fill_time,w.process_mode,w.fill_method]:
            w.fill_scroll.ensureWidgetVisible(combo);self.app.processEvents()
            combo.showPopup();self.app.processEvents();self.assertTrue(combo.view().isVisible())
            QtTest.QTest.keyClick(combo.view(),QtCore.Qt.Key.Key_Down)
            QtTest.QTest.keyClick(combo.view(),QtCore.Qt.Key.Key_Return);self.app.processEvents()
            self.assertEqual(combo.currentIndex(),1)
        w.process_mode.setCurrentIndex(0);w.fill_time.setCurrentIndex(0)
        w.fill_start.setValue(w.s.first+3);self.assertEqual(w.start.value(),w.s.first+3)

    def test_generic_auxiliary_names_preserve_legacy_project_ids(self):
        from PySide6 import QtWidgets as W,QtCore
        from marker_names import display_name
        w=self.w;s=w.s;legacy='灯棒标记点4（WAND4）'
        s.update_slots(s.slots+['WAND1',legacy,'AUX7']);s.assign('WAND1',4,0,29);w.refresh()
        baseline=s.snapshot();text='\n'.join(display_name(n) for n in s.slots)
        self.assertNotIn('灯棒',text);self.assertNotIn('WAND',text)
        with patch('app.SchemeDialog') as dialog:
            dialog.return_value.exec.return_value=W.QDialog.DialogCode.Accepted
            dialog.return_value.result_scheme=s.model_scheme.copy();w.template()
        self.assertEqual(s.snapshot(),baseline)
        s.set_fill_excluded([])
        def inspect(dialog):
            labels=[button.text() for button in dialog.findChildren(W.QPushButton)]
            reset=next(button for button in dialog.findChildren(W.QPushButton) if button.text()=='恢复默认排除');reset.click()
            listing=dialog.findChild(W.QListWidget)
            for i in range(listing.count()):
                item=listing.item(i);labels.append(item.text())
                if item.data(QtCore.Qt.ItemDataRole.UserRole) in ['WAND1',legacy,'AUX7']:self.assertEqual(item.checkState(),QtCore.Qt.CheckState.Checked)
            self.assertFalse(any('灯棒' in label or 'WAND' in label for label in labels))
            return W.QDialog.DialogCode.Rejected
        with patch.object(W.QDialog,'exec',inspect):w.edit_fill_exclusions()
        self.assertEqual(s.fill_excluded,[])

    def test_scheme_dialog_presets_library_and_draft_cancel(self):
        from scheme_dialog import SchemeDialog
        from model_schemes import validate_scheme
        import json
        w=self.w;baseline=w.s.snapshot();library=Path(self.tmp.name)/'schemes'
        dialog=SchemeDialog(w,library)
        try:
            self.assertEqual(dialog.presets.count(),3)
            dialog.presets.setCurrentIndex(2)
            self.assertIn('LHEE',dialog.collect()['body_slots']);self.assertNotIn('LMMA',dialog.collect()['body_slots'])
            dialog.name.setText('Custom model');dialog.add_row('AUX8',False);dialog.connections.setPlainText('LFHD RFHD')
            dialog.save_preset();self.assertEqual(w.s.snapshot(),baseline)
            saved=next(library.glob('*.json'));value=validate_scheme(json.loads(saved.read_text(encoding='utf-8'))['scheme'])
            self.assertEqual(value['extra_slots'],['AUX8']);self.assertEqual(value['connections'],[['LFHD','RFHD']])
            dialog.apply();self.assertIsNotNone(dialog.result_scheme);self.assertEqual(w.s.snapshot(),baseline)
        finally:dialog.close()
        reopened=SchemeDialog(w,library)
        try:
            self.assertGreaterEqual(reopened.presets.findText('Custom model'),0)
            reopened.reject();self.assertEqual(w.s.snapshot(),baseline)
        finally:reopened.close()

    def test_double_click_clears_selection_without_selecting_a_frame(self):
        from PySide6 import QtTest,QtCore
        w=self.w;s=w.s;w.sources.setCurrentRow(0);w.show();self.app.processEvents();w.curve_canvas.draw()
        def position(time):
            x,y=w.curve.transData.transform((time,float(np.mean(w.curve.get_ylim()))));ratio=w.curve_canvas.devicePixelRatioF()
            return QtCore.QPoint(round(x/ratio),round(w.curve_canvas.height()-y/ratio))
        w.select_frames(5,10)
        QtTest.QTest.mouseDClick(w.curve_canvas,QtCore.Qt.MouseButton.LeftButton,QtCore.Qt.KeyboardModifier.NoModifier,position(.04))
        self.app.processEvents()
        self.assertFalse(w.selection_active);self.assertFalse(w.selection_patch.get_visible())
        self.assertEqual((w.start.value(),w.end.value()),(s.first-1,s.first-1));self.assertEqual(w.start.text(),'—')
        self.assertIsNone(w.press);self.assertFalse(w.edge_timer.isActive());self.assertFalse(w.quick_confirm.isEnabled())
        with self.assertRaises(ValueError):w.calibration_range()
        with self.assertRaises(ValueError):w.fill_parameters()
        QtTest.QTest.mouseClick(w.curve_canvas,QtCore.Qt.MouseButton.LeftButton,QtCore.Qt.KeyboardModifier.NoModifier,position(.07))
        self.assertFalse(w.selection_active)
        w.frame.setValue(s.first+3);self.assertFalse(w.selection_patch.get_visible())
        w.pairing.begin(s.slots.index('LSHO'));before=w.pairing.matrix.copy();w.select_public_marker(1)
        np.testing.assert_array_equal(w.pairing.matrix,before);w.pairing.cancel()
        QtTest.QTest.mouseClick(w.curve_canvas,QtCore.Qt.MouseButton.LeftButton,QtCore.Qt.KeyboardModifier.ShiftModifier,position(.03))
        self.assertTrue(w.selection_active);self.assertTrue(w.selection_patch.get_visible())
        QtTest.QTest.mouseDClick(w.slider,QtCore.Qt.MouseButton.LeftButton,QtCore.Qt.KeyboardModifier.NoModifier,w.slider.rect().center())
        self.assertFalse(w.selection_active);self.assertFalse(w.selection_patch.get_visible())
        w.calibration_scope.setCurrentIndex(1);self.assertEqual(w.calibration_range(),(0,s.frames-1))
        self.assertTrue(w.quick_confirm.isEnabled())
        w.start.setValue(s.first+5);self.assertTrue(w.selection_active);self.assertEqual(w.end.value(),s.first+5)
        w.clear_selection();w.select_all_time.click()
        self.assertTrue(w.selection_active);self.assertEqual(w.end.value(),s.first+s.frames-1)

    def test_native_pair_mode_stages_multiple_rows_and_commits_one_undo(self):
        from PySide6 import QtTest,QtCore
        w=self.w;s=w.s;p=w.pairing;w.resize(1200,900);w.show();self.app.processEvents()
        left=s.slots.index('LSHO');w.select_frames(5,10);w.frame.setValue(s.first+7)
        baseline=s.snapshot();history=len(s.history)
        p.table.scrollToItem(p.table.item(left,0));self.app.processEvents()
        point=p.table.visualItemRect(p.table.item(left,0)).center()
        QtTest.QTest.mouseClick(p.table.viewport(),QtCore.Qt.MouseButton.LeftButton,QtCore.Qt.KeyboardModifier.NoModifier,point)
        self.assertFalse(p.editing);self.assertEqual(w.pool.selected,0);self.assertEqual(s.snapshot(),baseline)
        QtTest.QTest.mouseDClick(p.table.viewport(),QtCore.Qt.MouseButton.LeftButton,QtCore.Qt.KeyboardModifier.NoModifier,point)
        self.assertTrue(p.editing);self.assertEqual(p.confirm.text(),'确定配对');self.assertEqual(p.anchor,left)
        w.pick(SimpleNamespace(artist=w.cloud,ind=[list(w.raw_visible).index(1)]))
        self.assertEqual(p.table.currentRow(),left);self.assertEqual(p.matrix[left,7],1)
        wrist=s.slots.index('LWRB');p.row_clicked(wrist,0);w.select_public_marker(4)
        self.assertEqual(p.matrix[wrist,7],4);self.assertEqual(s.snapshot(),baseline)
        p.confirm.click();self.assertFalse(p.editing);self.assertEqual(p.confirm.text(),'配对模式')
        self.assertEqual(len(s.history),history+1)
        self.assertEqual(s.pairing_matrix()[left,7],1);self.assertEqual(s.pairing_matrix()[wrist,7],4)
        self.assertEqual(s.pairing_matrix()[left,0],0)
        w.history(False);self.assertEqual(s.snapshot(),baseline)

    def test_pair_mode_cancel_discards_all_drafts_and_fixed_marker_picks_keys(self):
        w=self.w;s=w.s;p=w.pairing;baseline=s.snapshot();history=len(s.history)
        w.select_public_marker(4);p.confirm.click();self.assertTrue(p.editing)
        p.row_clicked(s.slots.index('LSHO'),0);self.assertEqual(w.pool.selected,4)
        w.select_public_marker(1);p.row_clicked(s.slots.index('LWRB'),0);w.select_public_marker(4)
        self.assertTrue(p.has_pending());self.assertEqual(s.snapshot(),baseline)
        with patch.object(w,'choose') as choose:self.assertFalse(w.save());choose.assert_not_called()
        p.remove.click();self.assertFalse(p.editing);self.assertEqual(s.snapshot(),baseline);self.assertEqual(len(s.history),history)
        p.mode.setCurrentIndex(1);p.confirm.click();p.row_clicked(0,0);w.select_public_marker(2)
        self.assertEqual(p.matrix[s.slots.index('LWRA'),7],0)
        p.row_clicked(1,0)
        # The already selected physical point must still be accepted for the next row.
        w.pick(SimpleNamespace(artist=w.cloud,ind=[list(w.raw_visible).index(2)]))
        self.assertEqual(p.matrix[s.slots.index('LSHO'),7],1)
        p.remove.click();self.assertEqual(s.snapshot(),baseline)

    def test_pairing_table_preview_select_and_fixed_name_after_renaming(self):
        w=self.w;s=w.s;p=w.pairing
        # Begin with the existing stable-channel workflow, then rename its IDs.
        s.place_interval(0,'LSHO',0,29);w.refresh()
        source=s.slot_channels['LSHO'];s.pair_fixed_marker(source,'LELB');w.refresh()
        old=s.build(fill=False,repair=False)[0].copy();public_source=s.marker_source(2,0);raw=s.points[:3,public_source].copy()
        row=s.slots.index('LSHO');p.table.selectRow(row);p.row_clicked(row,0)
        w.sources.setCurrentRow(public_source)
        self.assertEqual(p.table.currentRow(),s.slots.index('LWRA'))
        w.select_frames(5,10);p.begin(row)
        combo=p.table.cellWidget(row,1);combo.setCurrentIndex(combo.findData(2));p.confirm.click()
        result=s.build(fill=False,repair=False)[0]
        np.testing.assert_array_equal(result[:,row,5:11],raw[:,5:11])
        other=s.slots.index('LELB')
        np.testing.assert_array_equal(result[:,other],old[:,other])
        p.mode.setCurrentIndex(1);w.sources.setCurrentRow(s.marker_source(2,0))
        self.assertEqual(p.table.currentRow(),2)

    def test_quick_pairing_scope_and_synchronized_preview_visibility(self):
        w=self.w;s=w.s;p=w.pairing;points=s.points.copy()
        w.select_frames(5,10);w.frame.setValue(s.first+7)
        # A native Matplotlib pick follows the same route as clicking the preview.
        w.pick(SimpleNamespace(artist=w.cloud,ind=[list(w.raw_visible).index(1)]))
        self.assertEqual(w.pool.list.currentItem().data(__import__('PySide6').QtCore.Qt.ItemDataRole.UserRole),1)
        self.assertEqual(p.table.currentRow(),s.slots.index('LELB'))
        self.assertEqual(w.target.currentData(),'LELB')
        w.target.setCurrentIndex(w.target.findData('LSHO'));w.quick_confirm.click()
        matrix=s.pairing_matrix();left=s.slots.index('LSHO');right=s.slots.index('LELB')
        self.assertEqual((matrix[left,7],matrix[right,7]),(1,0))
        self.assertEqual((matrix[left,0],matrix[right,0]),(0,1))
        np.testing.assert_array_equal(points,s.points)
        self.assertEqual(p.table.currentRow(),left)
        w.pool.double_click(w.pool.list.currentItem());self.assertIn(1,w.hidden_markers);self.assertNotIn(1,w.raw_visible)
        w.frame.setValue(s.first+20);self.assertEqual(p.table.currentRow(),right)
        self.assertEqual(p.table.cellWidget(left,1).currentData(),0)
        w.pool.double_click(w.pool.list.currentItem());self.assertNotIn(1,w.hidden_markers);self.assertIn(1,w.raw_visible)
        p.mode.setCurrentIndex(1);self.assertEqual(p.table.currentRow(),1)
        w.calibration_scope.setCurrentIndex(1);w.target.setCurrentIndex(w.target.findData('LSHO'));w.quick_confirm.click()
        self.assertTrue(np.all(s.pairing_matrix()[left]==1))

    def test_table_modes_use_same_scope_and_empty_marker_has_no_false_selection(self):
        w=self.w;s=w.s;p=w.pairing;row=s.slots.index('LSHO')
        w.select_frames(5,10);p.mode.setCurrentIndex(1)
        p.confirm.click()
        combo=p.table.cellWidget(1,1);combo.setCurrentIndex(combo.findData('LSHO'));p.confirm.click()
        self.assertEqual(s.pairing_matrix()[row,7],1);self.assertEqual(s.pairing_matrix()[row,0],0)
        p.mode.setCurrentIndex(0);w.calibration_scope.setCurrentIndex(1)
        p.confirm.click()
        combo=p.table.cellWidget(row,1);combo.setCurrentIndex(combo.findData(1));p.confirm.click()
        self.assertTrue(np.all(s.pairing_matrix()[row]==1))
        w.select_public_marker(4);self.assertEqual(p.table.currentRow(),-1)
        w.calibration_scope.setCurrentIndex(0);p.table.selectRow(row);p.remove.click()
        self.assertTrue(np.all(s.pairing_matrix()[row,5:11]==-1))
        self.assertEqual(s.pairing_matrix()[row,0],1)

    def test_native_pool_double_click_and_layout_keeps_table_visible(self):
        from PySide6 import QtTest,QtCore
        w=self.w;w.resize(1200,850);w.show();self.app.processEvents();self.app.processEvents()
        def item_for(marker):
            return next(w.pool.list.item(i) for i in range(w.pool.list.count()) if w.pool.list.item(i).data(QtCore.Qt.ItemDataRole.UserRole)==marker)
        for marker in [0,4]:
            item=item_for(marker);w.pool.list.scrollToItem(item);self.app.processEvents()
            point=w.pool.list.visualItemRect(item).center()
            QtTest.QTest.mouseClick(w.pool.list.viewport(),QtCore.Qt.MouseButton.LeftButton,QtCore.Qt.KeyboardModifier.NoModifier,point)
            QtTest.QTest.mouseDClick(w.pool.list.viewport(),QtCore.Qt.MouseButton.LeftButton,QtCore.Qt.KeyboardModifier.NoModifier,point)
            self.app.processEvents();self.assertIn(marker,w.hidden_markers)
            center=item_for(marker).icon().pixmap(24,24).toImage().pixelColor(12,12)
            if marker==4:self.assertLess(max(center.red(),center.green(),center.blue()),60)
            else:self.assertGreater(min(center.red(),center.green(),center.blue()),200)
            self.assertNotIn(marker,w.raw_visible)
            w.pool.double_click(item_for(marker));self.assertNotIn(marker,w.hidden_markers)
        self.assertGreaterEqual(w.pairing.table.height(),190)
        expanded=w.pairing.table.height()
        w.pool.fold.setChecked(False);self.app.processEvents();self.app.processEvents()
        self.assertGreater(w.pairing.table.height(),expanded)
        w.pool.fold.setChecked(True);self.app.processEvents();self.app.processEvents()
        self.assertGreaterEqual(w.pairing.table.height(),190)
    def test_player_skip_shortcuts_buttons_and_accelerated_frame_control(self):
        from PySide6 import QtTest,QtCore
        w=self.w;w.show();w.activateWindow();self.app.processEvents()
        w.frame.setValue(w.s.first+12)
        QtTest.QTest.keyClick(w,QtCore.Qt.Key.Key_Right,QtCore.Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(w.frame.value(),w.s.first+22)
        QtTest.QTest.keyClick(w,QtCore.Qt.Key.Key_Left,QtCore.Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(w.frame.value(),w.s.first+12)
        w.back10.click();self.assertEqual(w.frame.value(),w.s.first+2)
        w.back10.click();self.assertEqual(w.frame.value(),w.s.first)
        w.forward10.click();self.assertEqual(w.frame.value(),w.s.first+10)
        self.assertTrue(w.frame.isAccelerated());self.assertEqual(w.play.text(),'')
        w.toggle();self.assertTrue(w.timer.isActive())
        w.back10.click();self.assertFalse(w.timer.isActive())
        self.assertIn('/',w.timecode.text());self.assertEqual(w.slider.rate,w.s.rate)
    def test_single_point_placement_swaps_and_keeps_other_frames(self):
        w=self.w;s=w.s;old=s.points.copy()
        w.sources.setCurrentRow(0);w.target.setCurrentIndex(w.target.findData('LELB'))
        w.select_frames(5,20);w.place_selected()
        channel=s.slot_channels['LELB'];other=s.slot_channels['LSHO']
        np.testing.assert_array_equal(s.points[:3,channel,5:21],old[:3,0,5:21])
        np.testing.assert_array_equal(s.points[:3,other,5:21],old[:3,1,5:21])
        np.testing.assert_array_equal(s.points[:3,other,:5],old[:3,0,:5])
        self.assertEqual(w.selected_source,channel)
        path=Path(self.tmp.name)/'placed.json';s.save_project(path);r=Session.load_project(path)
        self.assertEqual(r.snapshot(),s.snapshot());np.testing.assert_array_equal(r.points,s.points)
        out=Path(self.tmp.name)/'placed.c3d';s.export(out);read=ezc3d.c3d(str(out))
        j=s.slots.index('LELB');np.testing.assert_allclose(read['data']['points'][:3,j,5:21],old[:3,0,5:21])

    def test_native_qt_shift_click_and_live_drag_preview(self):
        from PySide6 import QtTest,QtCore
        w=self.w;w.s.valid[0,10:15]=False;w.refresh();w.sources.setCurrentRow(0)
        w.show();w.activateWindow();self.app.processEvents();w.curve_canvas.draw()
        canvas=w.curve_canvas
        def position(time):
            x,y=w.curve.transData.transform((time,float(np.mean(w.curve.get_ylim()))))
            ratio=canvas.devicePixelRatioF()
            return QtCore.QPoint(round(x/ratio),round(canvas.height()-y/ratio))
        w.select_frames(0,9);canvas.draw()
        QtTest.QTest.keyPress(canvas,QtCore.Qt.Key.Key_Shift)
        QtTest.QTest.mouseClick(canvas,QtCore.Qt.MouseButton.LeftButton,QtCore.Qt.KeyboardModifier.ShiftModifier,position(.1))
        QtTest.QTest.keyRelease(canvas,QtCore.Qt.Key.Key_Shift)
        self.app.processEvents()
        self.assertEqual((w.start.value(),w.end.value()),(w.s.first+15,w.s.first+29))
        canvas.draw()
        QtTest.QTest.mousePress(canvas,QtCore.Qt.MouseButton.LeftButton,QtCore.Qt.KeyboardModifier.NoModifier,position(.02))
        QtTest.QTest.mouseMove(canvas,position(.09),10);self.app.processEvents()
        # Crucially verify before release: timeline and 3D already follow the pointer.
        self.assertTrue(w.dragging)
        self.assertLessEqual(abs(w.frame.value()-(w.s.first+18)),1)
        f=w.frame.value()-w.s.first;src=list(w.raw_visible).index(0)
        np.testing.assert_allclose([axis[src] for axis in w.cloud._offsets3d],w.s.points[:3,0,f])
        self.assertLessEqual(abs(w.end.value()-(w.s.first+18)),1)
        QtTest.QTest.mouseRelease(canvas,QtCore.Qt.MouseButton.LeftButton,QtCore.Qt.KeyboardModifier.NoModifier,position(.09))
        self.app.processEvents();self.assertFalse(w.dragging)

    def test_space_horizontal_wheel_and_stationary_edge_scroll(self):
        from PySide6 import QtCore,QtGui,QtTest
        from matplotlib.backend_bases import MouseEvent
        w=self.w;w.show();w.activateWindow();w.curve_canvas.setFocus();self.app.processEvents();w.curve_canvas.draw()
        QtTest.QTest.keyClick(w.curve_canvas,QtCore.Qt.Key.Key_Space);self.assertTrue(w.timer.isActive())
        QtTest.QTest.keyClick(w.curve_canvas,QtCore.Qt.Key.Key_Space);self.assertFalse(w.timer.isActive())
        w.set_time_view(.03,.09);width=w.time_view[1]-w.time_view[0]
        point=QtCore.QPointF(w.curve_canvas.width()/2,w.curve_canvas.height()/2)
        # Native angle-based horizontal wheel, then pixel-based trackpad gesture.
        event=QtGui.QWheelEvent(point,point,QtCore.QPoint(),QtCore.QPoint(-120,0),QtCore.Qt.MouseButton.NoButton,QtCore.Qt.KeyboardModifier.NoModifier,QtCore.Qt.ScrollPhase.ScrollUpdate,False)
        before=w.time_view[0];self.app.sendEvent(w.curve_canvas,event);self.assertGreater(w.time_view[0],before)
        event=QtGui.QWheelEvent(point,point,QtCore.QPoint(30,0),QtCore.QPoint(),QtCore.Qt.MouseButton.NoButton,QtCore.Qt.KeyboardModifier.NoModifier,QtCore.Qt.ScrollPhase.ScrollUpdate,False)
        before=w.time_view[0];self.app.sendEvent(w.curve_canvas,event);self.assertLess(w.time_view[0],before)
        self.assertAlmostEqual(w.time_view[1]-w.time_view[0],width)
        w.set_time_view(.02,.08);w.curve_canvas.draw();y=np.mean(w.curve.get_ylim())
        x,py=w.curve.transData.transform((.04,y));w.curve_press(MouseEvent('button_press_event',w.curve_canvas,x,py,button=1))
        x,py=w.curve.bbox.x1-1,w.curve.transData.transform((.04,y))[1]
        motion=MouseEvent('motion_notify_event',w.curve_canvas,x,py,button=1);w.curve_motion(motion)
        before=w.time_view[0];before_frame=w.frame.value();before_end=w.end.value();self.assertTrue(w.edge_timer.isActive())
        for _ in range(5):w.edge_scroll_tick()
        self.assertGreater(w.time_view[0],before);self.assertGreater(w.frame.value(),before_frame);self.assertGreater(w.end.value(),before_end)
        self.assertAlmostEqual(w.time_view[1]-w.time_view[0],width)
        w.curve_release(MouseEvent('button_release_event',w.curve_canvas,x,py,button=1));self.assertFalse(w.edge_timer.isActive())
        # At the file boundary scrolling stops and cannot extend beyond the final frame.
        w.set_time_view(w.duration()-.06,w.duration());w.curve_canvas.draw()
        x,py=w.curve.transData.transform((w.duration()-.04,y));w.curve_press(MouseEvent('button_press_event',w.curve_canvas,x,py,button=1))
        x=w.curve.bbox.x1+5;w.curve_motion(MouseEvent('motion_notify_event',w.curve_canvas,x,py,button=1));w.edge_scroll_tick()
        self.assertFalse(w.edge_timer.isActive());self.assertLessEqual(w.end.value(),w.s.first+w.s.frames-1)
        w.press=None;w.dragging=False

    def test_world_ground_is_fixed_across_frames_and_has_origin(self):
        w=self.w;w.show();self.app.processEvents();w.canvas.draw();w.draw()
        old=[np.asarray(line) for line in w.ground_geometry['lines']]
        bounds=w.environment_bounds;spacing=w.ground_geometry['spacing']
        w.frame.setValue(w.s.first+10)
        for a,b in zip(old,w.ground_geometry['lines']):np.testing.assert_array_equal(a,b)
        self.assertTrue(any('O (0,0)' in text.get_text() for text in w.ax.texts))
        for line in w.ground_geometry['lines']:self.assertTrue(np.all(np.asarray(line)[:,2]==w.plane_height.value()))
        self.assertGreaterEqual(spacing,w.ground_step.value())
        w.fit_environment();self.assertLessEqual(w.ax.get_xlim()[0],bounds[0][0]);self.assertGreaterEqual(w.ax.get_xlim()[1],bounds[1][0])
        self.assertFalse(w.ax.computed_zorder)

    def test_isolated_point_toggle_is_display_only(self):
        w=self.w;s=w.s;s.valid[0,:20]=False;s.valid[0,[4,10,11]]=True
        w.refresh();w.sources.setCurrentRow(0);before=s.snapshot()
        self.assertEqual(len(w.curve.collections),3)
        w.show_isolated.setChecked(False);self.assertEqual(len(w.curve.collections),0)
        self.assertEqual(s.snapshot(),before)
        w.show_isolated.setChecked(True);self.assertEqual(len(w.curve.collections),3)

    def test_unified_bezier_current_point_scope_and_whole_replacement(self):
        w=self.w;s=w.s;s.valid[0,10:15]=False;s.points[:3,0,10:15]=np.nan
        w.refresh();w.sources.setCurrentRow(0);w.select_frames(10,14)
        w.fill_method.setCurrentIndex(w.fill_method.findData('bezier'));w.preview_process()
        self.assertEqual(w.preview_item['kind'],'gaps');self.assertFalse(s.fill_enabled)
        w.commit_repair();self.assertEqual(s.fill_jobs[-1]['method'],'bezier')
        self.assertTrue(np.all(w.built[1][s.slots.index('LSHO'),10:15]==2))
        self.assertTrue(np.all(w.built[1][s.slots.index('LELB')]==1))
        saved=Path(self.tmp.name)/'bezier_job.json';s.save_project(saved);r=Session.load_project(saved)
        self.assertEqual(r.fill_jobs[-1]['method'],'bezier');self.assertEqual(r.fill_tension,s.fill_tension)
        w.process_mode.setCurrentIndex(1);w.fill_method.setCurrentIndex(w.fill_method.findData('linear'))
        w.select_frames(16,20);w.preview_process();self.assertEqual(w.preview_item['kind'],'replace')
        before=s.snapshot();w.commit_repair();self.assertEqual(len(s.repairs),1)
        self.assertTrue(np.all(w.built[1][s.slots.index('LSHO'),16:21]==3))
        s.undo();self.assertEqual(s.snapshot(),before)

    def test_rectangular_viewport_keeps_physical_scale_and_contextual_review(self):
        from mpl_toolkits.mplot3d import proj3d
        w=self.w;w.show();self.app.processEvents();w.canvas.draw()
        full=w.ax.get_position(original=True);active=w.ax.get_position()
        np.testing.assert_allclose(full.bounds,active.bounds)
        w.ax.set_xlim(-1,1);w.ax.set_ylim(-1,1);w.ax.set_zlim(-1,1);w.ax.set_box_aspect((1,1,1));w.ax.view_init(0,-90)
        def project(x,y,z):
            a,b,_=proj3d.proj_transform(x,y,z,w.ax.get_proj());return w.ax.transData.transform((a,b))
        center=project(0,0,0)
        np.testing.assert_allclose(np.linalg.norm(project(1,0,0)-center),np.linalg.norm(project(0,0,1)-center),rtol=.01)
        w.tabs.setCurrentIndex(1);w.review_toggle.setChecked(True);self.assertTrue(w.review.isVisible())
        w.tabs.setCurrentIndex(0);self.assertFalse(w.review.isVisible())
        w.view_mode.setCurrentIndex(3);self.assertFalse(w.canvas.isVisible());self.assertTrue(w.curve_canvas.isVisible())

    def test_repair_preview_apply_and_curve_reuse(self):
        w=self.w;s=w.s;w.sources.setCurrentRow(0);w.select_frames(10,15)
        old=s.snapshot();w.preview_repair();self.assertIsNotNone(w.preview_item)
        self.assertEqual(s.snapshot(),old);self.assertEqual(len(w.fill_lines),3)
        w.commit_repair();self.assertEqual(len(s.repairs),1)
        line=w.curve.lines[0];head=w.playhead_line
        w.frame.setValue(s.first+12)
        self.assertIs(w.curve.lines[0],line);self.assertIs(w.playhead_line,head)
        # Gap scans must use already computed arrays, not rerun interpolation.
        with patch.object(s,'build',side_effect=AssertionError('scan recomputed data')):
            w.scan_gaps(True)
        w.remove_selected_repair();self.assertEqual(len(s.repairs),0)

    def test_one_click_batch_fill_and_local_revision(self):
        w=self.w
        path=w.s.path;c=ezc3d.c3d(str(path));c['data']['meta_points']['residuals'][0,:2,10:15]=-1;c.write(str(path))
        s=Session(path)
        for name,src in [('LSHO',0),('LELB',1),('LWRA',2),('LWRB',3)]:s.assign(name,src,0,29)
        w.set_session(s)
        before=s.snapshot();w.refresh();w.selected_source=-1
        w.batch_fill()
        self.assertEqual(s.fill_jobs[-1]['slots'],['LSHO','LELB','LWRA','LWRB'])
        self.assertEqual((s.fill_jobs[-1]['start'],s.fill_jobs[-1]['end']),(0,29))
        for name in ['LSHO','LELB']:self.assertTrue(np.all(w.built[1][s.slots.index(name),10:15]==2))
        self.assertEqual(w.gaps.rowCount(),0)
        w.gap_filter.setCurrentIndex(0);self.assertEqual(len(w.gap_rows),2)
        w.gap_filter.setCurrentIndex(1);self.assertEqual(w.gaps.rowCount(),0)
        w.gap_filter.setCurrentIndex(0);w.goto_gap(0,0)
        self.assertEqual((w.fill_scope.currentIndex(),w.fill_time.currentIndex()),(0,0))
        selected=w.selected_slot();other='LELB' if selected=='LSHO' else 'LSHO'
        w.remove_fill()
        self.assertTrue(np.all(w.built[1][s.slots.index(selected),10:15]==0))
        self.assertTrue(np.all(w.built[1][s.slots.index(other),10:15]==2))
        s.undo();self.assertTrue(np.all(s.build()[1][s.slots.index(selected),10:15]==2))
        s.undo();self.assertEqual(s.snapshot(),before)

    def test_position_list_resolves_legacy_ambiguous_source_for_fill(self):
        w=self.w;s=w.s;s.assignments=[]
        s.assign('LSHO',0,0,9);s.assign('LSHO',1,15,29);s.assign('LELB',0,15,29)
        w.selected_source=0;w.refresh();self.assertIsNone(w.selected_slot())
        w.position_selected(w.records.item(s.slots.index('LSHO')))
        self.assertEqual(w.selected_slot(),'LSHO')
        w.select_frames(10,14);w.apply_fill();self.assertEqual(len(w.fill_lines),3)

    def test_legacy_split_sources_show_dashed_bridge_and_full_measured_curve(self):
        w=self.w;s=w.s;s.assignments=[]
        s.assign('LSHO',0,0,9);s.assign('LSHO',1,15,29)
        w.selected_source=0;w.refresh();w.select_frames(10,14)
        w.fill_method.setCurrentIndex(w.fill_method.findData('linear'));w.gap.setValue(.1)
        w.apply_fill()
        self.assertEqual(len(w.fill_lines),3)
        for line in w.fill_lines:
            self.assertEqual(line.get_linestyle(),'-')
            np.testing.assert_allclose(np.asarray(line.get_xdata())[np.isfinite(line.get_xdata())],np.arange(9,16)/s.rate)
        measured_x=w.curve.lines[0].get_ydata()
        self.assertTrue(np.isnan(measured_x[10:15]).all())
        self.assertEqual(measured_x[20],s.points[0,1,20])
        self.assertEqual(w.gaps.rowCount(),1);self.assertEqual(w.gaps.item(0,3).text(),'已补（插值）')
        w.select_continuous(20/s.rate);self.assertEqual((w.start.value(),w.end.value()),(s.first+15,s.first+29))
        w.goto_gap(0,0);self.assertEqual((w.start.value(),w.end.value()),(s.first+10,s.first+14))
        w.remove_fill();self.assertEqual(w.fill_lines,[])

    def test_fill_connects_gap_with_dashed_lines_only(self):
        w=self.w;s=w.s;channel=s.place_interval(0,'LSHO',0,29)
        # Simulate a measured internal gap in the selected fixed channel.
        s.valid[channel,10:15]=False;s.points[:3,channel,10:15]=np.nan
        s.fill_enabled=True;s.max_gap_seconds=.05
        w.selected_source=channel;w.refresh()
        self.assertEqual(len(w.fill_lines),3)
        for line in w.fill_lines:
            self.assertEqual(line.get_linestyle(),'-')
            np.testing.assert_allclose(np.asarray(line.get_xdata())[np.isfinite(line.get_xdata())],np.arange(9,16)/s.rate)
            self.assertTrue(np.isfinite(line.get_ydata()[:-1]).all())
        s.fill_enabled=False;w.refresh();self.assertEqual(w.fill_lines,[])

    def test_empty_target_and_undo(self):
        s=self.w.s;before=s.snapshot();points=s.points.copy()
        channel=s.place_interval(4,'LFIN',10,20)
        np.testing.assert_array_equal(s.points[:3,channel,10:21],points[:3,4,10:21])
        self.assertFalse(s.valid[4,10:21].any())
        self.assertFalse(s.valid[channel,:10].any())
        s.undo();self.assertEqual(s.snapshot(),before);np.testing.assert_array_equal(s.points,points)
        s.redo();np.testing.assert_array_equal(s.points[:3,s.slot_channels['LFIN'],10:21],points[:3,4,10:21])

    def test_continuous_shift_click_plain_seek_drag_zoom_and_steps(self):
        from matplotlib.backend_bases import MouseEvent
        w=self.w;w.s.valid[0,10:15]=False;w.refresh();w.sources.setCurrentRow(0)
        w.show();self.app.processEvents();w.curve_canvas.draw()
        def send(kind,time,key=None):
            x,y=w.curve.transData.transform((time,np.mean(w.curve.get_ylim())))
            w.curve_canvas.callbacks.process(kind,MouseEvent(kind,w.curve_canvas,x,y,button=1,key=key))
        send('button_press_event',.1);send('button_release_event',.1)
        self.assertEqual(w.frame.value(),w.s.first+20)
        send('button_press_event',.1,'shift');send('button_release_event',.1,'shift')
        self.assertEqual((w.start.value(),w.end.value()),(w.s.first+15,w.s.first+29))
        send('button_press_event',.02);send('motion_notify_event',.09);send('button_release_event',.09)
        self.assertLessEqual(abs(w.start.value()-(w.s.first+4)),1)
        self.assertLessEqual(abs(w.end.value()-(w.s.first+18)),1)
        w.zoom_time(.5,anchor=.07);view=w.time_view;self.assertLess(view[1]-view[0],w.duration())
        w.pan_time(9000);self.assertGreater(w.time_view[0],view[0])
        current=w.frame.value();w.step(1);self.assertEqual(w.frame.value(),current+1);w.step(-1);self.assertEqual(w.frame.value(),current)
        w.full_time();self.assertEqual(w.time_view,(0,w.duration()))
        from PySide6 import QtTest,QtCore
        w.activateWindow();w.setFocus();self.app.processEvents()
        current=w.frame.value();QtTest.QTest.keyClick(w,QtCore.Qt.Key.Key_Right)
        self.assertEqual(w.frame.value(),current+1)
        QtTest.QTest.keyClick(w,QtCore.Qt.Key.Key_Left);self.assertEqual(w.frame.value(),current)

    def test_camera_visibility_tabs_and_save(self):
        w=self.w;self.assertEqual(w.tabs.count(),2)
        w.sources.item(4).setCheckState(__import__('PySide6').QtCore.Qt.CheckState.Unchecked);self.assertNotIn(4,w.raw_visible)
        w.show_all();self.assertIn(4,w.raw_visible)
        w.point_size.setValue(6);self.assertEqual(w.cloud.get_sizes()[0],6)
        w.ax.set_xlim(-100,400);before=w.ax.get_xlim();w.frame.setValue(w.s.first+10);self.assertEqual(w.ax.get_xlim(),before)
        dest=str(Path(self.tmp.name)/'saved.json');w.choose=lambda *args:dest
        self.assertTrue(w.save());self.assertEqual(Session.load_project(dest).snapshot(),w.s.snapshot())

    def test_camera_orbit_keeps_ground_level(self):
        w=self.w;self.assertEqual(rcParams['axes3d.mouserotationstyle'],'azel')
        w.ax.view_init(25,-50,roll=37);w.lock_ground_horizon()
        self.assertAlmostEqual(w.ax.roll,0)

    def test_repeated_placement_is_idempotent_and_number_fixed(self):
        s=self.w.s;channel=s.place_interval(4,'LFIN',0,29)
        assignments=s.snapshot()['assignments'];points=s.points.copy()
        channel2=s.place_interval(channel,'LFIN',0,29)
        self.assertEqual(channel,channel2);self.assertEqual(s.assignments,assignments)
        np.testing.assert_array_equal(s.points,points)

if __name__=='__main__':unittest.main()
