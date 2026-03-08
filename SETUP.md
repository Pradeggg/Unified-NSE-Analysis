# Setup – Virtual environment and dependencies

## Virtual environment (already created)

The project uses a Python virtual environment at **`.venv`** (ignored by git).

### Activate the venv

**macOS / Linux (bash/zsh):**
```bash
source .venv/bin/activate
```

**Windows (Command Prompt):**
```cmd
.venv\Scripts\activate.bat
```

**Windows (PowerShell):**
```powershell
.venv\Scripts\Activate.ps1
```

After activation, your prompt will show `(.venv)` and `python`/`pip` will use the venv.

### Run without activating

You can run scripts with the venv’s Python directly:

```bash
.venv/bin/python working-sector/agent_cli.py --sector "Auto Components" --run-all
.venv/bin/python working-sector/web_search.py "Auto components India" --max-results 5
```

## Installed packages (from `requirements.txt`)

- **pandas**, **numpy** – data processing  
- **pandas-ta** – technical analysis  
- **openpyxl** – Excel export  
- **ollama** – agent (Ollama Granite4 + tool calling)  
- **duckduckgo-search** – web search (default engine)  

## Reinstall or add packages

With venv activated:
```bash
pip install -r requirements.txt
pip install <some-package>
```

Or without activating:
```bash
.venv/bin/pip install -r requirements.txt
```

## Optional

- **Ollama** – For the agent and iterative web search: install from [ollama.com](https://ollama.com), then `ollama pull granite4`.
- **Google/Bing search** – Optional: `pip install googlesearch-python` for Google; set `BING_SEARCH_KEY` for Bing.
