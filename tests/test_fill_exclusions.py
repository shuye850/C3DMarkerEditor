import sys,json,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import ezc3d
from core import Session

class Exclusions(unittest.TestCase):
    def test_default_custom_wands_existing_rules_export_and_legacy_load(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'markers.c3d';c=ezc3d.c3d();c['parameters']['POINT']['RATE']['value']=[200.]
            c['parameters']['POINT']['LABELS']['value']=['arm','wand1','wand4']
            values=np.zeros((4,3,60));values[:3]=np.arange(60)[None,None,:]+np.arange(3)[:,None,None]
            c['data']['points']=values;residual=np.zeros((1,3,60));residual[:,:,20:25]=-1
            c['data']['meta_points']['residuals']=residual;c['data']['meta_points']['camera_masks']=np.zeros((7,3,60),dtype=bool);c.write(str(path))
            s=Session(path);custom='灯棒标记点4（WAND4）';s.update_slots(s.slots+['WAND1',custom])
            for slot,source in [('LSHO',0),('WAND1',1),(custom,2)]:s.assign(slot,source,0,59)
            self.assertIn(custom,s.fill_excluded)
            # A rule from an older project may include wands; the engine still skips them.
            s.fill_enabled=True;s.fill_jobs=[dict(slots=['LSHO','WAND1',custom],start=0,end=59,method='linear',max_gap_seconds=.1)]
            xyz,status,_=s.build()
            self.assertTrue(np.all(status[s.slots.index('LSHO'),20:25]==2))
            for name in ['WAND1',custom]:self.assertTrue(np.all(status[s.slots.index(name),20:25]==0))
            self.assertTrue(all('WAND' not in row['slot'] for row in s.gap_report(['LSHO','WAND1',custom],0,59,.1)))
            with self.assertRaises(ValueError):s.repair_preview('WAND1',20,24)
            s.set_fill_excluded([n for n in s.fill_excluded if n!='WAND1'])
            item=s.repair_preview('WAND1',20,24,'linear');s.apply_repair(item)
            s.set_fill_excluded(s.fill_excluded+['WAND1'])
            self.assertTrue(np.all(s.build()[1][s.slots.index('WAND1'),20:25]==0))
            project=Path(folder)/'saved.json';s.save_project(project);loaded=Session.load_project(project)
            self.assertEqual(loaded.fill_excluded,s.fill_excluded)
            np.testing.assert_array_equal(loaded.build()[0],s.build()[0])
            legacy=json.loads(project.read_text(encoding='utf-8'));legacy['version']=7;legacy['state'].pop('fill_excluded');project.write_text(json.dumps(legacy),encoding='utf-8')
            self.assertIn(custom,Session.load_project(project).fill_excluded)
            out=Path(folder)/'export.c3d';s.export(out);read=ezc3d.c3d(str(out))
            j=s.slots.index('WAND1');self.assertTrue(np.all(read['data']['meta_points']['residuals'][0,j,20:25]<0))
            np.testing.assert_allclose(read['data']['points'][:3,j,:20],s.points[:3,1,:20])

if __name__=='__main__':unittest.main()
