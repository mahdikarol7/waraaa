import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from config import SCHEDULE_TIMES

logger = logging.getLogger(__name__)


def parse_time(time_str):
    """Parse 'HH:MM' string into (hour, minute) tuple."""
    parts = time_str.split(":")
    return int(parts[0]), int(parts[1])


def setup_scheduler(run_callback):
    """Set up APScheduler with cron triggers for each scheduled time."""
    scheduler = AsyncIOScheduler(timezone="UTC")

    for time_str in SCHEDULE_TIMES:
        hour, minute = parse_time(time_str)
        trigger = CronTrigger(hour=hour, minute=minute)
        scheduler.add_job(
            run_callback,
            trigger=trigger,
            id=f"news_run_{time_str}",
            name=f"News Monitor {time_str}",
            misfire_grace_time=300,  # 5 min grace period
            replace_existing=True,
        )
        logger.info(f"Scheduled news run at {time_str}")

    return scheduler
