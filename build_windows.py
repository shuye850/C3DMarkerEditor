"""Create a private-data-free source kit, or build and test a Windows app bundle."""
import argparse,hashlib,json,os,platform,shutil,struct,subprocess,sys,zipfile
from datetime import datetime,timezone
from importlib.metadata import version
from pathlib import Path

ROOT=Path(__file__).resolve().parent
APP_MODULES=['app.py','core.py','body_model.py','candidate_pool.py','environment_grid.py','fill_page.py','gap_smoothing.py','marker_names.py','menu_bar.py','model_schemes.py','pairing_table.py','player_widgets.py','runtime_paths.py','scheme_dialog.py','segment_repair.py','ui_theme.py','viewer_axes.py','windows_entry.py']
BUILD_FILES=['build_windows.py','build_windows.bat','C3DMarkerEditor.spec','windows_runtime_hook.py','requirements.txt','requirements-windows-build.txt','Windows使用说明.txt']
APP_NAME='三维动作捕捉标记点智能校准软件'

def source_kit(destination):
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    files=[ROOT/name for name in APP_MODULES+BUILD_FILES]
    files+=sorted((ROOT/'icons').glob('*.svg'))
    # Explicitly include only the editor's synthetic tests, not trial-specific utilities.
    files+=[p for p in sorted((ROOT/'tests').glob('test_*.py')) if 'heel' not in p.name.lower()]
    files+=list((ROOT/'tests'/'fixtures').glob('*.ini'))
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            if not path.is_file():raise FileNotFoundError(path)
            archive.write(path,'C3DMarkerEditor-Windows-Source/'+path.relative_to(ROOT).as_posix())
    return destination

def build():
    if sys.platform!='win32':raise SystemExit('Windows executables must be built on Windows. Use --source-kit on macOS.')
    if struct.calcsize('P')!=8 or platform.machine().lower() not in ('amd64','x86_64'):raise SystemExit('Use 64-bit x86 Python for this Windows x64 build.')
    subprocess.run([sys.executable,'-m','unittest','discover','-s','tests'],cwd=ROOT,check=True,env=dict(os.environ,QT_QPA_PLATFORM='offscreen',QT_STYLE_OVERRIDE='Fusion'))
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean',str(ROOT/'C3DMarkerEditor.spec')],cwd=ROOT,check=True)
    dist=ROOT/'dist';folder=dist/APP_NAME;exe=folder/f'{APP_NAME}.exe'
    report=dist/'windows-self-test.json'
    report.unlink(missing_ok=True)
    subprocess.run([str(exe),'--self-test','--report',str(report)],cwd=folder,env=dict(os.environ,QT_QPA_PLATFORM='offscreen'),timeout=180,check=True)
    if not json.loads(report.read_text(encoding='utf-8'))['ok']:raise RuntimeError('The packaged application failed its smoke test.')
    shutil.copy2(ROOT/'Windows使用说明.txt',folder/'Windows使用说明.txt')
    manifest={'built_at_utc':datetime.now(timezone.utc).isoformat(),'target':'Windows x64','python':platform.python_version(),
              'dependencies':{name:version(name) for name in ['ezc3d','numpy','scipy','PySide6-Essentials','matplotlib','pyinstaller']},
              'sources':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in APP_MODULES}}
    (folder/'build-info.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    output=shutil.make_archive(str(dist/f'{APP_NAME}-Windows-x64'),'zip',root_dir=dist,base_dir=APP_NAME)
    print('Windows build and executable self-test passed.\n'+output)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source-kit',type=Path);args=parser.parse_args()
    if args.source_kit:print(source_kit(args.source_kit))
    else:build()
