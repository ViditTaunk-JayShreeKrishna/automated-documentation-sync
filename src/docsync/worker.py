"""Background process entry point; no jobs or scheduler are active yet."""

import logging
import signal
import threading

logger = logging.getLogger(__name__)


def run(stop_event: threading.Event) -> None:
    logger.info("Worker started; job processing and scheduling are not implemented.")
    while not stop_event.wait(timeout=1):
        pass
    logger.info("Worker stopped.")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    stop_event = threading.Event()

    def request_stop(signum: int, frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    run(stop_event)


if __name__ == "__main__":
    main()
