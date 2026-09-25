# Hareruya Spyglass

This version tightens card matching so a search for `Tithe` only accepts listings whose card-name portion is exactly `Tithe`, including bilingual `税収/Tithe`. It therefore rejects `Blood Tithe` and `Smothering Tithe`. Listings containing `Art Card` are ignored.

## Run locally

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
uvicorn app.main:app --reload
```

Windows PowerShell:
```powershell
py -3.11 -m venv .venv
.venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000
