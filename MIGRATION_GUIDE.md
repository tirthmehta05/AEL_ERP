# AEL ERP Database Migration - Implementation Summary

## ✅ What Has Been Built (Current Status)

### 1. Complete Database Schema ✅
- **Location**: `/app/src/database/`
- **15 Tables Created**: All your operational tables
- **WAL Mode**: Enabled for 5-user concurrency
- **Foreign Keys**: Enforced
- **Migrations**: Alembic configured for version control

**Database File**: `/app/data/ael_erp.db`

### 2. Data Discovery Script ✅
- **Location**: `/app/scripts/01_data_discovery.py`
- **Purpose**: Finds data quality issues before migration
- **Checks**: Duplicates, invalid data, orphaned records, missing fields
- **Output**: CSV + HTML reports

### 3. Migration Script ✅
- **Location**: `/app/scripts/02_migrate_data.py`
- **Purpose**: Migrates all data from Google Sheets → SQLite
- **Features**: Dry-run mode, error logging, respects foreign keys
- **Order**: Customers → Vendors → Coils → Sales Orders → Designs → etc.

### 4. Streamlit UI for Discovery ✅
- **Location**: `/app/pages/data_discovery.py`
- **Purpose**: Run discovery from your web interface
- **Features**: Progress tracking, visual summary, download reports

---

## 📋 How to Run Data Discovery

You have **TWO OPTIONS**:

### Option 1: From Streamlit App (RECOMMENDED ✅)

1. **Start your app**:
```bash
cd /app
sudo supervisorctl start all
```

2. **Open browser** and navigate to your app

