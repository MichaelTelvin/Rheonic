import os
from redis import Redis
from rq import Worker, Queue

def main() -> None:
    redis_url = os.getenv("REDIS_URL")
    conn = Redis.from_url(redis_url)

    with conn:
        worker = Worker(
            queues=["llmtbg"],
            connection=conn,
        )
        worker.work()

if __name__ == "__main__":
    main()