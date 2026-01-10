import shutil
import os
import glob
from datetime import datetime, date
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def perform_daily_backup(db_path: str, backup_dir: str = "backups", retention_days: int = 30):
    """
    Creates a copy of the database file in the backup folder if one for today doesn't exist.
    Retains only the last `retention_days` backups.
    """
    if not os.path.exists(db_path):
        logger.warning(f"Database at {db_path} not found. Skipping backup.")
        return

    # Ensure backup directory exists
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)

    today_str = date.today().strftime("%Y-%m-%d")
    base_name = os.path.basename(db_path)
    backup_filename = f"{today_str}_{base_name}"
    backup_path = os.path.join(backup_dir, backup_filename)

    # 1. Perform Backup
    if os.path.exists(backup_path):
        logger.info(f"Backup for today already exists: {backup_path}")
    else:
        try:
            shutil.copy2(db_path, backup_path)
            logger.info(f"Database backed up successfully to: {backup_path}")
        except Exception as e:
            logger.error(f"Failed to backup database: {e}")

    # 2. Prune Old Backups
    try:
        # Pattern matching specific to our naming convention: YYYY-MM-DD_filename
        search_pattern = os.path.join(backup_dir, f"*_{base_name}")
        backups = sorted(glob.glob(search_pattern))
        
        while len(backups) > retention_days:
            oldest_backup = backups.pop(0)
            os.remove(oldest_backup)
            logger.info(f"Pruned old backup: {oldest_backup}")
            
    except Exception as e:
        logger.error(f"Error pruning backups: {e}")
