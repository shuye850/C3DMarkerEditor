# Build on 64-bit Windows with: python -m PyInstaller C3DMarkerEditor.spec
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

root=Path(SPECPATH)
APP_NAME='三维动作捕捉标记点智能校准软件'
ez_data,ez_binaries,ez_hidden=collect_all('ezc3d')
a=Analysis(
    [str(root/'windows_entry.py')],pathex=[str(root)],
    binaries=ez_binaries,datas=ez_data+[(str(root/'icons'),'icons')],
    hiddenimports=ez_hidden+['scipy.interpolate','matplotlib.backends.backend_qtagg','PySide6.QtSvg'],
    hookspath=[],runtime_hooks=[str(root/'windows_runtime_hook.py')],
    hooksconfig={'matplotlib':{'backends':['QtAgg']}},
    excludes=['PyQt5','PyQt6','PySide2','tkinter','IPython','pytest','heel_repair','correct_ankles'],
    noarchive=False,
)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name=APP_NAME,debug=False,
        bootloader_ignore_signals=False,strip=False,upx=False,console=False,
        disable_windowed_traceback=False)
# Do not bundle unrelated ICU 78 DLLs found on the build machine's PATH.
# They shadow Windows' ICU DLL and prevent the bundled Qt6Core from loading.
runtime_binaries=[item for item in a.binaries if item[0].lower() not in {'icuuc.dll','icudt78.dll'}]
coll=COLLECT(exe,runtime_binaries,a.datas,strip=False,upx=False,name=APP_NAME)
