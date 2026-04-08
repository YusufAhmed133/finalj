"""APScheduler wrapper for JARVIS scheduled tasks."""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from jarvis.utils.logger import get_logger

log = get_logger("scheduler")


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Australia/Sydney")
    log.info("Scheduler created (AEST/AEDT)")
    return scheduler


def add_daily_job(scheduler: AsyncIOScheduler, func, hour: int, minute: int = 0, name: str = ""):
    trigger = CronTrigger(hour=hour, minute=minute, timezone="Australia/Sydney")
    scheduler.add_job(func, trigger, name=name or func.__name__)
    log.info(f"Scheduled daily job '{name or func.__name__}' at {hour:02d}:{minute:02d} AEST")
