#!/usr/bin/env bash
set -euo pipefail

echo "== PR Test Script =="
echo "Repo: $(basename "$(git rev-parse --show-toplevel)")"
echo "Commit: $(git rev-parse --short HEAD)"
echo

# -------- Python (if present) --------
if [[ -f "pyproject.toml" || -f "requirements.txt" ]]; then
  echo "== Python checks =="
  python -V

  if [[ -f "requirements.txt" ]]; then
    python -m pip install -r requirements.txt
  fi

  # Lint/format (optional, only runs if tools exist)
  command -v ruff  >/dev/null 2>&1 && ruff check .
  command -v black >/dev/null 2>&1 && black --check .

  # Unit tests
  command -v pytest >/dev/null 2>&1 && pytest -q
  echo
fi

# -------- Node (if present) --------
if [[ -f "package.json" ]]; then
  echo "== Node checks =="
  npm ci
  npm test
  echo
fi

# -------- CMake/C++ (if present) --------
if [[ -f "CMakeLists.txt" ]]; then
  echo "== CMake checks =="
  rm -rf build
  cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
  cmake --build build -j
  ctest --test-dir build --output-on-failure
  echo
fi

echo "✅ All PR checks passed."
