import logging
from abc import ABC, abstractmethod

import httpx

logger = logging.getLogger(__name__)

_HA_API = "http://supervisor/core/api"


class HAClient(ABC):
    @abstractmethod
    async def add_item(self, label: str) -> bool: ...


class SupervisorAdapter(HAClient):
    def __init__(self, token: str) -> None:
        self._token = token

    async def add_item(self, label: str) -> bool:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(
                    f"{_HA_API}/services/todo/add_item",
                    json={"entity_id": "todo.einkaufsliste", "item": label},
                    headers=headers,
                )
                if resp.status_code == 404:
                    resp = await client.post(
                        f"{_HA_API}/services/shopping_list/add_item",
                        json={"name": label},
                        headers=headers,
                    )
                resp.raise_for_status()
                return True
            except Exception as e:
                logger.warning("HA add_item failed for %r: %s", label, e)
                return False


class NoopAdapter(HAClient):
    async def add_item(self, label: str) -> bool:
        logger.debug("NoopAdapter.add_item (dev/test): %s", label)
        return True
