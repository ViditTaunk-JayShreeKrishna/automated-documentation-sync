"""Background process entry point; no jobs or scheduler are active yet."""

import logging
import signal
import threading

from docsync.config import Settings, require_settings

logger = logging.getLogger(__name__)


def run(stop_event: threading.Event, settings: Settings) -> None:
    logger.info(
        "Worker started in %s; job processing and scheduling are not implemented.",
        settings.environment,
    )
    while not stop_event.wait(timeout=1):
        pass
    logger.info("Worker stopped.")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = require_settings()
    stop_event = threading.Event()

    def request_stop(signum: int, frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    run(stop_event, settings)


if __name__ == "__main__":
    main()
