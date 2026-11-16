import json,sys,tempfile,unittest,zipfile,shutil
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_windows import source_kit,APP_MODULES
from runtime_paths import data_dir

class WindowsPackagingTests(unittest.TestCase):
    def test_source_kit_is_complete_and_excludes_trial_and_heel_utilities(self):
        with tempfile.TemporaryDirectory() as folder:
            package=source_kit(Path(folder)/'windows.zip')
            with zipfile.ZipFile(package) as archive:
                names=archive.namelist();relative=[name.split('/',1)[1] for name in names]
                for name in APP_MODULES+['build_windows.bat','C3DMarkerEditor.spec','windows_runtime_hook.py']:self.assertIn(name,relative)
                self.assertFalse(any('heel' in name.lower() or 'correct_ankles' in name or name.endswith(('.c3d','.npz','.bak','.command')) for name in relative))
                self.assertNotIn('ui_settings.ini',relative)
                self.assertFalse(any('自动恢复' in name or '项目/' in name or '.venv/' in name for name in relative))
                self.assertIsNone(archive.testzip())

    def test_frozen_windows_settings_are_stored_outside_resources(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(sys,'frozen',True,create=True),patch.object(sys,'platform','win32'),patch.dict('os.environ',{'LOCALAPPDATA':folder}):
                self.assertEqual(data_dir(),Path(folder)/'三维动作捕捉标记点智能校准软件');self.assertTrue(data_dir().is_dir())

    def test_project_moved_between_operating_systems_resolves_colocated_source(self):
        import ezc3d,numpy as np
        from core import Session
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.c3d';c=ezc3d.c3d();c['parameters']['POINT']['RATE']['value']=[200.];c['parameters']['POINT']['LABELS']['value']=['A'];c['data']['points']=np.zeros((4,1,5));c.write(str(source))
            session=Session(source);original=root/'original.json';session.save_project(original)
            moved=root/'moved';moved.mkdir();shutil.copy2(source,moved/source.name)
            data=json.loads(original.read_text(encoding='utf-8'));data['source']='C:\\DifferentComputer\\source.c3d';data.pop('source_relative',None)
            project=moved/'project.json';project.write_text(json.dumps(data),encoding='utf-8')
            loaded=Session.load_project(project);self.assertEqual(loaded.path,(moved/source.name).resolve());self.assertEqual(loaded.snapshot(),session.snapshot())
