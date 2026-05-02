"use strict";

const { app, BrowserWindow, ipcMain, dialog, shell } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const http = require("http");
const fs = require("fs");

// ── Config ────────────────────────────────────────────────────────────────────

const IS_DEV       = process.env.NODE_ENV === "development";
const SERVER_PORT  = 8000;
const BACKEND_DIR  = path.join(__dirname, "..", "..", "claude-dj");
const DIST_INDEX   = path.join(__dirname, "..", "dist", "index.html");

// ── Python server lifecycle ───────────────────────────────────────────────────

let serverProcess = null;

function startPythonServer() {
  // In dev the developer is expected to run the server manually, but we still
  // try — if the port is already bound, uvicorn exits cleanly and we carry on.
  const logFile = fs.createWriteStream(
    path.join(app.getPath("logs"), "claude-dj-server.log"),
    { flags: "a" },
  );

  // Python resolution priority: .venv → conda claude-dj env → system python3
  const candidates = [
    path.join(BACKEND_DIR, ".venv", "bin", "python"),
    "/opt/anaconda3/envs/claude-dj/bin/python",
    "/opt/homebrew/bin/python3",
    "python3",
  ];
  const python = candidates.find((p) => p === "python3" || fs.existsSync(p));

  // Forward ANTHROPIC_API_KEY from the shell environment (set before launching)
  const env = { ...process.env };

  serverProcess = spawn(python, ["cli.py", "serve", "--port", String(SERVER_PORT)], {
    cwd:   BACKEND_DIR,
    env,
    stdio: ["ignore", "pipe", "pipe"],
  });

  serverProcess.stdout.pipe(logFile);
  serverProcess.stderr.pipe(logFile);

  serverProcess.on("error", (err) => {
    console.error("[server] failed to start:", err.message);
  });
}

function waitForServer(maxRetries = 40, intervalMs = 500) {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const check = () => {
      const req = http.get(`http://127.0.0.1:${SERVER_PORT}/health`, (res) => {
        if (res.statusCode === 200) {
          resolve();
        } else {
          retry();
        }
      });
      req.on("error", retry);
      req.setTimeout(400, () => { req.destroy(); retry(); });
    };
    const retry = () => {
      if (++attempts >= maxRetries) {
        reject(new Error(`Server did not start after ${maxRetries} attempts`));
      } else {
        setTimeout(check, intervalMs);
      }
    };
    check();
  });
}

// ── Window ────────────────────────────────────────────────────────────────────

let mainWindow = null;

async function createWindow() {
  mainWindow = new BrowserWindow({
    width:           1280,
    height:          820,
    minWidth:        960,
    minHeight:       600,
    titleBarStyle:   "hiddenInset",   // macOS: traffic lights inset into toolbar
    backgroundColor: "#0c0c0c",
    vibrancy:        "under-window",  // macOS: frosted glass chrome
    show:            false,           // reveal after content loads
    webPreferences: {
      preload:          path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration:  false,
      sandbox:          false,
    },
  });

  mainWindow.once("ready-to-show", () => mainWindow.show());

  // Start server (non-blocking) then poll until ready
  startPythonServer();
  try {
    await waitForServer();
  } catch (err) {
    console.error("[electron] server never became ready:", err.message);
    // Load anyway — the app will show error states for failed requests
  }

  if (IS_DEV) {
    await mainWindow.loadURL(`http://localhost:5173`);
    mainWindow.webContents.openDevTools({ mode: "detach" });
  } else {
    await mainWindow.loadFile(DIST_INDEX);
  }
}

// ── App events ────────────────────────────────────────────────────────────────

app.whenReady().then(createWindow);

app.on("window-all-closed", () => {
  killServer();
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});

app.on("before-quit", killServer);

function killServer() {
  if (serverProcess) {
    serverProcess.kill("SIGTERM");
    serverProcess = null;
  }
}

// ── IPC handlers ─────────────────────────────────────────────────────────────

ipcMain.handle("select-folder", async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title:       "Select Music Folder",
    buttonLabel: "Analyze",
    properties:  ["openDirectory", "createDirectory"],
  });
  return result.canceled ? null : (result.filePaths[0] ?? null);
});

ipcMain.handle("show-item-in-folder", (_e, filePath) => {
  shell.showItemInFolder(filePath);
});
