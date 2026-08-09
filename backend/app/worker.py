from uuid import UUID

from redis import Redis
from redis.exceptions import TimeoutError

from app.config import get_settings
from app.database import SessionLocal
from app.object_store import ObjectStore
from app.services import parse_version


def run() -> None:
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True, socket_timeout=15)
    print("parse worker started: talent:parse:queue", flush=True)
    while True:
        try:
            item = redis.blpop("talent:parse:queue", timeout=5)
        except TimeoutError:
            continue
        if not item:
            continue
        job_id, version_id = item[1].split(":", 1)
        with SessionLocal() as db:
            job = parse_version(db, ObjectStore(), UUID(version_id), UUID(job_id))
            print(f"job={job.id} status={job.status} parser={job.parser_name}", flush=True)


if __name__ == "__main__":
    run()
