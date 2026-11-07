import pytest

from ct125_api.auth.current_user import parse_groups, user_from_claims
from ct125_api.domain.exceptions import NotAuthenticatedError


def test_user_from_access_token_claims():
    user = user_from_claims({"sub": "abc", "username": "guest", "cognito:groups": "[admin viewer]"})
    assert user.user_id == "abc"
    assert user.username == "guest"
    assert user.groups == ("admin", "viewer")
    assert user.belongs_to("admin")


def test_username_falls_back_to_sub():
    user = user_from_claims({"sub": "abc"})
    assert user.username == "abc"


def test_claims_without_sub_are_rejected():
    with pytest.raises(NotAuthenticatedError):
        user_from_claims({"username": "nobody"})


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, ()),
        ("[]", ()),
        ("[admin]", ("admin",)),
        ("[admin viewer]", ("admin", "viewer")),
        (["admin", "viewer"], ("admin", "viewer")),
    ],
)
def test_parse_groups(raw, expected):
    assert parse_groups(raw) == expected
