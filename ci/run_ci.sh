#!/usr/bin/env bash
# run_ci.sh — Four-layer quality gate for multi_arm_line_ws
#
# Layer 1: colcon build (all packages compile)
# Layer 2: unit test (pytest + colcon test)
# Layer 3: launch smoke test (ros2 launch + node alive check)
# Layer 4: E2E smoke test (submit task → verify success/failure)
#
# Usage:
#   ./ci/run_ci.sh              # Run all layers
#   ./ci/run_ci.sh --layer 1    # Run only layer 1
#   ./ci/run_ci.sh --layer 1,2  # Run layers 1 and 2
#   ./ci/run_ci.sh --skip-4     # Skip layer 4 (needs Gazebo)
#
# Exit code: 0 = all pass, 1 = failure

set -eo pipefail

WORKSPACE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ROS_SETUP="/opt/ros/jazzy/setup.bash"
RESULTS_DIR="${WORKSPACE_DIR}/ci_results"
LAYER_RESULTS=()

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[CI INFO]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[CI WARN]${NC} $*"; }
log_error() { echo -e "${RED}[CI FAIL]${NC} $*"; }

parse_args() {
    RUN_LAYERS="1,2,3,4"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --layer) RUN_LAYERS="$2"; shift 2 ;;
            --skip-4) RUN_LAYERS="1,2,3"; shift ;;
            *) log_error "Unknown argument: $1"; exit 1 ;;
        esac
    done
}

should_run() {
    local layer="$1"
    echo ",${RUN_LAYERS}," | grep -q ",${layer},"
}

setup_env() {
    log_info "Setting up ROS2 environment"
    source "${ROS_SETUP}"
    export PATH="/usr/bin:/usr/local/bin:/opt/ros/jazzy/bin:/opt/ros/jazzy/opt/gz_tools_vendor/bin:${PATH}"
    export ROS_HOME="/tmp/ros_home"
    export ROS_LOG_DIR="/tmp/ros_home/log"
    export GZ_SIM_SYSTEM_PLUGIN_PATH="/opt/ros/jazzy/lib:/opt/ros/jazzy/opt/gz_sim_vendor/lib/gz-sim-8/plugins"
    mkdir -p "${ROS_HOME}" "${RESULTS_DIR}"
}

run_layer_1() {
    log_info "=== Layer 1: colcon build ==="
    local start_time
    start_time=$(date +%s)

    cd "${WORKSPACE_DIR}"
    colcon build \
        --packages-select \
            multi_arm_interfaces \
            multi_arm_core \
            multi_arm_safety \
            multi_arm_world_model \
            multi_arm_task_planner \
            multi_arm_recovery \
            multi_arm_benchmark \
            order_manager \
            ur_simulation_gz \
        2>&1 | tee "${RESULTS_DIR}/layer1_build.log"

    local exit_code=${PIPESTATUS[0]}
    local end_time
    end_time=$(date +%s)

    if [[ ${exit_code} -eq 0 ]]; then
        log_info "Layer 1 PASSED ($((end_time - start_time))s)"
        LAYER_RESULTS+=("Layer1:PASS")
    else
        log_error "Layer 1 FAILED ($((end_time - start_time))s)"
        LAYER_RESULTS+=("Layer1:FAIL")
    fi
    return ${exit_code}
}

run_layer_2() {
    log_info "=== Layer 2: unit tests ==="
    local start_time
    start_time=$(date +%s)

    cd "${WORKSPACE_DIR}"
    source install/setup.bash

    colcon test \
        --packages-select \
            multi_arm_interfaces \
            multi_arm_core \
            multi_arm_safety \
            multi_arm_world_model \
            multi_arm_task_planner \
            multi_arm_recovery \
            multi_arm_benchmark \
        2>&1 | tee "${RESULTS_DIR}/layer2_test.log"

    colcon test-result --verbose \
        2>&1 | tee "${RESULTS_DIR}/layer2_results.log"

    local exit_code=$?
    local end_time
    end_time=$(date +%s)

    local failed
    failed=$(grep -c "0 errors, 0 failures" "${RESULTS_DIR}/layer2_results.log" || echo "0")
    if [[ ${exit_code} -eq 0 ]] && [[ ${failed} -ge 1 ]]; then
        log_info "Layer 2 PASSED ($((end_time - start_time))s)"
        LAYER_RESULTS+=("Layer2:PASS")
    else
        log_error "Layer 2 FAILED ($((end_time - start_time))s)"
        LAYER_RESULTS+=("Layer2:FAIL")
    fi
    return ${exit_code}
}

