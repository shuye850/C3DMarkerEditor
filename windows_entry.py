"""GUI entry point with packaged startup diagnostics and a real bundle smoke test."""
import json,os,sys,traceback,tempfile
from pathlib import Path
from runtime_paths import data_dir

def self_test(report=None):
    import numpy as np
    import ezc3d
    from PySide6 import QtWidgets as W,QtGui
    from app import Editor
    from core import Session
    application=W.QApplication.instance() or W.QApplication([])
    with tempfile.TemporaryDirectory() as folder:
        # ezc3d's writer cannot create a Unicode filename on all Windows builds.
        # Write first using an ASCII name, then rename with pathlib so the reader
        # still verifies that packaged applications can open Unicode paths.
        source=Path(folder)/'中文路径测试.c3d';temporary_source=Path(folder)/'unicode-path-test.c3d';c=ezc3d.c3d()
        c['parameters']['POINT']['LABELS']['value']=['A','B']
        c['parameters']['POINT']['RATE']['value']=[200.]
        c['parameters']['POINT']['UNITS']['value']=['mm']
        points=np.zeros((4,2,30));points[0]=np.arange(30);points[1,1]=100;points[2]=1000
        c['data']['points']=points;c.write(str(temporary_source));temporary_source.replace(source)
        session=Session(source);session.assign('LFHD',0,0,29);session.assign('RFHD',1,0,29)
        window=Editor(persist_layout=False);window.write_recovery=lambda:None
        try:
            window.set_session(session);window.tabs.setCurrentIndex(1);window.resize(1200,850);window.show();application.processEvents()
            for field in [window.fill_scope,window.fill_time,window.fill_start,window.fill_method]:
                assert field.isVisible() and field.width()>40,'Invisible fill control'
            for icon in ['up.svg','down.svg']:
                path=Path(__file__).parent/'icons'/icon
                assert path.exists() and not QtGui.QIcon(str(path)).pixmap(16,16).isNull(),'Missing SVG support or icon asset'
            output=Path(folder)/'导出.c3d';session.export(output)
            loaded=Session.load_project(str(output)+'.project.json');assert loaded.snapshot()==session.snapshot()
            assert Path(str(output)+'.provenance.npz').exists()
        finally:window.saved_state=session.snapshot();window.close();application.processEvents()
    if report:Path(report).write_text(json.dumps({'ok':True,'platform':sys.platform,'frozen':bool(getattr(sys,'frozen',False))},indent=2),encoding='utf-8')
    return 0

def main():
    testing='--self-test' in sys.argv
    report=Path(sys.argv[sys.argv.index('--report')+1]) if '--report' in sys.argv else None
    try:
        if testing:return self_test(report)
        from PySide6 import QtWidgets as W
        from app import Editor
        from core import Session
        application=W.QApplication(sys.argv);window=Editor()
        if len(sys.argv)>1:
            path=Path(sys.argv[1])
            window.guard(lambda:window.set_session(Session.load_project(path),path) if path.suffix.lower()=='.json' else window.set_session(Session(path)))
        window.show();return application.exec()
    except Exception:
        detail=traceback.format_exc();folder=data_dir()/'logs';folder.mkdir(parents=True,exist_ok=True)
        log=folder/'startup-error.txt';log.write_text(detail,encoding='utf-8')
        if testing and report:report.write_text(json.dumps({'ok':False,'error':detail},ensure_ascii=False),encoding='utf-8')
        if sys.platform=='win32' and not testing:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,f'程序启动失败，详细信息已保存至：\n{log}','三维动作捕捉标记点智能校准软件',0x10)
        elif sys.stderr:sys.stderr.write(detail)
        return 1

if __name__=='__main__':sys.exit(main())