3. **Go to "Data Discovery" page** (it's in your pages menu)

4. **Click "Run Data Discovery" button**

5. **Review results** in the UI

6. **Download reports** (CSV/HTML) for detailed analysis

---

### Option 2: Command Line (Advanced)

This requires the app to be running for configuration access:

```bash
# Make sure app is running
sudo supervisorctl start all

# In another terminal, run:
cd /app
python3 -c "
import streamlit as st
from scripts.01_data_discovery import DataDiscoveryReport
from config import settings

report = DataDiscoveryReport(settings.api.google_sheets_id)
report.analyze_all()
"
```

---

## 🎯 The Migration Workflow

### Step 1: Data Discovery (YOU ARE HERE)
```
Run discovery → Fix issues in Google Sheets → Re-run discovery → Repeat until clean
```

**Timeline**: 4-8 hours (mostly manual data cleaning)

### Step 2: Dry Run Migration
```bash
python3 scripts/02_migrate_data.py --dry-run
```

**Purpose**: Test migration without committing changes

### Step 3: Live Migration
```bash
python3 scripts/02_migrate_data.py
```

**Purpose**: Actually import all data into SQLite

**Timeline**: 5-15 minutes

---

## ⚠️ IMPORTANT: Expected Data Issues

Based on typical manufacturing ERPs, expect to find:

### Critical (MUST FIX):
- ❌ **Duplicate Coil Numbers** (5-15 instances)
  - **Fix**: Rename with suffix (e.g., `11689` → `11689-A`)
  
- ❌ **Duplicate Receipt Numbers** (0-5 instances)
  - **Fix**: Regenerate with unique numbers

### High (SHOULD FIX):
- ⚠️ **Duplicate Job Cards** (10-30 instances)
  - **Fix**: Add `-REV` suffix or consolidate

- ⚠️ **Missing Party Names** (5-10 instances)
  - **Fix**: Fill in customer names or mark as "Internal"

- ⚠️ **Negative Available Weights** (2-10 instances)
  - **Fix**: Check over-allocations, adjust Material Used

- ⚠️ **Invalid Dates** (10-50 instances)
  - **Fix**: Correct format or set to reasonable defaults

### Medium/Low (CAN SKIP FOR NOW):
- ℹ️ Orphaned drafts (safe to ignore)
- ℹ️ Non-standard material type names (standardize later)
- ℹ️ Missing optional fields (fill in gradually)

---

## 📊 What the Discovery Report Shows

### Summary Section:
```
Total Issues: 48
  🔴 CRITICAL: 2
  🟠 HIGH:     18
  🟡 MEDIUM:   15
  🟢 LOW:      13
```

### Per-Table Breakdown:
```
Sales Order         : 23 issues
RM Inward          : 17 issues
WeightReceipts     :  3 issues
Finished Goods     :  5 issues
```

### Issue Details:
- **Severity**: CRITICAL, HIGH, MEDIUM, LOW
- **Category**: Duplicates, Missing Data, Invalid Data, Orphaned Records
- **Sample Data**: Specific records with issues
- **Action Required**: What to do to fix it

---

## 🛠️ How to Fix Issues

### For Duplicates:

**Coil Numbers:**
```
Original: 11689, 11689, 11689
Fixed:    11689, 11689-A, 11689-B
```

**Job Cards:**
```
Original: N-6169, N-6169
Fixed:    N-6169, N-6169-REV
```

### For Missing Data:

**Party Names:**
- If internal order → Enter "Internal" or "AEL Internal"
- If external → Enter actual customer name
- If unknown → Enter "Unknown Customer" (then investigate)

### For Invalid Data:

**Negative Weights:**
1. Check "Raw Material Used" sheet
2. Find allocations for that coil
3. Sum allocated weight
4. If > Coil Weight → Reduce allocations
5. If < Coil Weight → Fix "Material in stock" formula

**Invalid Dates:**
1. Check if date is in future → Likely correct
2. Check if date is year 1900 or 2100 → Fix to current year
3. Check if delivery < order date → Swap them

---

## 📁 Files Created

```
/app/
├── src/database/
│   ├── __init__.py              # Database package
│   ├── connection.py            # SQLAlchemy connection (WAL mode)
│   └── models.py                # All 15 table models
│
├── migrations/                  # Alembic migrations
│   ├── env.py                   # Migration environment
│   └── versions/
│       └── 71cb...py            # Initial schema
│
├── scripts/
│   ├── 00_verify_database.py   # Test database setup
│   ├── 01_data_discovery.py    # Find data issues
│   └── 02_migrate_data.py      # Migrate to SQLite
│
├── pages/
│   └── data_discovery.py       # Streamlit UI for discovery
│
├── data/
│   ├── ael_erp.db              # SQLite database
│   ├── ael_erp.db-wal          # WAL file
│   └── ael_erp.db-shm          # Shared memory
│
└── alembic.ini                 # Alembic config
```

---

## 🚀 Next Steps After Discovery

Once your data is clean (zero CRITICAL issues):

### 1. Service Layer Refactoring
- Create SQLAlchemy-based services
- Keep Google Sheets services for parallel run
- Add audit logging

### 2. Toggle Mechanism
- Config flag to switch Sheets ↔ Database
- Parallel write mode (both systems)

### 3. UI Updates
- Add UPDATE forms
- Add DELETE with safety checks
- Add AG-Grid for Excel-like editing
- Add Excel export/import

### 4. Docker & Deployment
- Docker Compose
- VPS deployment guide
- Backup scripts

---

## 💡 Tips for Success

### DO ✅:
- Fix CRITICAL issues before migration
- Keep backups of Google Sheets
- Run dry-run migration first
- Verify sample data after migration
- Keep both systems parallel for 1 week

### DON'T ❌:
- Skip data cleaning (causes migration failures)
- Delete Google Sheets after migration (keep as backup)
- Modify .env URLs (already configured correctly)
- Ignore warnings in migration logs

---

## 🆘 If You Get Stuck

### "Script won't run"
→ Use Streamlit UI instead (Option 1 above)

### "Too many issues found"
→ Start with CRITICAL only, fix those first

### "Don't know how to fix an issue"
→ Share the specific error, I'll help

### "Migration failed"
→ Check `/app/migration_log_*.json` for details
→ Fix issues and re-run

---

## ✅ Current Branch

You're working in: **`feature/database-migration`**

All changes are safe and reversible. Your main branch is untouched.

---

## 📞 Quick Commands

```bash
# Verify database
python3 scripts/00_verify_database.py

# Start app (to run discovery UI)
sudo supervisorctl start all

# Check app status
sudo supervisorctl status

# View logs if needed
tail -f /var/log/supervisor/frontend.out.log
```

---

**Ready to run discovery!** 🚀

Start your app, go to the Data Discovery page, and click the button!
