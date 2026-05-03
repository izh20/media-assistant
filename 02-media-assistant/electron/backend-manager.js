const { spawn } = require('child_process');
const path = require('path');
const net = require('net');
const { app } = require('electron');

class BackendManager {
  constructor() {
    this.process = null;
    this.port = 8090;
    this._restartCount = 0;
    this._stopping = false;
    this._onFatalCrash = null;
  }

  getBackendPath() {
    if (app.isPackaged) {
      const name = process.platform === 'win32' ? 'media-assistant.exe' : 'media-assistant';
      return path.join(process.resourcesPath, 'backend', name);
    }
    // Dev mode: run Python directly
    if (process.platform === 'win32') {
      return path.join(__dirname, '..', '.venv', 'Scripts', 'python.exe');
    }
    return path.join(__dirname, '..', '.venv', 'bin', 'python');
  }

  getBackendArgs() {
    if (app.isPackaged) {
      return [];
    }
    return ['video_subtitle_app.py'];
  }

  getBackendCwd() {
    if (app.isPackaged) {
      return path.join(process.resourcesPath, 'backend');
    }
    return path.join(__dirname, '..');
  }

  getDataDir() {
    return path.join(app.getPath('documents'), 'MediaAssistant');
  }

  getBundledDir() {
    if (app.isPackaged) {
      return path.join(process.resourcesPath, 'bundled');
    }
    return path.join(__dirname, '..', 'bundled');
  }

  async start() {
    this._stopping = false;

    // Kill any leftover process on the target port
    await this._killPortOccupant(8090);
    this.port = await this.findAvailablePort(8090);

    const backendPath = this.getBackendPath();
    const args = this.getBackendArgs();
    const cwd = this.getBackendCwd();

    console.log(`[backend] Starting: ${backendPath} ${args.join(' ')}`);
    console.log(`[backend] CWD: ${cwd}`);
    console.log(`[backend] Port: ${this.port}`);

    this.process = spawn(backendPath, args, {
      cwd,
      env: {
        ...process.env,
        MEDIA_ASSISTANT_PORT: String(this.port),
        MEDIA_ASSISTANT_DATA_DIR: this.getDataDir(),
        MEDIA_ASSISTANT_BUNDLED_DIR: this.getBundledDir(),
      },
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    this.process.stdout.on('data', (d) => {
      process.stdout.write(`[backend] ${d}`);
    });
    this.process.stderr.on('data', (d) => {
      process.stderr.write(`[backend:err] ${d}`);
    });

    this._setupCrashRecovery();
    await this.waitForReady();
  }

  stop() {
    this._stopping = true;
    if (this.process) {
      if (process.platform === 'win32') {
        this.process.kill();
      } else {
        this.process.kill('SIGTERM');
      }
      this.process = null;
    }
  }

  _setupCrashRecovery() {
    this.process.on('exit', (code) => {
      console.log(`[backend] exited with code: ${code}`);
      if (code !== 0 && code !== null && !this._stopping) {
        if (this._restartCount < 3) {
          this._restartCount++;
          console.log(`[backend] crash detected, restart attempt ${this._restartCount}/3`);
          // Wait 2s for port release, then restart
          setTimeout(() => {
            this.start().then(() => {
              console.log(`[backend] restarted on port ${this.port}`);
              if (this._onRestarted) this._onRestarted(this.port);
            }).catch(console.error);
          }, 2000);
        } else {
          console.error('[backend] max restart attempts reached');
          if (this._onFatalCrash) this._onFatalCrash();
        }
      }
    });
  }

  onFatalCrash(callback) {
    this._onFatalCrash = callback;
  }

  onRestarted(callback) {
    this._onRestarted = callback;
  }

  _killPortOccupant(port) {
    return new Promise((resolve) => {
      if (process.platform === 'win32') { resolve(); return; }
      const { exec } = require('child_process');
      exec(`lsof -ti :${port}`, (err, stdout) => {
        if (stdout && stdout.trim()) {
          const pids = stdout.trim().split('\n');
          for (const pid of pids) {
            try { process.kill(Number(pid), 'SIGTERM'); } catch {}
          }
          console.log(`[backend] killed old process(es) on port ${port}: ${pids.join(',')}`);
          setTimeout(resolve, 500);
        } else {
          resolve();
        }
      });
    });
  }

  findAvailablePort(startPort) {
    return new Promise((resolve) => {
      const server = net.createServer();
      server.listen(startPort, '127.0.0.1', () => {
        server.close(() => resolve(startPort));
      });
      server.on('error', () => {
        resolve(this.findAvailablePort(startPort + 1));
      });
    });
  }

  waitForReady(timeout = 30000) {
    const start = Date.now();
    return new Promise((resolve, reject) => {
      const check = () => {
        if (Date.now() - start > timeout) {
          reject(new Error('Backend startup timeout (30s)'));
          return;
        }
        const socket = new net.Socket();
        socket.setTimeout(500);
        socket.on('connect', () => {
          socket.destroy();
          // Extra delay for FastAPI to fully initialize
          setTimeout(resolve, 500);
        });
        socket.on('error', () => {
          setTimeout(check, 300);
        });
        socket.on('timeout', () => {
          socket.destroy();
          setTimeout(check, 300);
        });
        socket.connect(this.port, '127.0.0.1');
      };
      check();
    });
  }
}

module.exports = BackendManager;
