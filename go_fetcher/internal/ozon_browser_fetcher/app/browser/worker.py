import queue
import threading
import traceback
from typing import Any, Dict, Optional

from ozon_browser_fetcher.app.browser.manager import BrowserManager
from ozon_browser_fetcher.app.parsers.product_parser import parse_product_from_page


class BrowserWorker:
    def __init__(self, cookie_path: str) -> None:
        self.cookie_path = cookie_path
        self.manager = BrowserManager()

        self.task_queue: queue.Queue = queue.Queue()
        self.ready_event = threading.Event()
        self.stop_event = threading.Event()

        self.thread: Optional[threading.Thread] = None
        self.startup_error: Optional[str] = None

    def start(self) -> None:
        if self.thread is not None and self.thread.is_alive():
            return

        self.thread = threading.Thread(
            target=self._run,
            name="ozon-browser-worker",
            daemon=True,
        )
        self.thread.start()

        is_ready = self.ready_event.wait(timeout=90)

        if not is_ready:
            raise RuntimeError("Ozon browser worker did not start in time")

        if self.startup_error is not None:
            raise RuntimeError(self.startup_error)

    def _run(self) -> None:
        try:
            self.manager.start(self.cookie_path)
            self.ready_event.set()
        except Exception:
            self.startup_error = traceback.format_exc()
            self.ready_event.set()
            return

        while not self.stop_event.is_set():
            try:
                task = self.task_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                task_type = task.get("type")

                if task_type == "product":
                    result = self._handle_product(task)
                else:
                    raise RuntimeError(f"Unknown task type: {task_type}")

                task["result_queue"].put(
                    {
                        "ok": True,
                        "data": result,
                    }
                )
            except Exception as exc:
                task["result_queue"].put(
                    {
                        "ok": False,
                        "error": str(exc),
                        "trace": traceback.format_exc(),
                    }
                )
            finally:
                self.task_queue.task_done()

        self.manager.stop()

    def _handle_product(self, task: Dict[str, Any]) -> Dict[str, Any]:
        url = task.get("url")

        if not url:
            raise RuntimeError("url is required")

        page = self.manager.new_page()

        try:
            product = parse_product_from_page(page, url)

            return {
                "sku": product.sku,
                "title": product.title,
                "seller_name": product.seller_name,
                "brand": product.brand,
                "price_cents": product.price_cents,
                "currency": product.currency,
                "available": product.available,
                "is_active": product.is_active,
                "rating": product.rating,
                "reviews_count": product.reviews_count,
            }
        finally:
            page.close()

    def parse_product(self, url: str, timeout_seconds: int = 90) -> Dict[str, Any]:
        if self.startup_error is not None:
            raise RuntimeError(self.startup_error)

        result_queue: queue.Queue = queue.Queue(maxsize=1)

        self.task_queue.put(
            {
                "type": "product",
                "url": url,
                "result_queue": result_queue,
            }
        )

        try:
            return result_queue.get(timeout=timeout_seconds)
        except queue.Empty:
            raise TimeoutError(f"Ozon product parsing timed out after {timeout_seconds} seconds")

    def stop(self) -> None:
        self.stop_event.set()


_browser_worker: Optional[BrowserWorker] = None


def init_browser_worker(cookie_path: str) -> BrowserWorker:
    global _browser_worker

    if _browser_worker is None:
        _browser_worker = BrowserWorker(cookie_path=cookie_path)
        _browser_worker.start()

    return _browser_worker


def get_browser_worker() -> BrowserWorker | None:
    if _browser_worker is None:
        raise RuntimeError("Ozon browser worker is not initialized")

    return _browser_worker


def shutdown_browser_worker() -> None:
    if _browser_worker is not None:
        _browser_worker.stop()
