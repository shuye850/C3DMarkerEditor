"""Separate bundled, read-only resources from writable user settings."""
import os,sys
from pathlib import Path

def data_dir():
    if not getattr(sys,'frozen',False):return Path(__file__).resolve().parent
    if sys.platform=='win32':base=Path(os.environ.get('LOCALAPPDATA') or Path.home()/'AppData'/'Local')
    elif sys.platform=='darwin':base=Path.home()/'Library'/'Application Support'
    else:base=Path(os.environ.get('XDG_DATA_HOME') or Path.home()/'.local'/'share')
    folder=base/'三维动作捕捉标记点智能校准软件';folder.mkdir(parents=True,exist_ok=True);return folder
