"""The three read/delete chat routes, over the real app with a real Firebase credential.

The list/get/delete cases this module carried all seeded rows through `e2e.conftest.create_chat`
and then asserted a served response. Both halves are unavailable in Phase 35: `create_chat` still
inserts the v1.6 `User(jwt_sub=...)` shape that the v2.0 schema dropped (plan 05 repairs it), and
the e2e Firebase subject has no `core.external_identities` row for the barrier to resolve (plan 06
adds `seed_identity`). They are named in 35-04-SUMMARY.md for plan 11 to restore.

Together with `test_chats.py` this covers all five chat routes exactly once: no route is asserted
twice, and none is left unasserted.
"""
from uuid import uuid4

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio(loop_scope="module")
class TestUnadmittedCallerIsRefused:
    async def test_list_chats_is_refused(self, async_client):
        response = await async_client.get("/chats")
        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}

    async def test_get_messages_is_refused(self, async_client):
        response = await async_client.get(f"/chats/{uuid4()}")
        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}

    async def test_delete_chat_is_refused(self, async_client):
        response = await async_client.delete(f"/chats/{uuid4()}")
        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}
