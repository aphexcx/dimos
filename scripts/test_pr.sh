#!/usr/bin/env bash
set -euo pipefail

echo "== PR Test Script =="
echo "Repo: $(basename "$(git rev-parse --show-toplevel)")"
echo "Commit: $(git rev-parse --short HEAD)"
echo

ran_anything=0

# -------- Python (if present) --------
if [[ -f "pyproject.toml" || -f "requirements.txt" ]]; then
  ran_anything=1
  echo "== Python checks =="
  python -V
  python -m pip --version
  python -m pip install --upgrade pip

  if [[ -f "requirements.txt" ]]; then
    python -m pip install -r requirements.txt
  fi

  # If you have a dev requirements file, this is common:
  if [[ -f "requirements-dev.txt" ]]; then
    python -m pip install -r requirements-dev.txt
  fi

  # Require pytest if this is a Python repo
  if ! command -v pytest >/dev/null 2>&1; then
    echo "ERROR: pytest not installed. Add it to requirements-dev.txt (or project deps)."
    exit 1
  fi

  # Lint/format are optional, but if present, run them
  command -v ruff  >/dev/null 2>&1 && ruff check .
  command -v black >/dev/null 2>&1 && black --check .

  pytest -q
  echo
fi

# -------- Node (if present) --------
if [[ -f "package.json" ]]; then
  ran_anything=1
  echo "== Node checks =="
  npm ci
  npm test
  echo
fi

# -------- CMake/C++ (if present) --------
if [[ -f "CMakeLists.txt" ]]; then
  ran_anything=1
  echo "== CMake checks =="
  rm -rf build
  cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
  cmake --build build -j
  ctest --test-dir build --output-on-failure
  echo
fi

if [[ "$ran_anything" -eq 0 ]]; then
  echo "ERROR: No recognized project type detected (no pyproject.toml/requirements.txt/package.json/CMakeLists.txt)."
  echo "Add checks for your repo’s build/test commands."
  exit 1
fi

echo "✅ All PR checks passed."
