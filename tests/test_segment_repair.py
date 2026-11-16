import sys,tempfile,unittest
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1])]
import numpy as np
import ezc3d
from core import Session

class RepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'spike.c3d'
        c=ezc3d.c3d();c['parameters']['POINT']['RATE']['value']=[200.];c['parameters']['POINT']['LABELS']['value']=['A'];c['parameters']['POINT']['UNITS']['value']=['mm']
        t=np.arange(60);data=np.zeros((4,1,60));data[:3,0]=np.array([2*t,-t,1000+t]);data[:3,0,25]+=[90,-50,60]
        c['data']['points']=data;residual=np.zeros((1,1,60));residual[0,0,20:31]=-1;residual[0,0,25]=0
        c['data']['meta_points']['residuals']=residual;c['data']['meta_points']['camera_masks']=np.zeros((7,1,60),dtype=bool);c.write(str(self.path))
        self.s=Session(self.path);self.s.assign('LWRB',0,0,59)
    def tearDown(self):self.tmp.cleanup()
    def test_bezier_replaces_hidden_single_point_preserves_endpoints_and_file(self):
        s=self.s;before=s.snapshot();raw=s.points.copy();j=s.slots.index('LWRB')
        item=s.repair_preview('LWRB',20,30,'bezier',.7)
        self.assertEqual(s.snapshot(),before);self.assertEqual((item['left'],item['right']),(19,31))
        s.apply_repair(item);xyz,status,_=s.build()
        self.assertTrue(np.all(status[j,20:31]==3))
        t=np.arange(20,31);np.testing.assert_allclose(xyz[:,j,20:31],np.array([2*t,-t,1000+t]),atol=1e-8)
        np.testing.assert_array_equal(s.points,raw)
        np.testing.assert_array_equal(xyz[:,j,:20],raw[:3,0,:20])
        np.testing.assert_array_equal(xyz[:,j,31:],raw[:3,0,31:])
        s.undo();self.assertEqual(s.snapshot(),before);s.redo();self.assertEqual(len(s.repairs),1)
        project=Path(self.tmp.name)/'fixed.json';s.save_project(project);r=Session.load_project(project)
        np.testing.assert_array_equal(r.build()[0],s.build()[0])
        out=Path(self.tmp.name)/'fixed.c3d';s.export(out);data=ezc3d.c3d(str(out))
        np.testing.assert_allclose(data['data']['points'][:3,j,20:31],xyz[:,j,20:31],rtol=1e-6)
        self.assertTrue(np.all(data['data']['meta_points']['residuals'][0,j,20:31]>=0))
    def test_bezier_preserves_turn_with_equal_endpoint_coordinate(self):
        from segment_repair import replacement_curve
        t=np.arange(41,dtype=float);xyz=np.array([t,100-(t-20)**2,np.zeros(41)])
        measured=np.ones(41,dtype=bool);measured[11:30]=False
        curved=replacement_curve(xyz,measured,11,29,'bezier',1.,7)
        straight=replacement_curve(xyz,measured,11,29,'linear',0.,7)
        values=np.array(curved['values']);line=np.array(straight['values'])
        # Y has equal endpoints but the surrounding motion rises then falls.
        self.assertGreater(values[1,9],line[1,9]+50)
        np.testing.assert_allclose(values[1],xyz[1,11:30],atol=1e-7)
        self.assertGreater(curved['deviation'],50)

    def test_linear_and_tension_zero_match_and_remove_is_local(self):
        a=self.s.repair_preview('LWRB',20,30,'linear');b=self.s.repair_preview('LWRB',20,30,'bezier',0.)
        np.testing.assert_allclose(a['values'],b['values']);self.s.apply_repair(a)
        self.s.remove_repairs('LWRB',24,26);status=self.s.build()[1][self.s.slots.index('LWRB')]
        self.assertTrue(np.all(status[20:24]==3));self.assertTrue(np.all(status[27:31]==3));self.assertEqual(status[25],1)
        with self.assertRaises(ValueError):self.s.repair_preview('LWRB',0,30)

if __name__=='__main__':unittest.main()
