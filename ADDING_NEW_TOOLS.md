# Adding New Tools & Updating Existing Tools

**Quick Summary**: No, just placing the file is **NOT enough**. Follow these integration steps to add new tools or update existing ones seamlessly.

---

## 📋 Tool Requirements Checklist

All tools (new or existing) must have:

- ✅ `run()` function as entry point
- ✅ Importable as a module from `_pages/`
- ✅ No Windows-only dependencies (use `platform_utils` for cross-platform features)
- ✅ Error handling for all critical operations
- ✅ No direct `import streamlit as st` in critical initialization code

---

## 🆕 Adding a NEW Tool

### Step 1: Create the Tool File

Create a new file in `_pages/` directory:

```bash
_pages/my_new_tool.py
```

### Step 2: Implement the Tool with Required Structure

```python
"""
My New Tool - Brief description
Handles [feature] analysis and reporting
"""

import streamlit as st
import logging
from utils.error_handler import ErrorHandler

logger = logging.getLogger(__name__)


def run():
    """
    REQUIRED: Entry point for the Streamlit framework.
    This function is called by Home.py to load your tool.
    """
    st.set_page_config(
        page_title="My New Tool",
        page_icon="📊",
        layout="wide"
    )
    
    st.title("My New Tool")
    st.markdown("Tool description and usage guide")
    
    try:
        # Your tool logic here
        main()
    except Exception as e:
        logger.error(f"Tool error: {e}")
        st.error(f"An error occurred: {e}")


def main():
    """Main tool logic."""
    # Implementation here
    pass


if __name__ == "__main__":
    run()
```

### Step 3: Register the Tool in Home.py

