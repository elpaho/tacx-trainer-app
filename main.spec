# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
			('ui', 'ui'),
			('ble', 'ble'),
			('intervals', 'intervals'),
			('models', 'models'),
			('workout', 'workout'),
			('version.py', '.')
	],
	hiddenimports=[
		'PyQt6.QtCharts',
		'PyQt6.QtCore', 
		'PyQt6.QtGui',
		'PyQt6.QtWidgets',
		'PyQt6.sip',
		'ble',
		'intervals',
		'models',
		'workout',
		'ui'
	],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='main',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
