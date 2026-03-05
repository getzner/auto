#!/bin/bash
# Herstelplan: Dagelijkse backups van Postgres en Redis
# Voer dit script dagelijks uit via cron, bijv.:
# 0 2 * * * /path/to/trade_server/scripts/backup.sh >> /var/log/trade_backup.log 2>&1

set -e

# Configuratie
BACKUP_DIR="/opt/trade_server_backups" # of een specifiek (S3) gemount pad
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=7

mkdir -p "$BACKUP_DIR/$DATE"
echo "[$DATE] Start backup van trade_server..."

# Laad environment variables (voor DB credentials)
if [ -f "$PROJECT_DIR/.env" ]; then
    export $(grep -v '^#' "$PROJECT_DIR/.env" | xargs)
fi

DB_USER=${DB_USER:-trader}
DB_NAME=${DB_NAME:-trade_db}

# 1. Postgres Backup (pg_dump)
echo "Backing up PostgreSQL..."
docker exec -e PGPASSWORD=${DB_PASSWORD} trade_postgres pg_dump -U "$DB_USER" "$DB_NAME" -F c -f "/tmp/pg_backup.dump"
docker cp trade_postgres:/tmp/pg_backup.dump "$BACKUP_DIR/$DATE/postgresql_$DATE.dump"
docker exec trade_postgres rm -f /tmp/pg_backup.dump

# 2. Redis RDB Snapshot
echo "Backing up Redis RDB..."
docker exec trade_redis redis-cli SAVE
docker cp trade_redis:/data/dump.rdb "$BACKUP_DIR/$DATE/redis_$DATE.rdb"

# Optioneel: ChromaDB Backup (tar van Chroma volume als de container is gestopt)
# echo "Backing up ChromaDB..."
# tar -czf "$BACKUP_DIR/$DATE/chroma_$DATE.tar.gz" -C "$PROJECT_DIR" chromadata || true

# Comprimeren van de dagelijkse backup map
echo "Comprimeren van backups..."
cd "$BACKUP_DIR"
tar -czf "backup_$DATE.tar.gz" "$DATE"
rm -rf "$DATE"

# Off-site sync: (kies 1 van de volgende opties in productie)
# Optie A: S3 via AWS CLI  (Verwijder commentaar als 'aws cli' beschikbaar is)
# echo "Syncing to S3..."
# aws s3 cp "backup_$DATE.tar.gz" s3://my-trade-server-backups/
# 
# Optie B: Git commit (voor kleine bestanden - niet aangeraden voor grote DBs, tenzij git-lfs)
# if [ -d "$PROJECT_DIR/.git" ]; then
#     echo "Committing to Git backup branch..."
#     # git add ... (Implementatie afhankelijk van repository policies)
# fi

# Cleanup oude backups
echo "Cleanup van backups ouder dan $RETENTION_DAYS dagen..."
find "$BACKUP_DIR" -type f -name "backup_*.tar.gz" -mtime +$RETENTION_DAYS -delete

echo "[$DATE] Backup succesvol afgerond: $BACKUP_DIR/backup_$DATE.tar.gz"
