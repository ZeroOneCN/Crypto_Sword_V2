#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "==========================================="
echo " CryptoPilot — 全市场多因子雷达交易系统"
echo "==========================================="
echo ""

# Python check
PYTHON=""
for py in python3 python; do
    if command -v "$py" &>/dev/null; then
        PYTHON="$py"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "[ERROR] Python 3.10+ 未安装"
    exit 1
fi

echo "Python: $($PYTHON --version)"

# .env check
if [ ! -f ".env" ]; then
    echo "[ERROR] .env 文件不存在"
    echo "cp .env.example .env && 编辑填入密钥"
    exit 1
fi

# Setup
mkdir -p data/logs
$PYTHON -m pip install -r requirements.txt --quiet 2>&1

echo ""
echo "启动 CryptoPilot..."
exec $PYTHON -m cryptopilot.main "$@"
