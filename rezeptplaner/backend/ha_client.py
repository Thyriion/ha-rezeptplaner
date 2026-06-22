import logging
from abc import ABC, abstractmethod

import httpx

logger = logging.getLogger(__name__)

_HA_API = "http://supervisor/core/api"

_TODO_ENTITIES = [
    "todo.einkaufsliste",
    "todo.shopping_list",
    "todo.einkaufen",
]


class HAClient(ABC):
    @abstractmethod
    async def add_item(self, label: str) -> bool: ...


class SupervisorAdapter(HAClient):
    def __init__(self, token: str) -> None:
        self._token = token
        self._headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    async def _try_todo(self, client: httpx.AsyncClient, entity_id: str, label: str) -> bool:
        try:
            resp = await client.post(
                f"{_HA_API}/services/todo/add_item",
                json={"entity_id": entity_id, "item": label},
                headers=self._headers,
            )
            if resp.status_code < 400:
                return True
            logger.debug("todo.add_item %s → %s", entity_id, resp.status_code)
        except Exception as e:
            logger.debug("todo.add_item %s exception: %s", entity_id, e)
        return False

    async def _try_shopping_list(self, client: httpx.AsyncClient, label: str) -> bool:
        try:
            resp = await client.post(
                f"{_HA_API}/services/shopping_list/add_item",
                json={"name": label},
                headers=self._headers,
            )
            if resp.status_code < 400:
                return True
            logger.debug("shopping_list.add_item → %s", resp.status_code)
        except Exception as e:
            logger.debug("shopping_list.add_item exception: %s", e)
        return False

    async def add_item(self, label: str) -> bool:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for entity_id in _TODO_ENTITIES:
                if await self._try_todo(client, entity_id, label):
                    return True
            if await self._try_shopping_list(client, label):
                return True
        logger.warning("All HA methods failed for item %r", label)
        return False


class NoopAdapter(HAClient):
    async def add_item(self, label: str) -> bool:
        logger.debug("NoopAdapter.add_item (dev/test): %s", label)
        return True
