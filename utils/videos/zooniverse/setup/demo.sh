#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Simulated demo: wildintel-tools zooniverse workflow — Step 0
# Intended to be run by VHS (https://github.com/charmbracelet/vhs)
# ─────────────────────────────────────────────────────────────────────────────

RESET="\033[0m"
BOLD="\033[1m"
GREEN="\033[0;32m"
BLUE="\033[0;34m"
DIM="\033[2m"

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

# Slow-type a response to a prompt
answer() {
    local text="$1"
    local delay="${2:-0.06}"
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

# ─────────────────────────────────────────────────────────────────────────────
# STEP 0 — Setup wizard
# ─────────────────────────────────────────────────────────────────────────────

clear
sleep 0.5

prompt_type "wildintel-tools zooniverse wizard setup"

section "Configure zooniverse module"
echo ""
echo -e "${BLUE}ℹ${RESET} This wizard will guide you through Zooniverse connection settings."
echo ""
sleep 0.8

echo -ne "Continue? [y/N]: "
sleep 0.5
answer "y"

echo ""
echo -ne "Enter your Zooniverse username [myuser]: "
sleep 0.3
answer "wildintel_admin"

echo -ne "Enter your Zooniverse password: "
sleep 0.3
answer "••••••••••••" 0.08

echo -ne "Enter your Zooniverse project ID [myprojectid]: "
sleep 0.3
answer "98765"

echo ""
echo -ne "Number of images per upload batch [5]: "
sleep 0.3
answer "5"

echo -ne "Maximum interval between upload batches (seconds) [90]: "
sleep 0.3
answer "90"

echo -ne "Maximum download attempts per batch (from Trapper) [5]: "
sleep 0.3
answer "5"

echo -ne "Delay between download attempts (seconds) [15]: "
sleep 0.3
answer "15"

echo -ne "Maximum attempts per subject [5]: "
sleep 0.3
answer "5"

echo -ne "Delay per subject (seconds) [30]: "
sleep 0.3
answer "30"

echo ""
echo -ne "Trapper username for Zooniverse observations (classifiedBy) [zooniverse@wildintel-project.org]: "
sleep 0.3
answer "zooniverse@wildintel-project.org"

echo -ne "Maximum CSV file size in MB before splitting [1.5]: "
sleep 0.3
answer "1.5"

echo ""
sleep 0.8

# Settings summary table
echo -e "${BOLD} Settings to update ${RESET}"
echo -e "${DIM}┌──────────────────────────────────────────────────────┬──────────────────────────────────────────┐${RESET}"
echo -e "${DIM}│${RESET} ${BOLD}Setting${RESET}                                              ${DIM}│${RESET} ${BOLD}Value${RESET}                                    ${DIM}│${RESET}"
echo -e "${DIM}├──────────────────────────────────────────────────────┼──────────────────────────────────────────┤${RESET}"
echo -e "${DIM}│${RESET} ZOONIVERSE.zooniverse_username                       ${DIM}│${RESET} wildintel_admin                          ${DIM}│${RESET}"
echo -e "${DIM}│${RESET} ZOONIVERSE.zooniverse_password                       ${DIM}│${RESET} ********                                 ${DIM}│${RESET}"
echo -e "${DIM}│${RESET} ZOONIVERSE.zooniverse_project_id                     ${DIM}│${RESET} 98765                                    ${DIM}│${RESET}"
echo -e "${DIM}│${RESET} ZOONIVERSE_CONNECTOR.upload_collection_n_images_seq  ${DIM}│${RESET} 5                                        ${DIM}│${RESET}"
echo -e "${DIM}│${RESET} ZOONIVERSE_CONNECTOR.upload_collection_max_interval  ${DIM}│${RESET} 90                                       ${DIM}│${RESET}"
echo -e "${DIM}│${RESET} ZOONIVERSE_CONNECTOR.upload_collection_download_attempts ${DIM}│${RESET} 5                                   ${DIM}│${RESET}"
echo -e "${DIM}│${RESET} ZOONIVERSE_CONNECTOR.upload_collection_download_delay    ${DIM}│${RESET} 15                                  ${DIM}│${RESET}"
echo -e "${DIM}│${RESET} ZOONIVERSE_CONNECTOR.annotations_classified_by       ${DIM}│${RESET} zooniverse@wildintel-project.org         ${DIM}│${RESET}"
echo -e "${DIM}│${RESET} ZOONIVERSE_CONNECTOR.annotations_max_file_size_mb    ${DIM}│${RESET} 1.5                                      ${DIM}│${RESET}"
echo -e "${DIM}└──────────────────────────────────────────────────────┴──────────────────────────────────────────┘${RESET}"
echo ""
sleep 0.5

echo -ne "Do you want to apply these changes? [y/N]: "
sleep 0.5
answer "y"

echo ""
echo -e "${BOLD}${GREEN}Zooniverse configuration for project 'default' saved successfully!${RESET}"
echo ""
sleep 1.5

# ─────────────────────────────────────────────────────────────────────────────
# VERIFY CONNECTION
# ─────────────────────────────────────────────────────────────────────────────

echo ""
prompt_type "wildintel-tools zooniverse test-connection"

sleep 0.5
echo -e "${BLUE}ℹ${RESET} Testing Zooniverse API connection wildintel_admin..."
sleep 2
echo -e "${GREEN}✓${RESET} ${BOLD}Zooniverse API connection successful!${RESET}"
echo ""
sleep 2
