# Installation & Setup Guide

## Quick Start (5 minutes)

### Step 1: Verify Python Installation
```bash
python --version  # Should be 3.8+
pip --version
```

### Step 2: Clone/Download the Package
```bash
cd /path/to/SmartMeter/Automation_Integration
```

### Step 3: Setup Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/macOS
python3 -m venv venv
source venv/bin/activate
```

### Step 4: Install Dependencies

**Windows:**
```bash.
pip install -r requirements-windows.txt
```

**Linux/macOS:**
```bash
pip install -r requirements-unix.txt
```

**Any System (Core Only):**
```bash
pip install -r requirements.txt
```

### Step 5: Verify Installation
```bash
python -c "from utils.dependencies import validate_environment; print(validate_environment())"
```

### Step 6: Run the Application
```bash
streamlit run Home.py
```

The application will open at: `http://localhost:8501`

---

## Detailed Installation

### System Requirements

| Component | Requirement |
|-----------|-------------|
| Python | 3.8, 3.9, 3.10, or 3.11 |
| RAM | Minimum 2GB, Recommended 4GB+ |
| Disk Space | ~500MB (with all dependencies) |
| OS | Windows, Linux, or macOS |

### Step-by-Step Installation

#### 1. Install Python

**Windows:**
- Download from [python.org](https://www.python.org)
- Run installer, check "Add Python to PATH"
- Verify: `python --version`

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv
```

**macOS:**
```bash
brew install python3
```

#### 2. Create Project Directory
```bash
mkdir smartmeter-tools
cd smartmeter-tools
```

#### 3. Clone or Copy Package
```bash
# If using git
git clone <repository> .

# Or copy files manually
```

#### 4. Create Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/macOS
python3 -m venv venv
source venv/bin/activate
```

#### 5. Upgrade pip
```bash
python -m pip install --upgrade pip
```

#### 6. Install Package Dependencies

**Option A: Using requirements.txt (Recommended)**
```bash
# Core dependencies (all platforms)
pip install -r requirements.txt

# Plus platform-specific (optional)
# Windows
pip install -r requirements-windows.txt

# Or
# Linux/macOS  
pip install -r requirements-unix.txt
```

**Option B: Using setup.py**
```bash
# Development installation (editable)
pip install -e .

# With extras
pip install -e ".[windows]"   # Windows support
pip install -e ".[dev]"       # Development tools
```

**Option C: Manual Installation**
```bash
pip install streamlit>=1.40.0
pip install pandas>=2.0.0
pip install numpy>=1.24.0
pip install plotly>=5.0.0
pip install altair>=5.0.0
pip install matplotlib>=3.6.0
pip install seaborn>=0.12.0
pip install openpyxl>=3.8.0
```

#### 7. Verify Installation
```bash
# Check dependency status
python -c "from utils.dependencies import DEPENDENCY_MANAGER; print(DEPENDENCY_MANAGER.get_status_report())"

# Verify imports
python -c "import streamlit; import pandas; import plotly; print('✅ All core dependencies installed')"
```

#### 8. Launch Application
```bash
streamlit run Home.py
```

---

## Troubleshooting Installation

### Python Not Found
```bash
# Windows: Make sure Python is in PATH
# Reinstall with "Add Python to PATH" checked

# Linux/macOS: Use python3 explicitly
python3 -m venv venv
source venv/bin/activate
python3 -m pip install -r requirements.txt
```

### Permission Denied (Linux/macOS)
```bash
# Fix permissions
chmod +x venv/bin/activate
```

### Module Not Found After Installation
```bash
# Ensure virtual environment is activated
# Windows
venv\Scripts\activate

# Linux/macOS
source venv/bin/activate

# Reinstall packages
pip install -r requirements.txt --force-reinstall
```

### Pip Installation Fails
```bash
# Upgrade pip first
python -m pip install --upgrade pip

# Try installing with no-cache
pip install -r requirements.txt --no-cache-dir

# Check internet connection
ping google.com
```

### Streamlit Port Already in Use
```bash
# Use a different port
streamlit run Home.py --server.port 8502

# Or kill the existing process
# Windows
netstat -ano | findstr :8501
taskkill /PID <PID> /F

# Linux/macOS
lsof -i :8501
kill <PID>
```

---

## Specific Dependency Setup

### Windows Outlook Support

If you want to use Outlook email functionality on Windows:

```bash
# Install pywin32
pip install pywin32>=311

# Additional setup (one-time)
python -m pip install --upgrade pywin32
python Scripts/pywin32_postinstall.py -install

# Verify
python -c "import win32com; print('✅ Outlook support installed')"
```

### Optional Visualization Libraries

For enhanced charts and graphs:

```bash
# Already included in requirements.txt but verify
pip install plotly>=5.0.0
pip install altair>=5.0.0
pip install matplotlib>=3.6.0
pip install seaborn>=0.12.0
```

### Development Tools (Optional)

For development and testing:

```bash
pip install -r requirements-dev.txt

# Or individually
pip install pytest>=7.0.0
pip install black>=23.0.0
pip install flake8>=6.0.0
pip install mypy>=1.0.0
```

---

## Running on Different Systems

### Windows with PowerShell
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements-windows.txt
streamlit run Home.py
```

### Windows with Command Prompt
```cmd
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements-windows.txt
streamlit run Home.py
```

### Linux/macOS
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-unix.txt
streamlit run Home.py
```

### Docker (All Platforms)
```dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
EXPOSE 8501
CMD ["streamlit", "run", "Home.py"]
```

Build and run:
```bash
docker build -t smartmeter .
docker run -p 8501:8501 smartmeter
```

---

## Post-Installation

### First Launch

1. Navigate to `http://localhost:8501`
2. Check system information panel
3. Verify all tools are available
4. Review dependency status report

### Configuration

1. **Streamlit Config**: Edit `.streamlit/config.toml`
2. **Logging**: Configure in `Home.py` or Python logging config
3. **Environment Variables**: Set as needed for your environment

### Troubleshooting First Launch

If you see dependency warnings:
```bash
# Install missing packages
pip install -r requirements.txt --force-reinstall

# Restart streamlit
streamlit run Home.py --logger.level=debug
```

---

## Sharing the Package

### Package for Distribution

```bash
# Create distribution
python setup.py sdist bdist_wheel

# Share the wheel
# smartmeter_analysis_tools-1.0.0-py3-none-any.whl

# Install on another machine
pip install smartmeter_analysis_tools-1.0.0-py3-none-any.whl
```

### Including in Requirements

Add to another project's `requirements.txt`:
```
smartmeter-analysis-tools==1.0.0
# Or local path
-e /path/to/smartmeter-analysis-tools
```

---

## Uninstallation

### Remove Virtual Environment
```bash
# Windows
rmdir /s venv

# Linux/macOS
rm -rf venv
```

### Remove Package
```bash
pip uninstall smartmeter-analysis-tools
```

---

## Getting Help

1. **Check logs**:
   ```bash
   streamlit run Home.py --logger.level=debug 2>&1 | tee debug.log
   ```

2. **Verify environment**:
   ```bash
   python -c "from utils.dependencies import DEPENDENCY_MANAGER; print(DEPENDENCY_MANAGER.get_status_report())"
   ```

3. **System info**:
   ```bash
   python --version
   pip list
   uname -a  # Linux/macOS
   systeminfo  # Windows
   ```

4. **Contact support** with debug information from above

---

**Last Updated**: 2026-06-03
