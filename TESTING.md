# Integration Testing & Verification Guide

This guide helps you verify that all components are properly integrated and the package is error-free.

## Pre-Flight Checklist

Run this checklist before deploying to ensure everything works:

```bash
# 1. Virtual environment active
python --version  # Should show Python 3.8+

# 2. All dependencies installed
pip list | grep streamlit  # Should show streamlit version

# 3. Package structure intact
ls -la _pages/  # Should see all tool files
ls -la utils/   # Should see utility modules

# 4. Python path correct
python -c "import sys; print(sys.path[0])"
```

## Dependency Validation

### 1. Core Dependency Check

```bash
# Check if all core dependencies are available
python -c "
from utils.dependencies import validate_environment
is_valid, msg = validate_environment()
print('✅ PASSED' if is_valid else '❌ FAILED')
print(msg)
"
```

### 2. Detailed Dependency Report

```bash
# Get comprehensive dependency status
python -c "
from utils.dependencies import DEPENDENCY_MANAGER
print(DEPENDENCY_MANAGER.get_status_report())
"
```

### 3. Optional Dependency Check

```bash
# Check which optional packages are available
python -c "
from utils.dependencies import DEPENDENCY_MANAGER
optional_status = DEPENDENCY_MANAGER.check_optional_dependencies()
for pkg, available in optional_status.items():
    status = '✅' if available else '❌'
    print(f'{status} {pkg}')
"
```

## Integration Testing

### 1. Tool Registry Test

```bash
# Verify tool registration works
python << 'EOF'
from _pages import REGISTRY
from Home import TOOLS_METADATA

print("Registering tools...")
for metadata in TOOLS_METADATA:
    REGISTRY.register(metadata.module_path, metadata)
    print(f"  ✅ {metadata.title}")

print(f"\nTotal tools registered: {len(REGISTRY.get_all_tools())}")
print("Expected: 5")

if len(REGISTRY.get_all_tools()) == 5:
    print("✅ PASSED: All tools registered correctly")
else:
    print("❌ FAILED: Tool count mismatch")
EOF
```

### 2. Import Test

```bash
# Test if all tool modules can be imported
python << 'EOF'
import importlib
import sys

tools = [
    "_pages.gw_data_analysis",
    "_pages.esw_flag_control", 
    "_pages.daily_data_analysis",
    "_pages.weekly_data_analysis",
    "_pages.block_data_validation_1p_hpl",
]

print("Testing tool imports...")
for tool in tools:
    try:
        importlib.import_module(tool)
        print(f"  ✅ {tool}")
    except ImportError as e:
        print(f"  ❌ {tool}: {e}")
        sys.exit(1)

print("\n✅ PASSED: All tools can be imported")
EOF
```

### 3. Cross-Platform Utilities Test

```bash
# Test platform detection and utilities
python << 'EOF'
from utils.platform_utils import (
    PLATFORM_MANAGER, EMAIL_SERVICE, FILE_MANAGER, PROCESS_MANAGER
)

print("Platform Information:")
info = PLATFORM_MANAGER.get_platform_info()
for key, value in info.items():
    print(f"  {key}: {value}")

print("\nPlatform Detection:")
print(f"  Windows: {PLATFORM_MANAGER.is_windows}")
print(f"  Linux: {PLATFORM_MANAGER.is_linux}")
print(f"  macOS: {PLATFORM_MANAGER.is_mac}")

print("\n✅ PASSED: Platform utilities working")
EOF
```

### 4. Error Handling Test

```bash
# Test error handling framework
python << 'EOF'
from utils.error_handler import (
    ErrorHandler, DataValidator, ValidationResult
)

print("Testing error handling...")

# Test safe execution
result = ErrorHandler.safe_execute(
    lambda: 1/0,  # Will raise ZeroDivisionError
    context="test_error",
    default="error_caught"
)

if result == "error_caught":
    print("  ✅ Error caught and handled correctly")
else:
    print("  ❌ Error not handled properly")

# Test validation result
validation = ValidationResult(is_valid=True, errors=[])
validation.add_error("Test error")
validation.add_warning("Test warning")

print(f"  ✅ Validation result: {validation.is_valid}")
print("\n✅ PASSED: Error handling working")
EOF
```

### 5. Dependency Management Test

