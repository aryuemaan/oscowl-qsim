# Setup on Windows (Git Bash + VS Code)

This takes about 10 minutes the first time. Every command below runs in **Git Bash**.

## 1. Install the prerequisites

| Tool | Version | Where | Notes |
|---|---|---|---|
| Python | 3.11, 3.12 or 3.13 | python.org/downloads | Tick **"Add python.exe to PATH"** in the installer |
| Node.js | 22 LTS (20.19+ works) | nodejs.org | The default installer options are fine |
| Git for Windows | latest | git-scm.com | Includes **Git Bash** |
| VS Code | latest | code.visualstudio.com | Install the recommended extensions when prompted |

Check them in a new Git Bash window:

```bash
python --version     # Python 3.12.x  (or: py -3 --version)
node --version       # v22.x
npm --version
git --version
```

> If `python` opens the Microsoft Store, open *Settings → Apps → Advanced app settings →
> App execution aliases* and turn off the two "python" aliases, then reopen Git Bash.

## 2. Get the code and open it in VS Code

```bash
cd ~/Documents            # or wherever you keep projects
# unzip oscowl-qsim.zip here, or: git clone <your-repo-url> oscowl-qsim
cd oscowl-qsim
code .
```

VS Code asks to install the recommended extensions (Python, Pylance, Ruff, Docker). Accept.
The integrated terminal defaults to Git Bash (`.vscode/settings.json`).

## 3. One-time setup

```bash
bash scripts/setup.sh
```

This script:
- creates `.venv/` and installs `backend/requirements-dev.txt`
- runs `npm install` in `frontend/`
- copies `.env.example` to `.env`

In VS Code, choose the interpreter once: `Ctrl+Shift+P` → *Python: Select Interpreter* → `.venv`.

## 4. Run it

```bash
bash scripts/dev.sh
```

- App: http://localhost:5173
- API docs: http://localhost:8000/api/docs

You can also use two terminals (`bash scripts/run-backend.sh` and `bash scripts/run-frontend.sh`), or
VS Code *Terminal → Run Task → Dev: start everything*.

To debug the backend with breakpoints, open the Run and Debug view and choose **"Backend: FastAPI (debug)"**.

## 5. Test and benchmark

```bash
bash scripts/test.sh          # pytest (30 tests) + TypeScript type check
bash scripts/bench.sh --quick # 20-second benchmark
bash scripts/bench.sh         # full run, about 1-2 minutes (the dense 24-qubit case needs about 800 MB RAM)
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Python 3.10+ not found` | Reinstall Python with "Add to PATH", or check that `py -3 --version` works (the script tries `python3`, `python` and `py -3`). |
| `bash: $'\r': command not found` | The scripts got Windows line endings. Run `git config --global core.autocrlf input`, then re-clone, or in VS Code switch the file's EOL (bottom-right) from CRLF to LF. |
| Port 8000 or 5173 in use | `PORT=8001 bash scripts/run-backend.sh`; for the frontend, change `server.port` in `frontend/vite.config.ts` and the proxy target. |
| UI says "Backend not reachable on :8000" | Start the backend first and check its terminal for errors. |
| `npm` errors about the engine | Upgrade Node to 22 LTS. |
| `pip` cannot build numpy | Use Python 3.11–3.13 (wheels exist); 3.14 may need newer packages. |
| VS Code tasks fail to start bash | `.vscode/tasks.json` expects Git at `C:\Program Files\Git\bin\bash.exe`; edit that path if Git is installed elsewhere. |
| Gemini calls fail | The **AI stack** tab shows the last error. Check the key and model IDs in `.env`, then restart the backend. |
| Antivirus slows `npm install` | Exclude the project folder, or wait: the first install downloads about 150 MB. |
