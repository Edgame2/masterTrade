#!/bin/bash
# MasterTrade System Cleanup Script
# Removes redundant documentation and keeps essential files

echo "================================"
echo "MasterTrade System Cleanup"
echo "================================"
echo ""

# Backup directory
BACKUP_DIR="./documentation_archive"
mkdir -p "$BACKUP_DIR"

echo "Step 1: Archiving redundant documentation files..."
echo ""

# Redundant files to archive (keeping in system but moving to archive)
REDUNDANT_DOCS=(
    "PROBLEM_FIXED.md"
    "QUICK_STATUS.md"
    "INTEGRATION_ANALYSIS.md"
    "TASK_11_COMPLETION_SUMMARY.md"
    "TASK_12_COMPLETION_SUMMARY.md"
    "SYSTEM_TEST_REPORT.md"
    "DAILY_STRATEGY_REVIEW_COMPLETE.md"  # Duplicate of DAILY_STRATEGY_REVIEW_SYSTEM.md
)

for file in "${REDUNDANT_DOCS[@]}"; do
    if [ -f "$file" ]; then
        echo "  Archiving: $file"
        mv "$file" "$BACKUP_DIR/"
    fi
done

echo ""
echo "Step 2: Cleaning up .pyc files and __pycache__ directories..."
find . -type d -name "__pycache__" ! -path "*/venv/*" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" ! -path "*/venv/*" -delete 2>/dev/null
echo "  ✓ Cleaned Python cache files"

echo ""
echo "Step 3: Removing temporary files..."
find . -type f -name "*.tmp" ! -path "*/venv/*" -delete 2>/dev/null
find . -type f -name "*.swp" ! -path "*/venv/*" -delete 2>/dev/null
find . -type f -name "*.swo" ! -path "*/venv/*" -delete 2>/dev/null
echo "  ✓ Cleaned temporary files"

echo ""
echo "Step 4: Cleaning old log files..."
find . -type f -name "*.log.*" -delete 2>/dev/null
find . -type f -name "*.log.1" -delete 2>/dev/null
find . -type f -name "*.log.2" -delete 2>/dev/null
echo "  ✓ Cleaned old log files"

echo ""
echo "================================"
echo "Cleanup Complete"
echo "================================"
echo ""
echo "Archived files location: $BACKUP_DIR"
echo ""
echo "Essential documentation kept:"
echo "  - README.md (main documentation)"
echo "  - SYSTEM_CAPABILITIES.md (feature overview)"
echo "  - SYSTEM_MANAGEMENT.md (operations guide)"
echo "  - All feature-specific documentation"
echo ""
echo "Run './status.sh' to verify system status"
echo ""
