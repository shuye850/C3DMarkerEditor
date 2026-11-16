import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import ezc3d
from core import Session

class Trajectories(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'input.c3d'
        c=ezc3d.c3d();c['parameters']['POINT']['RATE']['value']=[200.]
        c['parameters']['POINT']['LABELS']['value']=['A','B']
        points=np.zeros((4,2,100));points[:3]=np.arange(100)[None,None,:]+np.arange(3)[:,None,None]
        c['data']['points']=points
        residual=np.zeros((1,2,100));residual[0,0,40:]=-1;residual[0,1,:45]=-1
        c['data']['meta_points']['residuals']=residual
        c['data']['meta_points']['camera_masks']=np.zeros((7,2,100),dtype=bool)
        c.write(str(self.path));self.s=Session(self.path)
    def tearDown(self):self.tmp.cleanup()
    def test_default_scheme_contains_only_39_body_markers(self):
        from model_schemes import BODY39,STANDARD_PIG39
        self.assertEqual(self.s.slots,BODY39);self.assertEqual(len(self.s.slots),39)
        self.assertEqual(self.s.fill_excluded,[])
        self.assertEqual(set(BODY39)-set(STANDARD_PIG39),{'LMMA','RMMA'})
        self.assertEqual(set(STANDARD_PIG39)-set(BODY39),{'LHEE','RHEE'})

    def test_scheme_switch_preserves_used_medial_marker_and_roundtrip(self):
        from model_schemes import PRESETS
        s=self.s;s.place_interval(0,'LMMA',0,99);baseline=s.snapshot();points=s.points.copy()
        before=s.build(fill=False,repair=False)[0][:,s.slots.index('LMMA')].copy()
        retained=s.apply_model_scheme(PRESETS[1]);self.assertIn('LMMA',retained)
        self.assertIn('LHEE',s.model_scheme['body_slots']);self.assertNotIn('LMMA',s.model_scheme['body_slots'])
        self.assertIn('LMMA',s.model_scheme['extra_slots']);self.assertIn('LMMA',s.fill_excluded)
        np.testing.assert_array_equal(s.points,points)
        np.testing.assert_array_equal(s.build(fill=False,repair=False)[0][:,s.slots.index('LMMA')],before)
        path=Path(self.tmp.name)/'model.json';s.save_project(path);r=Session.load_project(path)
        self.assertEqual(r.snapshot(),s.snapshot())
        s.undo();self.assertEqual(s.snapshot(),baseline);s.redo();self.assertEqual(s.snapshot(),r.snapshot())

    def test_custom_scheme_connections_and_auxiliary_defaults(self):
        s=self.s
        value=dict(name='Two markers',body_slots=['LFHD','RFHD'],extra_slots=['AUX1'],connections=[['LFHD','RFHD']])
        s.apply_model_scheme(value);self.assertEqual(s.slots,['LFHD','RFHD','AUX1']);self.assertEqual(s.fill_excluded,['AUX1'])
        state=s.snapshot()
        with self.assertRaises(ValueError):s.apply_model_scheme(dict(value,connections=[['LFHD','UNKNOWN']]))
        self.assertEqual(s.snapshot(),state)
        s.assign('LFHD',0,0,99);s.assign('RFHD',1,0,99)
        path=Path(self.tmp.name)/'custom.json';s.save_project(path);r=Session.load_project(path)
        self.assertEqual(r.model_scheme['connections'],[['LFHD','RFHD']])

    def test_standard_scheme_visual_connections_ignore_retained_medial_extra(self):
        from body_model import segments
        from model_schemes import STANDARD_PIG39
        slots=['LKNE','LANK','LHEE','LTOE','LMMA'];xyz=np.zeros((3,5,1));xyz[0,:,0]=[1,2,3,4,999]
        status=np.ones((5,1),dtype=np.uint8)
        lines,_=segments(slots,xyz,status,0,body_slots=STANDARD_PIG39)
        self.assertGreaterEqual(len(lines),3);self.assertFalse(any(np.any(np.asarray(line)==999) for line in lines))
        lines,_=segments(slots,xyz,status,0,connections=[['LKNE','LANK']]);self.assertEqual(len(lines),1)
    def test_interval_exchange_is_bijective_across_missing_samples_and_roundtrip(self):
        s=self.s;s.assign('LFHD',0,0,99);s.assign('RFHD',1,0,99)
        original=s.points.copy();s.exchange_marker(0,'RFHD',35,50)
        matrix=s.pairing_matrix()
        self.assertTrue(np.all(matrix[1,35:51]==0));self.assertTrue(np.all(matrix[0,35:51]==1))
        self.assertEqual((matrix[0,0],matrix[1,0]),(0,1))
        for frame in range(s.frames):
            values=matrix[:,frame];values=values[values>=0];self.assertEqual(len(values),len(set(values)))
        np.testing.assert_array_equal(original,s.points)
        path=Path(self.tmp.name)/'exchange.json';s.save_project(path);r=Session.load_project(path)
        np.testing.assert_array_equal(r.pairing_matrix(),matrix)
        s.clear_pairing(40,42,marker=0);self.assertTrue(np.all(s.pairing_matrix()[1,40:43]==-1))
        self.assertEqual(s.pairing_matrix()[1,43],0)
        s.undo();np.testing.assert_array_equal(s.pairing_matrix(),matrix)
        s.split_marker(0,45,'R0_B');self.assertEqual(s.pairing_matrix()[1,45],2)
    def test_public_marker_split_preserves_samples_assignments_and_roundtrip(self):
        s=self.s;s.place_interval(0,'LFHD',0,99)
        before=s.build(fill=False,repair=False)[0].copy();counts=s.valid.sum(axis=0)
        new=s.split_marker(0,20,'R0_B')
        self.assertEqual(s.markers[0]['end'],19);self.assertEqual(s.markers[new]['start'],20)
        np.testing.assert_array_equal(s.valid.sum(axis=0),counts)
        np.testing.assert_array_equal(s.build(fill=False,repair=False)[0],before)
        self.assertTrue(np.all(s.marker_sources(0)[20:]==-1))
        self.assertTrue(np.all(s.marker_sources(new)[:20]==-1))
        s.place_marker_interval(new,'RFHD',20,39)
        actual=s.build(fill=False,repair=False)[0]
        np.testing.assert_array_equal(actual[:,1,20:40],before[:,0,20:40])
        np.testing.assert_array_equal(actual[:,0,:20],before[:,0,:20])
        path=Path(self.tmp.name)/'split.json';s.save_project(path);r=Session.load_project(path)
        self.assertEqual(r.snapshot(),s.snapshot());np.testing.assert_array_equal(r.points,s.points)
        s.undo();s.undo();self.assertEqual(len(s.markers),2)
        s.redo();self.assertEqual(len(s.markers),3)

    def test_public_marker_names_empty_addition_and_internal_ids(self):
        s=self.s;s.edit_marker_labels(['01','02','03'])
        self.assertEqual([m['label'] for m in s.markers],['01','02','03'])
        self.assertFalse(s.valid[s.custom_channels['user_0']].any())
        s.place_interval(0,'LFHD',0,99)
        self.assertEqual(s.public_marker_for(s.slot_channels['LFHD'],0),0)
        self.assertEqual(s.markers[0]['label'],'01')
        path=Path(self.tmp.name)/'labels.json';s.save_project(path);r=Session.load_project(path)
        self.assertEqual(r.snapshot(),s.snapshot())
        index=s.split_marker(0,20,'03');self.assertEqual(index,2)
        self.assertEqual(s.markers[2]['start'],20)
        with self.assertRaises(ValueError):s.split_marker(0,0,'bad')
        with self.assertRaises(ValueError):s.edit_marker_labels(['same','same','03'])
    def test_merge_gap_export(self):
        s=self.s;s.assign('LFHD',0,0,99);s.assign('LFHD',1,0,99)
        xyz,status,origin=s.build();self.assertTrue(np.all(status[0,40:45]==0))
        s.fill_enabled=True;s.max_gap_seconds=.025
        xyz,status,origin=s.build();self.assertTrue(np.all(status[0,40:45]==2))
        np.testing.assert_allclose(xyz[:,0],np.arange(100)[None,:]+np.arange(3)[:,None],atol=1e-6)
        out=Path(self.tmp.name)/'out.c3d';s.export(out);r=ezc3d.c3d(str(out))
        np.testing.assert_allclose(r['data']['points'][:3,0],xyz[:,0],atol=1e-6)
        s.save_project(Path(self.tmp.name)/'project.json');again=Session.load_project(Path(self.tmp.name)/'project.json')
        np.testing.assert_array_equal(again.build()[1],status)

    def test_unicode_c3d_paths_are_supported(self):
        source=Path(self.tmp.name)/'中文源文件.c3d';self.path.replace(source)
        session=Session(source);session.assign('LFHD',0,0,99);session.assign('RFHD',1,0,99)
        output=Path(self.tmp.name)/'中文导出.c3d';session.export(output)
        self.assertTrue(output.is_file())
        reloaded=Session(output)
        self.assertEqual(reloaded.frames,100)
    def test_scoped_fill_methods_gap_report_remove_and_persistence(self):
        s=self.s;s.assign('LFHD',0,0,99);s.assign('LFHD',1,0,99)
        s.assign('RFHD',1,0,44)  # No measured data in this second slot; cannot extrapolate.
        raw=s.points.copy();j=s.slots.index('LFHD')
        s.add_fill_job(['LFHD'],42,44,'linear',.1)
        self.assertTrue(np.all(s.build()[1][j,40:45]==0))
        self.assertEqual(s.gap_report(['LFHD'],42,44,.1)[0]['status'],'缺口跨出选区')
        s.add_fill_job(['LFHD'],40,44,'linear',.1)
        xyz,status,_=s.build();self.assertTrue(np.all(status[j,40:45]==2))
        self.assertTrue(np.all(status[s.slots.index('RFHD')]==0))
        self.assertEqual(s.gap_report(['LFHD'],40,44,.1)[0]['status'],'已补（插值）')
        np.testing.assert_array_equal(s.points,raw)
        path=Path(self.tmp.name)/'scoped.json';s.save_project(path)
        r=Session.load_project(path);self.assertEqual(r.snapshot(),s.snapshot())
        np.testing.assert_array_equal(r.build()[0],xyz)
        s.remove_fill_range(['LFHD'],40,44);self.assertTrue(np.all(s.build()[1][j,40:45]==0))
        s.undo();self.assertTrue(np.all(s.build()[1][j,40:45]==2))

    def test_placement_preserves_all_samples_with_mixed_missing_data(self):
        s=self.s;s.assign('RFHD',1,0,99);before=s.build();valid=s.valid.copy();points=s.points.copy()
        target=s.place_interval(0,'RFHD',10,70)
        for frame in range(s.frames):
            original=points[:3,valid[:,frame],frame].T
            current=s.points[:3,s.valid[:,frame],frame].T
            self.assertEqual(sorted(map(tuple,original)),sorted(map(tuple,current)))
        j=s.slots.index('RFHD');after=s.build()
        np.testing.assert_array_equal(after[0][:,j,:10],before[0][:,j,:10])
        np.testing.assert_array_equal(after[0][:,j,71:],before[0][:,j,71:])
        np.testing.assert_array_equal(s.valid[target,10:71],valid[0,10:71])
        path=Path(self.tmp.name)/'placed.json';s.save_project(path);r=Session.load_project(path)
        np.testing.assert_array_equal(r.points,s.points)
        np.testing.assert_array_equal(r.effective_meta['residuals'],s.effective_meta['residuals'])

    def test_identity_binding_is_global_and_cannot_be_overwritten(self):
        s=self.s;s.bind_identity('LFHD',0)
        self.assertEqual(s.assignments,[dict(slot='LFHD',source=0,start=0,end=99)])
        with self.assertRaises(ValueError):s.bind_identity('LFHD',1)
        with self.assertRaises(ValueError):s.bind_identity('RFHD',0)
        s.bind_identity('RFHD',1);fixed=s.snapshot()['assignments']
        s.renumber_interval([0,1],[1,0],45,99)
        self.assertEqual(s.assignments,fixed)
        self.assertEqual(s.build()[1][s.slots.index('LFHD'),50],1)

    def test_renumber_moves_gap_and_residual_together(self):
        s=self.s;s.assign('LFHD',0,0,99);s.assign('RFHD',1,0,99)
        valid=s.valid.copy();meta=s.effective_meta['residuals'].copy();assignments=s.snapshot()['assignments']
        s.renumber_interval([0,1],[1,0],40,99)
        np.testing.assert_array_equal(s.valid[0,40:],valid[1,40:])
        np.testing.assert_array_equal(s.effective_meta['residuals'][:,0,40:],meta[:,1,40:])
        self.assertEqual(s.assignments,assignments)
        path=Path(self.tmp.name)/'numbered.json';s.save_project(path);r=Session.load_project(path)
        np.testing.assert_array_equal(r.valid,s.valid)

    def test_swap_after_gap_persists_without_touching_other_frames(self):
        s=self.s;s.assign('LFHD',0,0,99);s.assign('RFHD',1,0,99)
        before=s.build();state=s.snapshot();s.swap_interval('LFHD','RFHD',45,99);after=s.build()
        a=s.slots.index('LFHD');b=s.slots.index('RFHD')
        for i in [0,1,2]:
            if i==0:
                np.testing.assert_array_equal(after[i][:,a,45:],before[i][:,b,45:])
                np.testing.assert_array_equal(after[i][:,b,45:],before[i][:,a,45:])
                np.testing.assert_array_equal(after[i][:,:,:45],before[i][:,:,:45])
            else:
                np.testing.assert_array_equal(after[i][a,45:],before[i][b,45:])
                np.testing.assert_array_equal(after[i][:,:45],before[i][:,:45])
        path=Path(self.tmp.name)/'swapped.json';s.save_project(path)
        np.testing.assert_array_equal(Session.load_project(path).build()[0],after[0])
        s.undo();self.assertEqual(s.snapshot(),state)
        with self.assertRaises(ValueError):s.swap_interval('LFHD','LFHD',0,99)

    def test_template_edits_preserve_pairings_and_save_backups(self):
        s=self.s;s.assign('LFHD',0,0,39);s.assign('LFHD',1,45,99)
        old=s.snapshot();s.update_slots(s.slots+['WAND4','WAND5'])
        self.assertEqual(s.assignments,old['assignments'])
        s.update_slots(list(reversed(s.slots)))
        self.assertEqual(s.assignments,old['assignments'])
        with self.assertRaises(ValueError):s.update_slots([n for n in s.slots if n!='LFHD'])
        self.assertEqual(s.assignments,old['assignments'])
        path=Path(self.tmp.name)/'saved.json';s.save_project(path)
        previous=path.read_bytes();s.fill_enabled=True;s.save_project(path)
        self.assertEqual(list(path.parent.glob('saved.json.*.bak'))[0].read_bytes(),previous)
        restored=Session.load_project(path)
        self.assertEqual(restored.snapshot(),s.snapshot())

    def test_conflicts_undo_and_long_gap(self):
        s=self.s;s.assign('LFHD',0,0,99)
        with self.assertRaises(ValueError):s.assign('RFHD',0,0,99)
        s.undo();self.assertEqual(len(s.assignments),0);s.redo();self.assertEqual(len(s.assignments),1)
        s.assign('LFHD',1,0,99);s.fill_enabled=True;s.max_gap_seconds=.02
        self.assertTrue(np.all(s.build()[1][0,40:45]==0))
        with self.assertRaises(ValueError):s.export(self.path)

if __name__=='__main__':unittest.main()
