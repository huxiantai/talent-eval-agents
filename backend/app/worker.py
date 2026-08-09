import logging
from uuid import UUID

from redis import Redis
from redis.exceptions import TimeoutError

from app.config import get_settings
from app.database import SessionLocal
from app.logging_config import configure_logging
from app.object_store import ObjectStore
from app.services import parse_version


logger = logging.getLogger(__name__)


def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_dir, settings.service_name)
    redis = Redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=15)
    logger.info("worker_started queue=talent:parse:queue")
    while True:
        try:
            item = redis.blpop("talent:parse:queue", timeout=5)
        except TimeoutError:
            continue
        except Exception:
            logger.exception("worker_queue_read_failed queue=talent:parse:queue")
            raise
        if not item:
            continue
        job_id, version_id = item[1].split(":", 1)
        logger.info("worker_job_received job_id=%s version_id=%s", job_id, version_id)
        with SessionLocal() as db:
            job = parse_version(db, ObjectStore(), UUID(version_id), UUID(job_id))
            logger.info("worker_job_completed job_id=%s status=%s parser=%s", job.id, job.status, job.parser_name)


if __name__ == "__main__":
    run()