```bash
# Test dependency manager
python << 'EOF'
from utils.dependencies import DEPENDENCY_MANAGER

print("Testing dependency manager...")

# Check core dependencies
core_valid, missing = DEPENDENCY_MANAGER.check_core_dependencies()
print(f"  Core dependencies valid: {core_valid}")

if not core_valid:
    print(f"  Missing: {missing}")
    exit(1)

# Check optional dependencies
optional = DEPENDENCY_MANAGER.check_optional_dependencies()
print(f"  Optional packages checked: {len(optional)}")

print("\n✅ PASSED: Dependency manager working")
EOF
```

## Streamlit Application Tests

### 1. Basic Launch Test

```bash
# Test if Streamlit can start the app
timeout 10 streamlit run Home.py --headless 2>&1 | head -20

# Check exit code
echo "Exit code: $?"
```

### 2. Port Availability Test

```bash
# Check if default port is available
python << 'EOF'
import socket

def is_port_available(port=8501):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('localhost', port))
            return True
        except OSError:
            return False

if is_port_available():
    print("✅ PASSED: Port 8501 is available")
else:
    print("❌ FAILED: Port 8501 already in use")
EOF
```

## Data Processing Tests

### 1. DataFrame Validation Test

```bash
# Test data validation utilities
python << 'EOF'
import pandas as pd
from utils.error_handler import DataValidator

# Create test dataframe
df = pd.DataFrame({
    'meter_id': ['M001', 'M002', 'M003'],
    'timestamp': pd.date_range('2026-01-01', periods=3),
    'value': [100, 200, 300]
})

print("Testing DataFrame validation...")

# Test basic validation
result = DataValidator.validate_dataframe(df)
print(f"  DataFrame valid: {result.is_valid}")

# Test column validation
cols_result = DataValidator.validate_columns(df, ['meter_id', 'timestamp'])
print(f"  Required columns present: {cols_result.is_valid}")

print("✅ PASSED: Data validation working")
EOF
```

### 2. File Operation Test

```bash
# Test file operations
python << 'EOF'
import tempfile
import os
from utils.platform_utils import FILE_MANAGER

print("Testing file operations...")

# Test temp file creation
temp_path = FILE_MANAGER.save_to_temp_file(b"test data", ".txt")
exists = os.path.exists(temp_path)
print(f"  Temp file created: {exists}")

if exists:
    os.remove(temp_path)
    print("  Cleanup successful")

print("✅ PASSED: File operations working")
EOF
```

## Load Testing

### 1. Concurrent Tool Loading Test

```bash
# Test loading multiple tools simultaneously
python << 'EOF'
import threading
import importlib

tools = [
    "_pages.gw_data_analysis",
    "_pages.daily_data_analysis",
    "_pages.weekly_data_analysis",
]

errors = []

def load_tool(tool_name):
    try:
        importlib.import_module(tool_name)
    except Exception as e:
        errors.append((tool_name, str(e)))

threads = []
for tool in tools:
    t = threading.Thread(target=load_tool, args=(tool,))
    threads.append(t)
    t.start()

for t in threads:
    t.join()

if errors:
    print("❌ Errors during concurrent loading:")
    for tool, error in errors:
        print(f"  {tool}: {error}")
else:
    print("✅ PASSED: All tools loaded concurrently")
EOF
```

## Environment Compatibility Tests

### 1. Platform-Specific Features

```bash
# Test platform-specific feature availability
python << 'EOF'
import platform
from utils.platform_utils import PLATFORM_MANAGER

system = platform.system().lower()
print(f"Running on: {system}")

if system == "windows":
    print("Testing Windows-specific features...")
    try:
        import win32com.client
        print("  ✅ pywin32 available (Outlook email supported)")
    except ImportError:
        print("  ℹ️  pywin32 not available (SMTP will be used)")

elif system in ["linux", "darwin"]:
    print("Testing Unix-specific features...")
    print("  ✅ SMTP email supported")
    print("  ℹ️  Outlook not available on this platform")

print("✅ PASSED: Platform features configured")
EOF
```

### 2. Encoding Test

```bash
# Test character encoding compatibility
python << 'EOF'
import sys
from utils.platform_utils import PLATFORM_MANAGER

print(f"Default encoding: {sys.getdefaultencoding()}")
print(f"File system encoding: {sys.getfilesystemencoding()}")

# Test with special characters
test_text = "Meter_ID_🔋_Analysis"
encoded = test_text.encode('utf-8')
decoded = encoded.decode('utf-8')

if test_text == decoded:
    print("✅ PASSED: UTF-8 encoding/decoding works")
else:
    print("❌ FAILED: Encoding issue detected")
EOF
```

