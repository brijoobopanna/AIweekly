import sys
import logging
import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

import config as _cfg  # triggers logging setup via module-level side-effect
from config import config
from pipeline import run_pipeline

logger = logging.getLogger(__name__)


def start_scheduler() -> None:
    tz = pytz.timezone(config.schedule_timezone)
    scheduler = BlockingScheduler(timezone=tz)

    trigger = CronTrigger(
        day_of_week=config.schedule_day,
        hour=config.schedule_hour,
        minute=config.schedule_minute,
        timezone=tz,
    )

    scheduler.add_job(
        func=run_pipeline,
        trigger=trigger,
        id="weekly_ai_pipeline",
        name="Weekly AI Content Pipeline",
        misfire_grace_time=3600,  # Run within 1 hour if machine was asleep
    )

    logger.info(
        "Scheduler started. Runs every %s at %02d:%02d %s",
        config.schedule_day.upper(),
        config.schedule_hour,
        config.schedule_minute,
        config.schedule_timezone,
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    if "--run-now" in sys.argv:
        run_pipeline()
    else:
        start_scheduler()
