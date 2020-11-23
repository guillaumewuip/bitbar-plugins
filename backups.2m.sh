#!/bin/bash

# <bitbar.title>backups helper</bitbar.title>
# <bitbar.version>v1.0</bitbar.version>
set -e

export PATH=/usr/local/bin:$PATH

LOGO="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"

BACKUPS_FILE="/tmp/backups.json"

function readBackupFile() {
  [ -f $BACKUPS_FILE ] && cat $BACKUPS_FILE || echo "{}"
}

# status: done | running | error | unknown
function status() {
  type=$1

  readBackupFile | jq '.'$type' // {}' | jq -r '.status // "unknown"'
}

function lastUpdate() {
  type=$1

  readBackupFile | jq '.'$type' // {}' | jq -r '.lastUpdate // ""'
}

function lastUpdateReadable() {
  type=$1

  lastUpdateDate=$(lastUpdate $type)

  if [ -z "$lastUpdateDate" ]; then
    echo "unknown"
  else
    date -r $lastUpdateDate
  fi
}

echo "| templateImage=$LOGO"
echo "---"
echo "Documents"
echo "Status: $(status documents)"
echo "Last update: $(lastUpdateReadable documents)"
echo "---"
echo "Mails"
echo "Status: $(status mails)"
echo "Last update: $(lastUpdateReadable mails)"
