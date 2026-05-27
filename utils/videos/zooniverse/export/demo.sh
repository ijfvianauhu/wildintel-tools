#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Simulated demo: wildintel-tools zooniverse wizard export — Step 4
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

section() {
    echo ""
    echo -e "${GREEN}$(printf '%.0s━' $(seq 1 67))${RESET}"
    echo -e "${GREEN}  $1${RESET}"
    echo -e "${GREEN}$(printf '%.0s━' $(seq 1 67))${RESET}"
}

select_box() {
    local label="$1"
    local multi="$2"
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

progress_bar() {
    local total=$1
    local step=0
    while [ $step -le $total ]; do
        local pct=$(( step * 100 / total ))
        local filled=$(( step * 40 / total ))
        local empty=$(( 40 - filled ))
        local bar=""
        for ((i=0; i<filled; i++)); do bar+="━"; done
        for ((i=0; i<empty; i++)); do bar+=" "; done
        printf "\r  ${GREEN}${bar}${RESET}  ${CYAN}%3d/%d${RESET}  [%d%%]" "$step" "$total" "$pct"
        step=$(( step + 2 ))
        sleep 0.07
    done
    printf "\r  ${GREEN}$(printf '%.0s━' $(seq 1 40))${RESET}  ${CYAN}%d/%d${RESET}  [100%%]\n" "$total" "$total"
}

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Export wizard
# ─────────────────────────────────────────────────────────────────────────────

clear
sleep 0.5

prompt_type "wildintel-tools zooniverse wizard export"

section "Export annotations from a Zooniverse subject set to Trapper"
echo ""
echo -e "${BLUE}ℹ${RESET} This wizard will guide you through exporting Zooniverse classification"
echo -e "    results back to Trapper as observations. You will need to select"
echo -e "    the subject set, the research project and the classification project."
echo ""
sleep 1

echo -ne "Continue? [y/N]: "
sleep 0.5
answer "y"

# ── Step 1: Workflow ─────────────────────────────────────────────────────────
echo ""
echo -e "  ${BLUE}ℹ${RESET} Retrieving workflows from Zooniverse..."
sleep 1.3

select_box "Select a workflow" "single" \
    "Lynx identification  ${DIM_GREEN}(id: 29187)${RESET}" \
    "Wolf monitoring      ${DIM_GREEN}(id: 31042)${RESET}"
echo ""
echo -ne "  ${YELLOW}>${RESET} "
sleep 0.5
answer "1"
echo -e "  ${GREEN}✓${RESET} Workflow selected: ${BOLD}Lynx identification${RESET} (id: 29187)"

# ── Step 2: Subject set ──────────────────────────────────────────────────────
echo ""
echo -e "  ${BLUE}ℹ${RESET} Retrieving subject sets from Zooniverse..."
sleep 1.2

select_box "Select a subject set" "single" \
    "Eurasian lynx monitoring 2024_14_DONA_24_66_2026-05  ${DIM_GREEN}(id: 118432)${RESET}" \
    "Eurasian lynx monitoring 2024_14_MORA_24_71_2026-04  ${DIM_GREEN}(id: 115890)${RESET}"
echo ""
echo -ne "  ${YELLOW}>${RESET} "
sleep 0.5
answer "1"
echo -e "  ${GREEN}✓${RESET} Subject set selected: ${BOLD}Eurasian lynx monitoring 2024_14_DONA_24_66_2026-05${RESET} (id: 118432)"

# ── Step 3: Research project ─────────────────────────────────────────────────
echo ""
select_box "Select a research project" "single" \
    "Eurasian lynx monitoring 2024  ${DIM_GREEN}(pk: 14)${RESET}" \
    "Iberian wolf survey            ${DIM_GREEN}(pk: 7)${RESET}"
echo ""
echo -ne "  ${YELLOW}>${RESET} "
sleep 0.5
answer "1"
echo -e "  ${GREEN}✓${RESET} Research project selected: ${BOLD}Eurasian lynx monitoring 2024${RESET} (id: 14)"

# ── Step 4: Classification project ──────────────────────────────────────────
echo ""
select_box "Select a classification project" "single" \
    "Lynx_CP_2024  ${DIM_GREEN}(pk: 46)${RESET}"
echo ""
echo -ne "  ${YELLOW}>${RESET} "
sleep 0.5
answer "1"
echo -e "  ${GREEN}✓${RESET} Classification project selected: ${BOLD}Lynx_CP_2024${RESET} (id: 46)"

# ── Step 5: Collection ───────────────────────────────────────────────────────
echo ""
select_box "Select a collection" "single" \
    "DONA_24  ${DIM_GREEN}(collection_pk: 66)${RESET}" \
    "MORA_24  ${DIM_GREEN}(collection_pk: 71)${RESET}"
echo ""
echo -ne "  ${YELLOW}>${RESET} "
sleep 0.5
answer "1"

# ── Step 6: Deployments ──────────────────────────────────────────────────────
select_box "Select deployment" "multi" \
    "DONA_24-CAM01  ${DIM_GREEN}(pk: 1081)${RESET}" \
    "DONA_24-CAM02  ${DIM_GREEN}(pk: 1080)${RESET}" \
    "DONA_24-CAM03  ${DIM_GREEN}(pk: 1047)${RESET}"
echo ""
echo -ne "  ${YELLOW}>${RESET} "
sleep 0.5
answer "all"

# ── Step 7: Output file ──────────────────────────────────────────────────────
DEFAULT_CSV="~/Documents/wildintel-tools/zooniverse/zoo_annotations_29187_118432_66_46_202605281200.csv"
echo ""
echo -ne "CSV file to save annotations [${DIM}${DEFAULT_CSV}${RESET}]: "
sleep 0.5
answer ""

# ── Steps 8-11: Options ──────────────────────────────────────────────────────
echo ""
echo -ne "Show detail for each processed media in the progress bar? [Y/n]: "
sleep 0.4
answer "y"

echo -ne "Save the raw Zooniverse annotations as a separate CSV? [Y/n]: "
sleep 0.4
answer "y"

echo -ne "Maximum CSV file size in MB before splitting [1.5]: "
sleep 0.4
answer ""

echo -ne "Automatically upload the generated CSV(s) to Trapper after generating? [y/N]: "
sleep 0.4
answer "n"

# ── Step 12: Confirm ────────────────────────────────────────────────────────
echo ""
echo -ne "Ready to export. Proceed? [y/N]: "
sleep 0.6
answer "y"
echo ""

# ── Export progress ──────────────────────────────────────────────────────────
echo -e "${BLUE}ℹ${RESET} Applying consensus process to Zooniverse classifications..."
echo ""
progress_bar 87
echo ""
sleep 0.5

echo -e "${GREEN}✓${RESET} ${BOLD}Export complete!${RESET}"
echo ""
echo -e "  ${DIM}Output CSV  : ${DEFAULT_CSV}${RESET}"
echo -e "  ${DIM}Raw annots  : zoo_annotations_raw_29187_118432_202605281200.csv${RESET}"
echo -e "  ${DIM}Processed   : 87 subjects · 312 observations generated${RESET}"
echo -e "  ${DIM}Trapper URL : https://trapper.wildintel.eu/observations/import/${RESET}"
echo ""
sleep 2
