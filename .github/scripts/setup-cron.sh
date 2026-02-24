#!/bin/bash
# Setup cron jobs for production database backups
# Run this once on the Mac Mini to configure automated backups

set -e

PROD_DIR="/Users/xuzhi/prod/knowledge-base"
BACKUP_DIR="$PROD_DIR/data/backups"

mkdir -p "$BACKUP_DIR"

# Merge with existing crontab (if any), avoiding duplicates
MARKER="# knowledge-base-backup"
(crontab -l 2>/dev/null | grep -v "$MARKER" | grep -v "knowledge-base/data"; cat <<CRON
# Daily backup of knowledge-base prod database at 3am $MARKER
0 3 * * * /usr/bin/sqlite3 $PROD_DIR/data/knowledge.db ".backup $BACKUP_DIR/knowledge.db.\$(date +\%Y\%m\%d)" $MARKER
# Clean up backups older than 7 days $MARKER
5 3 * * * find $BACKUP_DIR -name "knowledge.db.*" -mtime +7 -delete $MARKER
CRON
) | crontab -

echo "Cron jobs installed. Verify with: crontab -l"
echo "Backups will be stored in: $BACKUP_DIR"
echo "Retention: 7 days"