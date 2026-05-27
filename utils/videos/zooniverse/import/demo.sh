#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Simulated demo: wildintel-tools zooniverse wizard import — Step 2
# Intended to be run by VHS (https://github.com/charmbracelet/vhs)
# ─────────────────────────────────────────────────────────────────────────────

RESET="\033[0m"
BOLD="\033[1m"
DIM="\033[2m"
ITALIC="\033[3m"
GREEN="\033[0;32m"
BLUE="\033[0;34m"
CYAN="\033[0;36m"
YELLOW="\033[1;33m"
DIM_GREEN="\033[2;32m"

# Simulated shell prompt + slow-typed command
prompt_type() {
    local cmd="$1"
    echo -ne "${GREEN}user@wildintel${RESET}:${BLUE}~${RESET}\$ "
    sleep 0.4
    for ((i=0; i<${#cmd}; i++)); do
        echo -n "${cmd:$i:1}"
        sleep 0.045
    done
    echo ""
    sleep 0.6
}

# Slow-type a response
answer() {
    local text="$1"
    local delay="${2:-0.07}"
    for ((i=0; i<${#text}; i++)); do
        echo -n "${text:$i:1}"
        sleep "$delay"
    done
    echo ""
    sleep 0.4
}

# Section separator (mirrors the real wizard style)
section() {
    echo ""
    echo -e "${GREEN}$(printf '%.0s━' $(seq 1 67))${RESET}"
    echo -e "${GREEN}  $1${RESET}"
    echo -e "${GREEN}$(printf '%.0s━' $(seq 1 67))${RESET}"
}

# Select box (mirrors TyperUtils.select_box output)
select_box() {
    local label="$1"
    local multi="$2"   # "single" or "multi"
    shift 2
    local items=("$@")

    echo ""
    echo -e "${BOLD}${BLUE}${label}${RESET}"
    echo ""
    for i in "${!items[@]}"; do
        printf "    ${CYAN}%d.${RESET}  %s\n" "$((i+1))" "${items[$i]}"
    done
    echo -e "  ${DIM}─────────────────────────────────────────────────────${RESET}"
    if [ "$multi" = "multi" ]; then
        echo -e "  ${DIM}${ITALIC}Use numbers (1, 2), ranges (5-8) or 'all'${RESET}"
    else
        echo -e "  ${DIM}${ITALIC}Enter a single number${RESET}"
    fi
}

# Simulate progress bar
progress_bar() {
    local total=$1
    local label="$2"
    local step=0
    while [ $step -le $total ]; do
        local pct=$(( step * 100 / total ))
        local filled=$(( step * 40 / total ))
        local empty=$(( 40 - filled ))
        local bar=""
        for ((i=0; i<filled; i++)); do bar+="━"; done
        for ((i=0; i<empty; i++)); do bar+=" "; done
        printf "\r  ${GREEN}${bar}${RESET}  ${CYAN}%3d/%d${RESET}  [%d%%]" "$step" "$total" "$pct"
        step=$(( step + 3 ))
        sleep 0.08
    done
    printf "\r  ${GREEN}$(printf '%.0s━' $(seq 1 40))${RESET}  ${CYAN}%d/%d${RESET}  [100%%]\n" "$total" "$total"
}

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Import wizard
# ─────────────────────────────────────────────────────────────────────────────

clear
sleep 0.5

prompt_type "wildintel-tools zooniverse wizard import"

section "Import images from Trapper to Zooniverse"
echo ""
echo -e "${BLUE}ℹ${RESET} This wizard will guide you through the process of importing a Trapper collection"
echo -e "    into a Zooniverse subject set. As a general rule, only blank images and images"
echo -e "    that contain animals will be imported."
echo ""
sleep 1

echo -ne "Continue? [y/N]: "
sleep 0.5
answer "y"

# ── Step 1: Research project ─────────────────────────────────────────────────
sleep 0.5
echo -e "  ${BLUE}ℹ${RESET} Connecting to Trapper..."
sleep 1.2

select_box "Select a research project" "single" \
    "Eurasian lynx monitoring 2024  ${DIM_GREEN}(pk: 14)${RESET}" \
    "Iberian wolf survey            ${DIM_GREEN}(pk: 7)${RESET}"
echo ""
echo -ne "  ${YELLOW}>${RESET} "
sleep 0.5
answer "1"
sleep 0.3

# ── Step 2: Classification project ──────────────────────────────────────────
select_box "Select a classification project" "single" \
    "Lynx_CP_2024  ${DIM_GREEN}(pk: 46)${RESET}"
echo ""
echo -ne "  ${YELLOW}>${RESET} "
sleep 0.5
answer "1"
sleep 0.3

# ── Step 3: Collection ───────────────────────────────────────────────────────
select_box "Select a collection" "single" \
    "DONA_24  ${DIM_GREEN}(collection_pk: 66)${RESET}" \
    "MORA_24  ${DIM_GREEN}(collection_pk: 71)${RESET}" \
    "VEGA_24  ${DIM_GREEN}(collection_pk: 75)${RESET}"
echo ""
echo -ne "  ${YELLOW}>${RESET} "
sleep 0.5
answer "1"
sleep 0.3

# ── Step 4: Deployments ──────────────────────────────────────────────────────
select_box "Select a deployment" "multi" \
    "DONA_24-CAM01  ${DIM_GREEN}(pk: 1081)${RESET}" \
    "DONA_24-CAM02  ${DIM_GREEN}(pk: 1080)${RESET}" \
    "DONA_24-CAM03  ${DIM_GREEN}(pk: 1047)${RESET}" \
    "DONA_24-CAM04  ${DIM_GREEN}(pk: 1071)${RESET}" \
    "DONA_24-CAM05  ${DIM_GREEN}(pk: 1083)${RESET}"
echo ""
echo -ne "  ${YELLOW}>${RESET} "
sleep 0.5
answer "1,2,3"
sleep 0.3

# ── Step 5: Subject set name ─────────────────────────────────────────────────
echo ""
DEFAULT_NAME="Eurasian lynx monitoring 2024_14_DONA_24_66_2026-05"
echo -ne "Subject set name [${DIM}${DEFAULT_NAME}${RESET}]: "
sleep 0.5
answer ""   # accept default
sleep 0.3

# ── Step 6: Confirmation ─────────────────────────────────────────────────────
echo ""
echo -e "We are going to import the images taken during deployments"
echo -e "${BOLD}DONA_24-CAM01 (1081), DONA_24-CAM02 (1080), DONA_24-CAM03 (1047)${RESET}"
echo -e "from collection ${BOLD}DONA_24 (66)${RESET} into Zooniverse subject set"
echo -e "${BOLD}${DEFAULT_NAME}${RESET},"
echo -e "using detection data from classification project ${BOLD}Lynx_CP_2024 (46)${RESET}"
echo -e "within research project ${BOLD}Eurasian lynx monitoring 2024 (14)${RESET}."
echo -e "Are you sure?"
echo ""
echo -ne "Confirm [y/N]: "
sleep 0.6
answer "y"

# ── Step 7: Dry-run ──────────────────────────────────────────────────────────
echo ""
echo -ne "Do you want to run in DRY-RUN mode? [y/N]: "
sleep 0.5
answer "n"
echo ""

# ── Import progress ──────────────────────────────────────────────────────────
echo -e "${BLUE}ℹ${RESET} Fetching media from Trapper deployments..."
sleep 1.2
echo -e "${GREEN}✓${RESET} 87 sequences built from 435 images (3 deployments)"
echo ""
echo -e "${BLUE}ℹ${RESET} Creating subject set ${BOLD}${DEFAULT_NAME}${RESET}..."
sleep 0.8
echo -e "${GREEN}✓${RESET} Subject set created (id: 118432)"
echo ""
echo -e "${BLUE}ℹ${RESET} Uploading sequences to Zooniverse..."
echo ""
progress_bar 87 "Uploading"
echo ""
sleep 0.5

echo -e "${GREEN}✓${RESET} ${BOLD}Upload complete!${RESET}"
echo ""
echo -e "  ${DIM}Subject set : ${DEFAULT_NAME} (118432)${RESET}"
echo -e "  ${DIM}Uploaded    : 87 / 87 sequences${RESET}"
echo -e "  ${DIM}Skipped     : 0${RESET}"
echo -e "  ${DIM}Failed      : 0${RESET}"
echo ""
sleep 2
