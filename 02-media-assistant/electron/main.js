const { app, BrowserWindow, Menu, shell, Tray, nativeImage } = require('electron');
const path = require('path');
const BackendManager = require('./backend-manager');
const { setupAutoUpdater } = require('./updater');

let mainWindow = null;
let tray = null;
const backendManager = new BackendManager();

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    title: 'Media Assistant',
    icon: path.join(__dirname, 'assets', 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
    show: false,
  });

  mainWindow.loadURL(`http://127.0.0.1:${backendManager.port}`);

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  // External links open in system browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  // Close → hide to tray (don't quit)
  mainWindow.on('close', (e) => {
    if (!app.isQuitting) {
      e.preventDefault();
      mainWindow.hide();
    }
  });
}

function createTray() {
  const iconPath = path.join(__dirname, 'assets', 'icon.png');
  const icon = nativeImage.createFromPath(iconPath).resize({ width: 22, height: 22 });
  tray = new Tray(icon);

  const contextMenu = Menu.buildFromTemplate([
    { label: '打开 Media Assistant', click: () => mainWindow && mainWindow.show() },
    { type: 'separator' },
    { label: '退出', click: () => { app.isQuitting = true; app.quit(); } },
  ]);

  tray.setToolTip('Media Assistant');
  tray.setContextMenu(contextMenu);
  tray.on('double-click', () => mainWindow && mainWindow.show());
}

app.whenReady().then(async () => {
  try {
    await backendManager.start();
  } catch (err) {
    const { dialog } = require('electron');
    dialog.showErrorBox('启动失败', `后端服务启动失败: ${err.message}\n\n请检查日志后重试。`);
    app.quit();
    return;
  }

  createWindow();
  createTray();
  setupAutoUpdater(mainWindow);

  // Backend crash handler
  backendManager.onFatalCrash(() => {
    if (mainWindow) {
      mainWindow.loadURL(`data:text/html,<html><body style="background:#1a1a2e;color:#eee;display:flex;align-items:center;justify-content:center;height:100vh;font-family:system-ui"><div style="text-align:center"><h2>⚠️ 后端服务异常退出</h2><p>已尝试重启 3 次仍然失败</p><p>请退出应用后重新打开</p></div></div></body></html>`);
    }
  });

  // Backend restart handler - reload window with new port
  backendManager.onRestarted((port) => {
    if (mainWindow) {
      mainWindow.loadURL(`http://127.0.0.1:${port}`);
    }
  });
});

app.on('before-quit', () => {
  app.isQuitting = true;
  backendManager.stop();
});

app.on('activate', () => {
  if (mainWindow) {
    mainWindow.show();
  }
});
