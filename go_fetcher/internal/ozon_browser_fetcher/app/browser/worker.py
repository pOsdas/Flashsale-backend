import queue
import threading
import traceback
from typing import Any, Dict, List, Optional

from ozon_browser_fetcher.app.browser.manager import BrowserManager
from ozon_browser_fetcher.app.models.product import Product
from ozon_browser_fetcher.app.parsers.category_parser import parse_category_from_page
from ozon_browser_fetcher.app.parsers.product_parser import parse_product_from_page
from ozon_browser_fetcher.app.parsers.search_parser import parse_search_from_page


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
                elif task_type == "search":
                    result = self._handle_search(task)
                elif task_type == "category":
                    result = self._handle_category(task)
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
        url = str(task.get("url") or "").strip()

        if not url:
            raise RuntimeError("url is required")

        page = self.manager.new_page()

        try:
            product = parse_product_from_page(page, url)

            return product_to_dict(product)
        finally:
            page.close()

    def _handle_search(self, task: Dict[str, Any]) -> List[Dict[str, Any]]:
        query = str(task.get("query") or "").strip()
        limit = int(task.get("limit") or 10)

        if not query:
            raise RuntimeError("query is required")

        page = self.manager.new_page()

        try:
            products = parse_search_from_page(
                page=page,
                query=query,
                limit=limit,
            )

            return products_to_dicts(products)
        finally:
            page.close()

    def _handle_category(self, task: Dict[str, Any]) -> List[Dict[str, Any]]:
        url = str(task.get("url") or "").strip()
        limit = int(task.get("limit") or 10)

        if not url:
            raise RuntimeError("url is required")

        page = self.manager.new_page()

        try:
            products = parse_category_from_page(
                page=page,
                url=url,
                limit=limit,
            )

            return products_to_dicts(products)
        finally:
            page.close()

    def submit_task(self, task: Dict[str, Any], timeout_seconds: int = 90) -> Dict[str, Any]:
        if self.startup_error is not None:
            raise RuntimeError(self.startup_error)

        result_queue: queue.Queue = queue.Queue(maxsize=1)
        task["result_queue"] = result_queue

        self.task_queue.put(task)

        try:
            return result_queue.get(timeout=timeout_seconds)
        except queue.Empty:
            task_type = task.get("type", "unknown")
            raise TimeoutError(f"Ozon browser task timed out: type={task_type}, timeout={timeout_seconds}")

    def parse_product(self, url: str, timeout_seconds: int = 90) -> Dict[str, Any]:
        return self.submit_task(
            task={
                "type": "product",
                "url": url,
            },
            timeout_seconds=timeout_seconds,
        )

    def parse_search(self, query: str, limit: int = 10, timeout_seconds: int = 90) -> Dict[str, Any]:
        return self.submit_task(
            task={
                "type": "search",
                "query": query,
                "limit": limit,
            },
            timeout_seconds=timeout_seconds,
        )

    def parse_category(self, url: str, limit: int = 10, timeout_seconds: int = 90) -> Dict[str, Any]:
        return self.submit_task(
            task={
                "type": "category",
                "url": url,
                "limit": limit,
            },
            timeout_seconds=timeout_seconds,
        )

    def stop(self) -> None:
        self.stop_event.set()


def product_to_dict(product: Product) -> Dict[str, Any]:
    return {
        "external_id": product.sku,
        "sku": product.sku,
        "title": product.title,
        "seller_name": product.seller_name,
        "brand": product.brand,
        "price_cents": product.price_cents,
        "old_price_cents": product.old_price_cents,
        "currency": product.currency,
        "is_available": product.available > 0,
        "available": product.available,
        "is_active": product.is_active,
        "rating": product.rating,
        "reviews_count": product.reviews_count,
        "url": product.url,
        "product_path": product.product_path,
    }


def products_to_dicts(products: List[Product]) -> List[Dict[str, Any]]:
    return [
        product_to_dict(product)
        for product in products
    ]


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
