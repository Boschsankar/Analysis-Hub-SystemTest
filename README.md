# Smart Meter Analysis Hub

A Streamlit dashboard hub for smart-meter operations and analysis workflows. The home page provides a stakeholder-friendly tool workspace with status cards, launch controls, and a single active tool view to keep navigation stable.

## Tools

- **GW Data Analysis**: Gateway SoC, supply-source, phase, and latitude/longitude insights.
- **ESW Flag Control**: Inspect and modify critical ESW binary payload bits.
- **Daily Data Analysis**: Review daily smart-meter status and data quality.
- **Weekly Data Analysis**: Summarize weekly SLA trends, gaps, and report health.

## Project Structure

```text
Home.py
requirements.txt
utils/
  common.py
_pages/
  __init__.py
  gw_data_analysis.py
  esw_flag_control.py
  daily_data_analysis.py
  weekly_data_analysis.py
```

## Setup

Create and activate a Python environment, then install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Run

```powershell
python -m streamlit run Home.py
```

Open the app at:

```text
http://localhost:8501
```

## Dependency Check

Before pushing or deploying, run:

```powershell
python -m pip check
python -m py_compile Home.py _pages\gw_data_analysis.py _pages\daily_data_analysis.py _pages\weekly_data_analysis.py _pages\esw_flag_control.py utils\common.py
```

## Notes

- Outlook email features require Windows with Outlook configured locally.
- Excel upload/export support uses `openpyxl`.
- Generated files such as `__pycache__`, `.pyc`, logs, local env files, and backup files are excluded through `.gitignore`.

## Git Push Checklist

```powershell
git status
git add .
git commit -m "Enhance Smart Meter analysis hub"
git push
```

If this folder is not yet a Git repository, initialize and attach a remote first:

```powershell
git init
git branch -M main
git remote add origin <your-repo-url>
```
