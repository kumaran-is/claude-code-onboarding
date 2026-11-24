# Automated Backup + Restoration Drill Pattern

## Overview

Backups that have never been restored are not backups — they are hopes. This pattern covers automated PostgreSQL backups with scheduled restoration drills.

## Automated Backup (pg_dump)

### Backup Script

```bash
#!/usr/bin/env bash
# scripts/backup-db.sh
set -euo pipefail

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="${BACKUP_DIR:-/backups}"
DB_NAME="${DB_NAME:?DB_NAME required}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.sql.gz"

echo "[$(date -Iseconds)] Starting backup of ${DB_NAME}..."

pg_dump \
  --format=custom \
  --verbose \
  --no-owner \
  --no-privileges \
  "${DATABASE_URL}" | gzip > "${BACKUP_FILE}"

BACKUP_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
echo "[$(date -Iseconds)] Backup complete: ${BACKUP_FILE} (${BACKUP_SIZE})"

# Upload to GCS (or S3)
gsutil cp "${BACKUP_FILE}" "gs://${GCS_BACKUP_BUCKET}/${DB_NAME}/${TIMESTAMP}.sql.gz"
echo "[$(date -Iseconds)] Uploaded to gs://${GCS_BACKUP_BUCKET}/${DB_NAME}/${TIMESTAMP}.sql.gz"

# Cleanup old local backups
find "${BACKUP_DIR}" -name "${DB_NAME}_*.sql.gz" -mtime +${RETENTION_DAYS} -delete
echo "[$(date -Iseconds)] Cleaned up backups older than ${RETENTION_DAYS} days"
```

### Cron Schedule

```cron
# Daily at 2 AM (off-peak)
0 2 * * * /opt/scripts/backup-db.sh >> /var/log/backup.log 2>&1

# Hourly WAL archiving for point-in-time recovery (if using continuous archiving)
0 * * * * /opt/scripts/archive-wal.sh >> /var/log/wal-archive.log 2>&1
```

### Cloud Run Jobs (Serverless Alternative)

Run `scripts/backup-db.sh` as a Cloud Run job whose image is built `FROM postgres:18.7` pinned by the digest you resolved (`docker buildx imagetools inspect postgres:18.7`), with `pg_dump` matching the server's major version. A GitHub Actions workflow builds and pushes that image; Cloud Scheduler starts the job.

```bash
gcloud run jobs create backup-db --region=<region> --image=<registry>/backup-db@sha256:<digest> \
  --set-secrets=DATABASE_URL=backup-db-url:latest --set-env-vars=GCS_BACKUP_BUCKET=<bucket> \
  --service-account=<backup-job-sa> --max-retries=1 --task-timeout=3600s
gcloud run jobs execute backup-db --region=<region> --wait    # manual run / drill

# Daily at 02:00 via Cloud Scheduler (service account needs roles/run.invoker on the job)
gcloud scheduler jobs create http backup-daily --location=<region> --schedule="0 2 * * *" \
  --http-method=POST \
  --uri="https://run.googleapis.com/v2/projects/<project>/locations/<region>/jobs/backup-db:run" \
  --oauth-service-account-email=<scheduler-sa>
```

## Restoration Drill

### Restore Script

```bash
#!/usr/bin/env bash
# scripts/restore-drill.sh
set -euo pipefail

BACKUP_FILE="${1:?Usage: restore-drill.sh <backup-file>}"
DRILL_DB="${DRILL_DB:-restore_drill_$(date +%Y%m%d)}"

echo "[$(date -Iseconds)] Starting restoration drill..."
echo "  Backup: ${BACKUP_FILE}"
echo "  Target DB: ${DRILL_DB}"

# 1. Create isolated drill database
psql "${DATABASE_URL}" -c "CREATE DATABASE ${DRILL_DB};"

# 2. Restore backup
DRILL_URL=$(echo "${DATABASE_URL}" | sed "s|/[^/]*$|/${DRILL_DB}|")
pg_restore \
  --verbose \
  --no-owner \
  --no-privileges \
  --dbname="${DRILL_URL}" \
  "${BACKUP_FILE}"

# 3. Validate restoration
TABLES=$(psql "${DRILL_URL}" -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';")
ROWS=$(psql "${DRILL_URL}" -t -c "
  SELECT sum(n_live_tup)
  FROM pg_stat_user_tables;
")

echo "[$(date -Iseconds)] Restoration complete."
echo "  Tables restored: ${TABLES}"
echo "  Total rows: ${ROWS}"

# 4. Run application health checks against drill DB
# (optional: point a staging app at the drill DB and run smoke tests)

# 5. Cleanup drill database
psql "${DATABASE_URL}" -c "DROP DATABASE ${DRILL_DB};"
echo "[$(date -Iseconds)] Drill database cleaned up."
```

### Drill Schedule

Run restoration drills on a regular cadence:

```cron
# Monthly on the 1st at 4 AM
0 4 1 * * /opt/scripts/restore-drill.sh /backups/latest.sql.gz >> /var/log/restore-drill.log 2>&1
```

## Monitoring and Alerts

- Alert if daily backup does not complete by 3 AM
- Alert if backup size drops >50% from previous day (data loss indicator)
- Alert if restoration drill fails
- Track backup sizes over time (unexpected shrinkage = problem)

## Checklist

- [ ] Daily automated backup running (pg_dump or continuous archiving)
- [ ] Backups uploaded to remote storage (GCS/S3, different region)
- [ ] Backup retention policy enforced (30 days minimum)
- [ ] Monthly restoration drill scheduled and passing
- [ ] Alerts configured for backup failures
- [ ] Alerts configured for restoration drill failures
- [ ] Backup encryption at rest (GCS default encryption or explicit KMS)
- [ ] Backup access restricted (IAM, not public)
- [ ] Point-in-time recovery configured (WAL archiving) for production databases