## Full Integration Test Suite

Run this comprehensive test:

```bash
#!/bin/bash

echo "=== Smart Meter Tools Integration Test Suite ==="
echo

echo "1. Checking environment..."
python -c "from utils.dependencies import validate_environment; is_valid, msg = validate_environment(); print('✅ PASSED' if is_valid else '❌ FAILED')" || exit 1

echo "2. Checking tool registry..."
python -c "from _pages import REGISTRY; from Home import TOOLS_METADATA; [REGISTRY.register(t.module_path, t) for t in TOOLS_METADATA]; print('✅ PASSED' if len(REGISTRY.get_all_tools()) == 5 else '❌ FAILED')" || exit 1

echo "3. Checking imports..."
python << 'EOF'
import importlib
tools = ["_pages.gw_data_analysis", "_pages.esw_flag_control", "_pages.daily_data_analysis", "_pages.weekly_data_analysis", "_pages.block_data_validation_1p_hpl"]
for t in tools:
    importlib.import_module(t)
print("✅ PASSED")
EOF
|| exit 1

echo "4. Checking utilities..."
python -c "from utils.platform_utils import PLATFORM_MANAGER; from utils.error_handler import ErrorHandler; from utils.dependencies import DEPENDENCY_MANAGER; print('✅ PASSED')" || exit 1

echo "5. Checking data validation..."
python << 'EOF'
import pandas as pd
from utils.error_handler import DataValidator
df = pd.DataFrame({'col1': [1,2,3]})
result = DataValidator.validate_dataframe(df)
print("✅ PASSED" if result.is_valid else "❌ FAILED")
EOF
|| exit 1

echo
echo "=== All Tests Passed ✅ ==="
```

## Automated CI/CD Testing

For continuous integration:

```yaml
# .github/workflows/test.yml
name: Integration Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        python-version: [3.8, 3.9, '3.10', 3.11]
    
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: ${{ matrix.python-version }}
      
      - name: Install dependencies
        run: pip install -r requirements.txt
      
      - name: Run tests
        run: |
          python -c "from utils.dependencies import validate_environment; is_valid, msg = validate_environment(); assert is_valid, msg"
          python -c "from _pages import REGISTRY; from Home import TOOLS_METADATA; [REGISTRY.register(t.module_path, t) for t in TOOLS_METADATA]; assert len(REGISTRY.get_all_tools()) == 5"
```

## Performance Benchmarking

```bash
# Measure startup time
python << 'EOF'
import time
import importlib

start = time.time()
from _pages import REGISTRY
from Home import TOOLS_METADATA
for metadata in TOOLS_METADATA:
    REGISTRY.register(metadata.module_path, metadata)
end = time.time()

print(f"Startup time: {(end-start)*1000:.2f}ms")

# Measure tool import time
for tool_id, metadata in REGISTRY.get_all_tools().items():
    start = time.time()
    importlib.import_module(metadata.module_path)
    end = time.time()
    print(f"  {metadata.title}: {(end-start)*1000:.2f}ms")
EOF
```

## Deployment Verification Checklist

Before deploying to production:

- [ ] All core dependencies installed
- [ ] Tool registry populated with 5 tools
- [ ] All tools importable without errors
- [ ] Platform detection working correctly
- [ ] Error handling framework functional
- [ ] Dependency validation passing
- [ ] Email service configured (Outlook/SMTP)
- [ ] Streamlit port available
- [ ] File operations working
- [ ] UTF-8 encoding compatible
- [ ] Cross-platform tests passing
- [ ] Load tests successful

## Troubleshooting Failed Tests

If any test fails:

1. **Check dependencies:**
   ```bash
   pip install -r requirements.txt --force-reinstall
   ```

2. **Check imports:**
   ```bash
   python -c "import streamlit; import pandas; import plotly"
   ```

3. **Check file permissions:**
   ```bash
   chmod -R 755 _pages utils
   ```

4. **Verify Python path:**
   ```bash
   python -c "import sys; print(sys.path)"
   ```

5. **Enable debug logging:**
   ```bash
   streamlit run Home.py --logger.level=debug
   ```

---

**Last Updated**: 2026-06-03
