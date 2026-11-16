"""Executed by PyInstaller before importing Qt, Matplotlib, and the application."""
import os
from runtime_paths import data_dir
os.environ.setdefault('QT_API','pyside6')
os.environ.setdefault('MPLBACKEND','QtAgg')
os.environ.setdefault('MPLCONFIGDIR',str(data_dir()/'matplotlib-cache'))
