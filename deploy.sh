#!/usr/bin/env bash
#
# deploy.sh — M20 ROSNav deployment script
#
# Manages dimos deployment on the M20 NOS host with container-based
# navigation stack (FASTLIO2, FAR planner, base_autonomy).

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# --- AOS connection defaults (override via environment or .env) ---
AOS_IP="${AOS_IP:-192.168.123.161}"
AOS_USER="${AOS_USER:-unitree}"
AOS_SSH_OPTS="${AOS_SSH_OPTS:--o StrictHostKeyChecking=no -o ConnectTimeout=5}"

# --- Helper functions ---

aos_ssh() {
    # Execute a command on the AOS board via SSH.
    # Usage: aos_ssh "command to run"
    ssh ${AOS_SSH_OPTS} "${AOS_USER}@${AOS_IP}" "$@"
}

aos_sudo() {
    # Execute a privileged command on the AOS board via SSH.
    # Usage: aos_sudo "command to run"
    aos_ssh "sudo $*"
}

# --- Service management ---

ensure_lio_disabled() {
    # Stop lio_perception on the AOS board so that the nav container's
    # FASTLIO2 can use the lidar exclusively. Idempotent — safe to call
    # multiple times.
    #
    # Acceptance criteria:
    #   - After running, lio_perception is not running on AOS
    #   - /lidar_points DDS topic still has publishers (hardware lidar driver
    #     is unaffected — only the SLAM process is stopped)
    #   - Function is idempotent

    echo -e "${GREEN}Checking lio_perception on AOS (${AOS_IP})...${NC}"

    # Check if lio_perception is running
    if ! aos_ssh "pgrep -x lio_perception" >/dev/null 2>&1; then
        echo -e "${GREEN}lio_perception is already stopped on AOS.${NC}"
        return 0
    fi

    echo -e "${YELLOW}Stopping lio_perception on AOS...${NC}"

    # Disable the systemd service so it doesn't restart on reboot
    aos_sudo "systemctl stop lio_perception.service" 2>/dev/null || true
    aos_sudo "systemctl disable lio_perception.service" 2>/dev/null || true

    # If lio_perception is not managed by systemd, kill it directly
    if aos_ssh "pgrep -x lio_perception" >/dev/null 2>&1; then
        echo -e "${YELLOW}lio_perception still running, sending SIGTERM...${NC}"
        aos_sudo "pkill -x lio_perception" 2>/dev/null || true

        # Wait up to 5 seconds for graceful shutdown
        for i in $(seq 1 10); do
            if ! aos_ssh "pgrep -x lio_perception" >/dev/null 2>&1; then
                break
            fi
            sleep 0.5
        done

        # Force kill if still alive
        if aos_ssh "pgrep -x lio_perception" >/dev/null 2>&1; then
            echo -e "${RED}Force-killing lio_perception...${NC}"
            aos_sudo "pkill -9 -x lio_perception" 2>/dev/null || true
            sleep 1
        fi
    fi

    # Final verification
    if aos_ssh "pgrep -x lio_perception" >/dev/null 2>&1; then
        echo -e "${RED}ERROR: Failed to stop lio_perception on AOS.${NC}" >&2
        return 1
    fi

    echo -e "${GREEN}lio_perception stopped successfully on AOS.${NC}"
    return 0
}
