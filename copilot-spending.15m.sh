#!/bin/bash

# <xbar.title>GitHub Copilot Usage</xbar.title>
# <xbar.version>v4.0</xbar.version>
# <xbar.desc>Shows GitHub Copilot premium request usage percentage</xbar.desc>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>

# create a .env file in the same directory with:
# GITHUB_TOKEN=your_github_token
# make sure to keep it private and list it in gitignore
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
set -a && source $SCRIPT_DIR/.env && set +a

# ========== CONFIGURATION ==========
if [[ -z "$GITHUB_TOKEN" ]]; then
	echo ":sparkle: Setup | sfcolor=orange"
	echo "---"
	echo "Edit this plugin and set:"
	echo "  GITHUB_TOKEN"
	exit 0
fi

response=$(curl -s -w "\n%{http_code}" \
	-H "Authorization: Bearer $GITHUB_TOKEN" \
	"https://api.github.com/copilot_internal/user" 2>&1)

http_code=$(echo "$response" | tail -1)
body=$(echo "$response" | sed '$d')

if [[ "$http_code" != "200" ]]; then
	echo ":exclamationmark.triangle.fill: Err | sfcolor=red"
	echo "---"
	echo "HTTP $http_code"
	echo "Refresh | refresh=true"
	exit 0
fi

# Parse premium_interactions quota snapshot
unlimited=$(echo "$body" | jq -r '.quota_snapshots.premium_interactions.unlimited // false')
if [[ "$unlimited" == "true" ]]; then
	pct="0.0"
	pct_int=0
	total_requests="∞"
	PLAN_LIMIT="∞"
else
	percent_remaining=$(echo "$body" | jq -r '.quota_snapshots.premium_interactions.percent_remaining // 0')
	entitlement=$(echo "$body" | jq -r '.quota_snapshots.premium_interactions.entitlement // 0')
	remaining=$(echo "$body" | jq -r '.quota_snapshots.premium_interactions.remaining // 0')

	# Calculate consumed percentage (capped at 100)
	pct=$(echo "scale=1; (100 - $percent_remaining)" | bc)
	pct_float=$(echo "$pct" | awk '{printf "%.1f", $1}')
	if (($(echo "$pct_float > 100" | bc -l))); then
		pct="100.0"
	else
		pct="$pct_float"
	fi
	pct_int=${pct%.*}

	# Calculate used requests
	total_requests=$((entitlement - remaining))
	PLAN_LIMIT=$entitlement
fi

if [[ $pct_int -lt 50 ]]; then
	color="#4a4a4a"
elif [[ $pct_int -lt 80 ]]; then
	color="#f39c12"
else
	color="#e74c3c"
fi

bar_len=10
filled=$((pct_int * bar_len / 100))
empty=$((bar_len - filled))
bar=$(printf '▓%.0s' $(seq 1 $filled 2>/dev/null) || echo "")
bar+=$(printf '░%.0s' $(seq 1 $empty 2>/dev/null) || echo "")

echo ":xserve.raid: ${pct}% | color=$color sfcolor=$color"
echo "---"
echo "Premium Requests | size=11"
echo "$bar ${total_requests}/${PLAN_LIMIT} | font=Menlo size=13"
days_left=$(($(date -v1d -v+1m +%s) - $(date +%s)))
days_left=$((days_left / 86400))
echo "Resets in $days_left days | size=12"
echo "---"
echo "View on GitHub | href=https://github.com/settings/copilot/features"
echo "Refresh | refresh=true"
