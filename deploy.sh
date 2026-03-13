#!/usr/bin/env bash
#
# deploy.sh — M20 ROSNav deployment script for NOS host
#
# Architecture: dimos runs natively on the NOS host (Python 3.10 venv),
# while the CMU nav stack (FASTLIO2, FAR planner, base_autonomy) runs
# inside a ROS2 Humble Docker container managed by DockerModule.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ----- Paths -----
VENV_DIR="/opt/dimos/venv"
DIMOS_SRC="${SCRIPT_DIR}"
NAV_IMAGE="dimos_autonomy_stack:humble"
DRDDS_BUILDER_NAME="dimos-drdds-builder"

# ----- Colours -----
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[deploy]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[deploy]${NC} $*"; }
log_error() { echo -e "${RED}[deploy]${NC} $*" >&2; }

# =====================================================================
# setup — one-time NOS host provisioning
# =====================================================================
cmd_setup() {
    log_info "=== NOS Host Provisioning ==="

    setup_install_uv
    setup_create_venv
    setup_install_dimos
    setup_install_drdds

    echo ""
    log_info "=== Setup complete ==="
    log_info "Python : ${VENV_DIR}/bin/python3"
    log_info "Activate: source ${VENV_DIR}/bin/activate"
}

# ----- Step 1: install uv -----
setup_install_uv() {
    if command -v uv &>/dev/null; then
        log_info "uv already installed ($(uv --version))"
        return
    fi
    log_info "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="${HOME}/.local/bin:${PATH}"
    log_info "uv installed ($(uv --version))"
}

# ----- Step 2: create Python 3.10 venv at /opt/dimos/venv -----
setup_create_venv() {
    if [ -d "${VENV_DIR}" ] && [ -x "${VENV_DIR}/bin/python3" ]; then
        local py_ver
        py_ver=$("${VENV_DIR}/bin/python3" --version 2>&1 | awk '{print $2}')
        if [[ "${py_ver}" == 3.10.* ]]; then
            log_info "Python 3.10 venv already exists at ${VENV_DIR} (${py_ver})"
            return
        fi
        log_warn "Existing venv has Python ${py_ver} — recreating with 3.10"
        sudo rm -rf "${VENV_DIR}"
    fi

    log_info "Creating Python 3.10 venv at ${VENV_DIR}..."
    sudo mkdir -p "$(dirname "${VENV_DIR}")"
    sudo uv venv --python 3.10 "${VENV_DIR}"
    sudo chown -R "$(id -u):$(id -g)" "${VENV_DIR}"
    log_info "Venv created ($("${VENV_DIR}/bin/python3" --version))"
}

# ----- Step 3: install dimos into the venv -----
setup_install_dimos() {
    log_info "Installing dimos into ${VENV_DIR}..."
    "${VENV_DIR}/bin/pip" install --upgrade pip
    "${VENV_DIR}/bin/pip" install -e "${DIMOS_SRC}"
    log_info "dimos installed"
}

# ----- Step 4: build drdds inside nav container, copy to host venv -----
setup_install_drdds() {
    log_info "Installing drdds bindings..."

    # Ensure the nav container image exists
    if ! docker image inspect "${NAV_IMAGE}" &>/dev/null; then
        log_error "Nav container image '${NAV_IMAGE}' not found."
        log_error "Build it first:  cd docker/navigation && ./build.sh"
        return 1
    fi

    # Clean up any previous builder container
    docker rm -f "${DRDDS_BUILDER_NAME}" &>/dev/null || true

    # Run a temporary container to build drdds.
    # Inside the container we have ROS2 Humble — the only environment where
    # drdds can be compiled (it links against Humble-native libraries).
    log_info "Building drdds inside nav container..."
    docker run --name "${DRDDS_BUILDER_NAME}" \
        "${NAV_IMAGE}" \
        bash -c '
set -e
source /opt/ros/humble/setup.bash
source /ros2_ws/install/setup.bash
source /opt/dimos-venv/bin/activate

# Destination for artifacts we will copy to the host
mkdir -p /tmp/drdds_out

# Strategy 1: pip-installable drdds package in the repo
if [ -f /workspace/dimos/drdds/setup.py ] || [ -f /workspace/dimos/drdds/pyproject.toml ]; then
    pip install --target /tmp/drdds_out /workspace/dimos/drdds
# Strategy 2: drdds built as part of the colcon workspace
elif python3 -c "import drdds" 2>/dev/null; then
    DRDDS_LOC=$(python3 -c "import drdds, os; print(os.path.dirname(drdds.__file__))")
    cp -r "${DRDDS_LOC}" /tmp/drdds_out/
# Strategy 3: drdds available via pip inside the container
elif pip install --target /tmp/drdds_out drdds 2>/dev/null; then
    true
else
    echo "WARNING: drdds package not found — skipping"
    exit 0
fi

echo "DRDDS_READY"
'

    # Check if the build produced artifacts
    local build_output
    build_output=$(docker logs "${DRDDS_BUILDER_NAME}" 2>&1 || true)

    if echo "${build_output}" | grep -q "DRDDS_READY"; then
        # Determine host venv site-packages path
        local host_site_packages
        host_site_packages=$("${VENV_DIR}/bin/python3" -c \
            "import site; print(site.getsitepackages()[0])")

        log_info "Copying drdds artifacts to ${host_site_packages}..."
        docker cp "${DRDDS_BUILDER_NAME}:/tmp/drdds_out/." "${host_site_packages}/"
    else
        log_warn "drdds not found in nav container — skipping"
        log_warn "Ensure drdds is available and re-run: deploy.sh setup"
    fi

    # Cleanup
    docker rm -f "${DRDDS_BUILDER_NAME}" &>/dev/null || true

    # Verify import
    if "${VENV_DIR}/bin/python3" -c "import drdds" 2>/dev/null; then
        log_info "drdds installed and importable"
    else
        log_warn "drdds import check failed — package may not be available yet"
    fi
}

# =====================================================================
# usage
# =====================================================================
usage() {
    cat <<EOF
Usage: $(basename "$0") <subcommand> [options]

M20 ROSNav deployment script for NOS host.

Subcommands:
  setup    One-time NOS host provisioning (uv, Python 3.10, dimos, drdds)
  start    Launch dimos on NOS host
  stop     Stop dimos and nav container
  status   Show system health
  dev      Sync source changes to NOS
  logs     View aggregated logs

Run '$(basename "$0") <subcommand> --help' for details.
EOF
}

# =====================================================================
# main dispatch
# =====================================================================
case "${1:-}" in
    setup)  shift; cmd_setup "$@" ;;
    start)  log_error "Not yet implemented"; exit 1 ;;
    stop)   log_error "Not yet implemented"; exit 1 ;;
    status) log_error "Not yet implemented"; exit 1 ;;
    dev)    log_error "Not yet implemented"; exit 1 ;;
    logs)   log_error "Not yet implemented"; exit 1 ;;
    -h|--help) usage ;;
    *)
        if [ -n "${1:-}" ]; then
            log_error "Unknown subcommand: $1"
        fi
        usage
        exit 1
        ;;
esac
