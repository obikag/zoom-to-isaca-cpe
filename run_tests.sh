#!/bin/bash
set -e

echo "=== isort ==="
isort zoom_cpe.py tests/

echo "=== black ==="
black zoom_cpe.py tests/

echo "=== pytest + coverage ==="
pytest tests/ -v --cov=zoom_cpe --cov-report=term-missing