run_layer_3() {
    log_info "=== Layer 3: launch smoke test ==="
    local start_time
    start_time=$(date +%s)

    cd "${WORKSPACE_DIR}"
    source install/setup.bash

    python3 "${WORKSPACE_DIR}/ci/launch_smoke_test.py" \
        2>&1 | tee "${RESULTS_DIR}/layer3_launch.log"

    local exit_code=${PIPESTATUS[0]}
    local end_time
    end_time=$(date +%s)

    if [[ ${exit_code} -eq 0 ]]; then
        log_info "Layer 3 PASSED ($((end_time - start_time))s)"
        LAYER_RESULTS+=("Layer3:PASS")
    else
        log_error "Layer 3 FAILED ($((end_time - start_time))s)"
        LAYER_RESULTS+=("Layer3:FAIL")
    fi
    return ${exit_code}
}

run_layer_4() {
    log_info "=== Layer 4: E2E smoke test ==="
    local start_time
    start_time=$(date +%s)

    cd "${WORKSPACE_DIR}"
    source install/setup.bash

    python3 "${WORKSPACE_DIR}/ci/e2e_smoke_test.py" \
        2>&1 | tee "${RESULTS_DIR}/layer4_e2e.log"

    local exit_code=${PIPESTATUS[0]}
    local end_time
    end_time=$(date +%s)

    if [[ ${exit_code} -eq 0 ]]; then
        log_info "Layer 4 PASSED ($((end_time - start_time))s)"
        LAYER_RESULTS+=("Layer4:PASS")
    else
        log_error "Layer 4 FAILED ($((end_time - start_time))s)"
        LAYER_RESULTS+=("Layer4:FAIL")
    fi
    return ${exit_code}
}

print_summary() {
    echo ""
    echo "========================================="
    echo "  CI Pipeline Summary"
    echo "========================================="
    for result in "${LAYER_RESULTS[@]}"; do
        local name="${result%%:*}"
        local status="${result##*:}"
        if [[ "${status}" == "PASS" ]]; then
            echo -e "  ${name}: ${GREEN}PASS${NC}"
        else
            echo -e "  ${name}: ${RED}FAIL${NC}"
        fi
    done
    echo "========================================="

    for result in "${LAYER_RESULTS[@]}"; do
        if [[ "${result##*:}" != "PASS" ]]; then
            return 1
        fi
    done
    return 0
}

main() {
    parse_args "$@"
    setup_env

    log_info "Running layers: ${RUN_LAYERS}"
    log_info "Results dir: ${RESULTS_DIR}"

    local overall_exit=0

    if should_run 1; then
        run_layer_1 || overall_exit=1
    fi

    if should_run 2; then
        if [[ ${overall_exit} -eq 0 ]]; then
            run_layer_2 || overall_exit=1
        else
            log_warn "Skipping Layer 2 (Layer 1 failed)"
            LAYER_RESULTS+=("Layer2:SKIP")
        fi
    fi

    if should_run 3; then
        if [[ ${overall_exit} -eq 0 ]]; then
            run_layer_3 || overall_exit=1
        else
            log_warn "Skipping Layer 3 (earlier layer failed)"
            LAYER_RESULTS+=("Layer3:SKIP")
        fi
    fi

    if should_run 4; then
        if [[ ${overall_exit} -eq 0 ]]; then
            run_layer_4 || overall_exit=1
        else
            log_warn "Skipping Layer 4 (earlier layer failed)"
            LAYER_RESULTS+=("Layer4:SKIP")
        fi
    fi

    print_summary
    return ${overall_exit}
}

main "$@"