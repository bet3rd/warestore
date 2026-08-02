import os

from PyInstaller.utils.hooks import collect_all

block_cipher = None

ROOT = os.path.abspath('.')
ICON = os.path.join(ROOT, 'assets', 'warestore.ico')

# The HWID spoofer (injector.exe) is intentionally NOT bundled — it keeps the
# base install a plain account manager (cleaner AV profile). The user installs
# it on demand from Settings, which downloads it from the spoofer repo's
# releases into %APPDATA% (see infrastructure/steam/injector_stage.py).

# ── collect cryptography (ships a compiled Rust binding that must be bundled) ─
crypto_datas, crypto_binaries, crypto_hidden = collect_all('cryptography')

# ── collect the CS2 rank-mint stack: ValvePython/steam (dynamically-imported
# generated protobufs), gevent (many C-extension submodules), and protobuf.
# Used by the in-process CM cookie mint (infrastructure/steam/cs2_cm_mint.py).
steam_datas, steam_binaries, steam_hidden = collect_all('steam')
gevent_datas, gevent_binaries, gevent_hidden = collect_all('gevent')
proto_datas, proto_binaries, proto_hidden = collect_all('google.protobuf')

# The app only uses QtCore/QtGui/QtWidgets (+ QtNetwork for single-instance IPC).
# Rely on PyInstaller's built-in PyQt5 hook to bundle just those imported modules
# — NOT collect_all, which drags in QML, WebEngine, Multimedia, the 20MB
# software-OpenGL renderer, translations, and every plugin. Unused Qt submodules
# are excluded explicitly, and the leftover dead weight is filtered out below.
_QT_EXCLUDES = [
    'PyQt5.QtQml', 'PyQt5.QtQuick', 'PyQt5.QtQuickWidgets', 'PyQt5.QtQuick3D',
    'PyQt5.QtQuickControls2', 'PyQt5.QtWebEngine', 'PyQt5.QtWebEngineCore',
    'PyQt5.QtWebEngineWidgets', 'PyQt5.QtWebSockets', 'PyQt5.QtWebChannel',
    'PyQt5.QtMultimedia', 'PyQt5.QtMultimediaWidgets', 'PyQt5.QtBluetooth',
    'PyQt5.QtNfc', 'PyQt5.QtPositioning', 'PyQt5.QtLocation', 'PyQt5.QtSensors',
    'PyQt5.QtSerialPort', 'PyQt5.QtSql', 'PyQt5.QtTest', 'PyQt5.QtXml',
    'PyQt5.QtXmlPatterns', 'PyQt5.QtDesigner', 'PyQt5.QtHelp',
    'PyQt5.QtPrintSupport', 'PyQt5.Qt3DCore', 'PyQt5.QtDBus',
]
_STDLIB_EXCLUDES = ['tkinter', 'unittest', 'pydoc', 'test', 'lib2to3', 'xmlrpc']

a = Analysis(
    [os.path.join(ROOT, 'src', 'warestore', 'presentation', 'account_manager', 'main.py')],
    pathex=[os.path.join(ROOT, 'src')],
    binaries=crypto_binaries + steam_binaries + gevent_binaries + proto_binaries,
    datas=[
        (ICON, 'assets'),
        (os.path.join(ROOT, 'assets', 'ranks'), 'assets/ranks'),
        (os.path.join(ROOT, 'assets', 'fonts'), 'assets/fonts'),
        (
            os.path.join(ROOT, 'src', 'warestore', 'presentation',
                         'account_manager', 'ui', 'theme', 'qss'),
            'warestore/presentation/account_manager/ui/theme/qss',
        ),
    ] + crypto_datas + steam_datas + gevent_datas + proto_datas,
    hiddenimports=[
        'win32crypt', 'win32timezone', 'jwt', 'vdf', 'chardet',
        'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets', 'PyQt5.QtNetwork',
        'greenlet',
    ] + crypto_hidden + steam_hidden + gevent_hidden + proto_hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=_QT_EXCLUDES + _STDLIB_EXCLUDES,
    cipher=block_cipher,
    noarchive=False,
)

# ── trim dead weight the PyQt5 hook still bundles ────────────────────────────
# Individual DLLs a widgets-only app never touches: the software-GL renderer,
# the D3D/ANGLE shader compiler, and Qt's OpenSSL (we only do local-socket IPC).
_DROP_DLLS = {
    'opengl32sw.dll', 'd3dcompiler_47.dll',
    'libcrypto-1_1-x64.dll', 'libssl-1_1-x64.dll', 'libeay32.dll', 'ssleay32.dll',
    'qt5quick.dll', 'qt5qml.dll', 'qt5qmlmodels.dll', 'qt5designer.dll',
}
# Qt plugin categories we actually need (platform, native style, avatar codecs).
_KEEP_PLUGINS = {'platforms', 'styles', 'imageformats', 'iconengines'}


def _norm(p):
    return p.replace('\\', '/').lower()


def _keep_binary(dest):
    name = os.path.basename(dest).lower()
    if name in _DROP_DLLS:
        return False
    # Pillow's AVIF codec (~8MB: libavif + aom/dav1d). Steam avatars are PNG/JPG;
    # Pillow degrades gracefully when a format plugin's binary is absent.
    if name.startswith('_avif'):
        return False
    parts = _norm(dest).split('/')
    if 'plugins' in parts:
        i = parts.index('plugins')
        if i + 1 < len(parts) and parts[i + 1] not in _KEEP_PLUGINS:
            return False
    return True


a.binaries = [b for b in a.binaries if _keep_binary(b[0])]
# Qt translations (qt_*.qm) — the UI is English-only.
a.datas = [d for d in a.datas if '/translations/' not in _norm(d[0])
           and not _norm(d[0]).endswith('.qm')]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# onedir: the app ships as a folder that the Inno Setup installer places under
# Program Files (see installer/warestore.iss). No temp _MEI extraction, faster
# startup. User data (tokens, injector, hardware_pool, profiles) is written to
# %APPDATA%, never the read-only install dir.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='WareStore',
    debug=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,
    # Embed a requireAdministrator manifest so the app always launches
    # elevated (UAC prompt on open). Needed because the HWID spoofer/injector
    # and Steam process/file manipulation require admin rights.
    uac_admin=True,
    icon=ICON,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='WareStore',
)
