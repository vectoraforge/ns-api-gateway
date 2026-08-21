"""The three read/delete chat routes, over the real app with a real Firebase credential.

The list/get/delete cases this module carried all seeded rows through `e2e.conftest.create_chat`
and then asserted a served response. They are named in 35-04-SUMMARY.md for plan 11 to restore;
what stands here is the refusal half, which plan 06 sharpened from `auth_required` to §1.3's
outcome 1'. See `test_chats.py`'s module docstring for why the class change is a strengthening
rather than a regression: the e2e Firebase subject is a *verified* subject with no
`core.external_identities` row, which is exactly what `preauth_identity_not_allowed` names.

Together with `test_chats.py` this covers all five chat routes exactly once: no route is asserted
twice, and none is left unasserted.
"""
from uuid import uuid4

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio(loop_scope="module")
class TestUnlinkedCallerIsRefused:
    async def test_list_chats_is_refused(self, async_client):
        response = await async_client.get("/chats")
        assert response.status_code == 403
        assert response.json() == {"code": "preauth_identity_not_allowed"}

    async def test_get_messages_is_refused(self, async_client):
        response = await async_client.get(f"/chats/{uuid4()}")
        assert response.status_code == 403
        assert response.json() == {"code": "preauth_identity_not_allowed"}

    async def test_delete_chat_is_refused(self, async_client):
        response = await async_client.delete(f"/chats/{uuid4()}")
        assert response.status_code == 403
        assert response.json() == {"code": "preauth_identity_not_allowed"}
