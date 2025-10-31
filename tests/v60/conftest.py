import httpx
import pytest

from bankid_sdk import AsyncV60, SyncV60


@pytest.fixture
def async_v60(mocked_async_client: httpx.AsyncClient) -> AsyncV60:
    return AsyncV60(client=mocked_async_client)


@pytest.fixture
def sync_v60(mocked_sync_client: httpx.Client) -> SyncV60:
    return SyncV60(client=mocked_sync_client)
