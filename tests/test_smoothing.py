import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import ezc3d
from scipy.interpolate import PchipInterpolator
from core import Session
from gap_smoothing import smooth_gap,suspicious_anchor

class Smoothing(unittest.TestCase):
    def test_smooth_known_quadratic_without_changing_endpoints(self):
        t=np.arange(60,dtype=float);xyz=np.array([t*t,2*t*t,np.ones(60)*50]);measured=np.ones(60,dtype=bool)
        left,right=19,31;measured[left+1:right]=False;support=np.r_[np.arange(16,20),np.arange(31,35)];target=np.arange(left+1,right)
        baseline=PchipInterpolator(support,xyz[:,support],axis=1)(target)
        result=smooth_gap(xyz,measured,left,right,baseline,1.,7)
        np.testing.assert_allclose(result,xyz[:,target],atol=1e-8)
        self.assertGreater(np.max(abs(baseline-xyz[:,target])),1e-3)
        np.testing.assert_array_equal(smooth_gap(xyz,measured,left,right,baseline,0.,7),baseline)
        for dim in range(3):
            self.assertTrue(np.all(result[dim]>=min(xyz[dim,left],xyz[dim,right])-1e-10))
            self.assertTrue(np.all(result[dim]<=max(xyz[dim,left],xyz[dim,right])+1e-10))
    def test_boundary_spike_detection(self):
        t=np.arange(30,dtype=float);xyz=np.array([t,t*t,np.zeros(30)]);mask=np.ones(30,dtype=bool)
        self.assertFalse(suspicious_anchor(xyz,mask,15,-1))
        xyz[:,15]+=100
        self.assertTrue(suspicious_anchor(xyz,mask,15,-1))
    def test_smoothed_job_persists_and_preserves_measured_samples(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'quadratic.c3d';c=ezc3d.c3d();c['parameters']['POINT']['RATE']['value']=[200.]
            c['parameters']['POINT']['LABELS']['value']=['A'];t=np.arange(60,dtype=float)
            data=np.zeros((4,1,60));data[:3,0]=np.array([t*t,2*t*t,np.ones(60)*50]);c['data']['points']=data
            residual=np.zeros((1,1,60));residual[0,0,20:31]=-1;c['data']['meta_points']['residuals']=residual
            c['data']['meta_points']['camera_masks']=np.zeros((7,1,60),dtype=bool);c.write(str(path))
            s=Session(path);s.assign('LFHD',0,0,59);original=s.points.copy();s.add_fill_job(['LFHD'],20,30,'pchip',.1,1.,7)
            xyz,status,_=s.build();good=s.valid[0]
            np.testing.assert_array_equal(xyz[:,0,good],original[:3,0,good]);np.testing.assert_array_equal(s.points,original)
            np.testing.assert_allclose(xyz[0,0,20:31],t[20:31]**2,atol=1e-8)
            project=Path(folder)/'smooth.json';s.save_project(project);restored=Session.load_project(project)
            self.assertEqual(restored.snapshot(),s.snapshot());np.testing.assert_array_equal(restored.build()[0],xyz)
            out=Path(folder)/'smooth.c3d';s.export(out);read=ezc3d.c3d(str(out))
            np.testing.assert_allclose(read['data']['points'][:3,0,20:31],xyz[:,0,20:31],rtol=1e-6)
            s.undo();self.assertFalse(s.fill_enabled)

if __name__=='__main__':unittest.main()
