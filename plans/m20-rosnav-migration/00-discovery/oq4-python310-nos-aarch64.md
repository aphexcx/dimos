# OQ4: Python 3.10 on NOS aarch64 (RK3588)

**Status:** RESOLVED - Python 3.10 works via uv on NOS aarch64.

**Date:** 2026-03-13

## Environment

| Property | Value |
|----------|-------|
| OS | Ubuntu 20.04.6 LTS (Focal Fossa) |
| Kernel | Linux 5.10.198 aarch64 |
| Hardware | RK3588 SoC |
| glibc | 2.31 |
| System Python | 3.8.10 |
| RAM | 15GB total |
| Disk free | 9.1GB on / |

## Test Results

### uv installation
- `curl -LsSf https://astral.sh/uv/install.sh | sh` succeeds
- Installs uv 0.10.9 for aarch64-unknown-linux-gnu
- Binary at `/home/user/.local/bin/uv`

### Python 3.10 installation
- `uv python install 3.10` downloads cpython-3.10.20-linux-aarch64-gnu (28.8MB)
- Install completes in ~4.5s
- Binary at `/home/user/.local/share/uv/python/cpython-3.10-linux-aarch64-gnu/bin/python3.10`

### Virtual environment
- `uv venv --python 3.10` creates venv successfully
- Python reports: `3.10.20 (main, Mar 3 2026) [Clang 21.1.4]`
- Platform: `Linux-5.10.198-aarch64-with-glibc2.31`

### Package installation
- `uv pip install pydantic` installs pydantic 2.12.5 with native extensions (pydantic-core 2.41.5)
- Import and execution confirmed working

## Conclusion

No blockers for running dimos natively on NOS host with Python 3.10 via uv.
The uv-managed Python 3.10 standalone build is fully compatible with the NOS
Ubuntu 20.04 / glibc 2.31 / aarch64 environment.
