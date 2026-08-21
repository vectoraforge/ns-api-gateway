from nativespeaker.api.models import SubscriptionPlan, User

# `GET /users/me` is deleted under D-16: it read `user.name`, `user.subscription_plan`, and
# `UsageDB`, all three of which the v2.0 schema dropped, so it could not serve unchanged and is
# rewritten from scratch in Phase 39. The six cases that exercised it went with it -- see
# 35-04-SUMMARY.md for the list.
#
# USER-01's identity value object is now `VerifiedClaims`, carrying only the verified (iss, sub).
# Its coverage lives beside the verification rules, in test_jwt_security.py::TestVerifiedClaims.


class TestUserModel:
    """USER-01: User model defaults and constraints."""

    def test_default_plan_is_free(self):
        user = User(jwt_sub="test", email="test@example.com")
        assert user.subscription_plan == SubscriptionPlan.free

    def test_default_active_is_true(self):
        user = User(jwt_sub="test", email="test@example.com")
        assert user.active is True

    def test_uuid7_id_generated(self):
        user = User(jwt_sub="test", email="test@example.com")
        assert user.id is not None

    def test_subscription_plan_values(self):
        assert list(SubscriptionPlan) == [SubscriptionPlan.free, SubscriptionPlan.silver,
                                          SubscriptionPlan.gold, SubscriptionPlan.platinum]
