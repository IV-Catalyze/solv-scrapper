# Quick Start Guide

## Setup & Run Checklist

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. (Optional) Set Environment Variables
Create a `.env` file if you need database connection:
```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=solvhealth_patients
DB_USER=postgres
DB_PASSWORD=your_password
USE_DATABASE=true
```

### 3. Run the API
```bash
uvicorn app.api.routes:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Access the API
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Alternative Docs**: http://localhost:8000/redoc

---

## Alternative: Run API + Monitor Together
```bash
python run_all.py
```

---

## Notes
- If `USE_DATABASE=false`, the API runs without a database
- The `--reload` flag enables auto-reload during development
- Default port is 8000 (change with `--port` or `API_PORT` env var)