Add your tool to the `TOOLS_METADATA` list in [Home.py](Home.py#L33):

```python
TOOLS_METADATA = [
    # ... existing tools ...
    ToolMetadata(
        title="My New Tool",                          # ✅ Display name in UI
        module_path="_pages.my_new_tool",             # ✅ Python import path
        accent_color="#FF5733",                       # ✅ Color for UI card
        description="Description of what it does",    # ✅ Shown in tool card
        button_label="Open My Tool",                  # ✅ Button text
        category="analysis",                          # ✅ Category (analysis/utilities/validation)
        dependencies=["pandas", "plotly"],            # ✅ Required packages
    ),
]
```

### Step 4: Install Dependencies (if needed)

Add new dependencies to `requirements.txt`:

```bash
pip install new-dependency-name
```

Then update the appropriate requirements file:
- **Windows**: `requirements-windows.txt`
- **Linux/macOS**: `requirements-unix.txt`
- **Core** (all platforms): `requirements.txt`

### Step 5: Test the Integration

1. **Verify import:**
   ```bash
   python -c "from _pages.my_new_tool import run; print('✅ Import successful')"
   ```

2. **Test within Streamlit:**
   - Reload `http://localhost:8501`
   - Your tool should appear in the dashboard
   - Click it to verify it loads without errors

---

## 🔄 Updating Existing Tools

### For Simple Updates (logic/UI changes)

1. **Edit the tool file** (e.g., `_pages/daily_data_analysis.py`)
2. **Save the file**
3. **Reload Streamlit** - Changes appear instantly (hot reload)

**No Home.py changes needed** ✅

### For Structural Changes (adding/removing `run()` function)

If you modify the `run()` function signature or move the entry point:

1. **Ensure `run()` function exists** - Framework calls `run()`, not `main()`
2. **Keep the function name `run()`** - Don't rename to `execute()` or other names
3. **Verify** - Import test should pass:
   ```bash
   python -c "from _pages.your_tool import run; print('✅ run() found')"
   ```

### For Dependency Changes

If the tool now requires new packages:

1. **Update `requirements.txt`** (if core dependency)
2. **Update `requirements-windows.txt`** or `requirements-unix.txt`** (if platform-specific)
3. **Run** `pip install -r requirements.txt`
4. **Restart Streamlit**

### For Cross-Platform Compatibility

If adding features that vary by OS:

**❌ DON'T DO THIS:**
```python
import pywin32  # Windows-only - crashes on Linux/Mac
import outlook   # Windows-only - not available on Linux/Mac
```

**✅ DO THIS INSTEAD:**
```python
from utils.platform_utils import PLATFORM_MANAGER, EMAIL_SERVICE

# Use platform detection
if PLATFORM_MANAGER.is_windows:
    # Windows-specific code
    pass
else:
    # Fallback for Linux/macOS
    pass

# Or use provided services
success, msg = EMAIL_SERVICE.send_email(to, subject, body)
```

---

## 📦 Tool Structure Best Practices

### Good Tool Structure
```python
"""Module docstring describing the tool."""

import streamlit as st
import logging
from utils.error_handler import ErrorHandler, ValidationResult
from utils.platform_utils import PLATFORM_MANAGER

logger = logging.getLogger(__name__)


def run():
    """Entry point - called by Home.py framework."""
    st.set_page_config(page_title="Tool Name", layout="wide")
    try:
        main()
    except Exception as e:
        logger.error(f"Error: {e}")
        st.error(f"Tool failed: {e}")


def main():
    """Main tool logic."""
    st.title("Tool Name")
    
    # Use error handling decorator
    @ErrorHandler.handle_errors("Tool Name", default=None, log_errors=True)
    def process_data():
        # Your logic
        pass
    
    process_data()


def helper_function():
    """Helper functions organized below main."""
    pass


if __name__ == "__main__":
    run()
```

### Common Issues & Fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| Tool doesn't appear in UI | Missing from TOOLS_METADATA | Add to Home.py TOOLS_METADATA list |
| "run() not found" error | Function named differently | Rename to `run()` |
| Import error on load | Missing dependency | Add to requirements file & install |
| Windows-only crash | Hard import of pywin32 | Use PLATFORM_MANAGER, EMAIL_SERVICE |
| Changes don't appear | Streamlit cache issue | Press R to reload page |

---

## 🔧 Framework Integration Details

### How Tool Loading Works

```
Home.py startup
    ↓
register_tools()
    ↓
For each TOOLS_METADATA:
    REGISTRY.register(module_path, metadata)
    ↓
User clicks tool button
    ↓
import_and_run_tool(metadata)
    ↓
importlib.import_module(module_path)  # ← Python import
    ↓
getattr(module, "run")                # ← Calls your run() function
    ↓
run()                                 # ← Your tool starts
```

### Tool Registry System

Your tool is automatically registered when Home.py finds it in TOOLS_METADATA. The registry tracks:

- **Tool ID**: `module_path` (e.g., `_pages.my_tool`)
- **Metadata**: Title, description, color, dependencies
- **Status**: AVAILABLE, UNAVAILABLE, ERROR

Check registration in code:
```python
from _pages import REGISTRY, ToolStatus

# Get all registered tools
tools = REGISTRY.get_all_tools()

# Check specific tool status
status = REGISTRY.get_status("_pages.my_tool")
```

---

## ✅ Integration Checklist for New Tools

- [ ] Created file in `_pages/` directory
- [ ] Implemented `run()` function as entry point
- [ ] Added to `TOOLS_METADATA` in [Home.py](Home.py#L33)
- [ ] Added import test: `python -c "from _pages.my_tool import run"`
- [ ] Added dependencies to requirements files
- [ ] Ran `pip install -r requirements.txt`
- [ ] Restarted Streamlit
- [ ] Tool appears in dashboard
- [ ] Tool loads without errors on click
- [ ] Tool uses `ERROR_HANDLER` for error handling
- [ ] Tool uses `PLATFORM_MANAGER` for cross-platform features (if needed)

---

## ✅ Integration Checklist for Updating Tools

**For logic/UI changes only:**
- [ ] Edited tool file (`_pages/tool_name.py`)
- [ ] Tested local functionality
- [ ] Reloaded Streamlit (press R)

**For structural changes:**
- [ ] `run()` function exists and is callable
- [ ] Import test passes: `python -c "from _pages.tool_name import run"`
- [ ] Restarted Streamlit

**For dependency changes:**
- [ ] Added to appropriate requirements file
- [ ] Ran `pip install -r requirements.txt`
- [ ] Verified import: `python -c "import package_name"`
- [ ] Restarted Streamlit

---

## 🚀 Quick Start: Add a Tool in 5 Minutes

### Example: Adding a "Data Export Tool"

**1. Create file** `_pages/data_export_tool.py`:
```python
"""Data Export Tool - Export analysis data in multiple formats."""

import streamlit as st
import logging

logger = logging.getLogger(__name__)


def run():
    """Entry point for the tool."""
    st.set_page_config(page_title="Data Export", layout="wide")
    st.title("📥 Data Export Tool")
    st.markdown("Export your analysis results as CSV, Excel, or JSON")
    
    uploaded_file = st.file_uploader("Upload data file")
    format_choice = st.selectbox("Export format", ["CSV", "Excel", "JSON"])
    
    if uploaded_file and st.button("Export"):
        st.success(f"Exported as {format_choice}!")


if __name__ == "__main__":
    run()
```

**2. Add to Home.py** TOOLS_METADATA:
```python
ToolMetadata(
    title="Data Export",
    module_path="_pages.data_export_tool",
    accent_color="#FF9800",
    description="Export analysis results in multiple formats",
    button_label="Open Export Tool",
    category="utilities",
    dependencies=[],
),
```

**3. Test:**
```bash
python -c "from _pages.data_export_tool import run; print('✅ Ready')"
```

**4. Reload Streamlit** - Done! ✅

---

## 📞 Troubleshooting

### Tool doesn't appear
```bash
# Check Home.py registration
grep "data_export_tool" Home.py

# Check import
python -c "from _pages.data_export_tool import run"
```

### Tool appears but won't load
```bash
# Check for errors
streamlit run Home.py  # Look at console output
# Common: missing run() function or import error
```

### Changes don't show up
```bash
# Option 1: Reload page (press R)
# Option 2: Restart Streamlit server
# Option 3: Clear cache (Ctrl+Shift+C in Streamlit)
```

### Cross-platform issues
```bash
# Test on target platform
# Windows: test with requirements-windows.txt
# Linux: test with requirements-unix.txt
# Use PLATFORM_MANAGER for conditional code
```

---

## 📚 Reference

- **Framework**: [_pages/__init__.py](_pages/__init__.py) - Registry and framework
- **Dependencies**: [utils/dependencies.py](utils/dependencies.py) - Validation system
- **Platform Utils**: [utils/platform_utils.py](utils/platform_utils.py) - Cross-platform features
- **Error Handler**: [utils/error_handler.py](utils/error_handler.py) - Error handling
- **Main Dashboard**: [Home.py](Home.py) - Tool registration and routing

---

## Summary

| Task | Steps | Time |
|------|-------|------|
| Add new tool | Create file + Add to metadata + Test | 5 min |
| Update tool logic | Edit file + Reload | 1 min |
| Add dependency | Update requirements + Install | 2 min |
| Cross-platform feature | Use PLATFORM_MANAGER | 3 min |

**Key Rule**: Every tool needs a `run()` function and registration in TOOLS_METADATA. Everything else follows naturally! ✨
