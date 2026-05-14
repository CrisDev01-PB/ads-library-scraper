#!/bin/bash
# Weekly competitor ad-library scrape — fired by launchd every Sunday at 10:00 local time.
# Writes a dated snapshot to the Ad Library Scraping Database folder.
# Independent of Claude Code; runs as long as the Mac is on.

set -u

# Make Homebrew tools (mlx_whisper, etc.) discoverable in the launchd PATH.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

DATE=$(date +%Y-%m-%d)
DB_DIR="/Users/cristianosanna/LLM-Wiki-Copy/Ad Library Scraping Database"
OUT="$DB_DIR/${DATE}-snapshot.md"
LOG_DIR="/Users/cristianosanna/tools/ads-library-scraper/logs"
LOG="$LOG_DIR/scrape-${DATE}.log"

mkdir -p "$DB_DIR" "$LOG_DIR"

echo "=== Weekly scrape starting at $(date) ===" | tee -a "$LOG"

/Users/cristianosanna/tools/ads-library-scraper/.venv/bin/ads-library-batch \
    464311650289123 \
    177930899801067 \
    102085878248433 \
    146438712035078 \
    279351549238696 \
    --transcribe \
    --since-days 7 \
    --transcribe-workers 2 \
    --output "$OUT" 2>&1 | tee -a "$LOG"

EXIT_CODE=${PIPESTATUS[0]}

echo "=== Weekly scrape finished at $(date) with exit code $EXIT_CODE ===" | tee -a "$LOG"
exit "$EXIT_CODE"
