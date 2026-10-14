from copy import deepcopy

import pytest
from auth_helpers import mutate, register_login
from pydantic import ValidationError
from sqlalchemy import delete, select

from app.modules.authorization.models import Permission, RolePermission
from app.modules.preferences.schemas import PreferenceInput


def payload(name="My profile"):
    return {
        "name": name,
        "criteria": {
            "preferred_skills": ["C++", "C#", "CI/CD"],
            "required_skills": ["Python"],
            "weights": {
                "skills": 100,
                "title": 0,
                "location": 0,
                "experience": 0,
                "employment": 0,
                "keywords": 0,
            },
        },
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"required_skills": ["c++"]},
        {"preferred_skills": ["C++", " c++ "]},
        {"excluded_keywords": ["PYTHON"]},
        {"excluded_keywords": ["c#"]},
        {"preferred_keywords": ["growth"], "excluded_keywords": ["Growth"]},
        {"job_titles": ["Engineer"], "excluded_keywords": ["engineer"]},
        {"locations": [""]},
        {"locations": ["a" * 101]},
        {"locations": [str(i) for i in range(51)]},
        {"experience_min_months": 25, "experience_max_months": 24},
        {"experience_min_months": -1},
        {"experience_max_months": 1201},
        {"experience_min_months": True},
        {"experience_max_months": "24"},
        {"remote_policy": "sometimes"},
        {"unknown": "value"},
    ],
)
def test_invalid_preferences(changes):
    data = payload()
    data["criteria"].update(changes)
    with pytest.raises(ValidationError):
        PreferenceInput.model_validate(data)


@pytest.mark.parametrize("value", [-1, 101, 99, 0, 1.5, True, "100", float("inf"), float("nan")])
def test_invalid_weights(value):
    data = payload()
    data["criteria"]["weights"]["skills"] = value
    with pytest.raises(ValidationError):
        PreferenceInput.model_validate(data)


def test_weight_contract_and_total_list_bound():
    data = payload()
    del data["criteria"]["weights"]["title"]
    with pytest.raises(ValidationError):
        PreferenceInput.model_validate(data)
    data = payload()
    data["criteria"]["weights"]["unknown"] = 0
    with pytest.raises(ValidationError):
        PreferenceInput.model_validate(data)
    data = payload()
    data["criteria"].update(preferred_skills=[], required_skills=[])
    with pytest.raises(ValidationError):
        PreferenceInput.model_validate(data)
    data = payload()
    for field in (
        "preferred_keywords",
        "job_titles",
        "seniority_preferences",
        "locations",
        "employment_types",
    ):
        data["criteria"][field] = [f"{field}{i}" for i in range(50)]
    with pytest.raises(ValidationError):
        PreferenceInput.model_validate(data)


def test_unicode_punctuation_remote_regions_and_experience():
    data = payload("  Unicode   profile  ")
    data["criteria"].update(
        locations=["Île-de-France"],
        remote_policy="remote_only",
        experience_min_months=0,
        experience_max_months=24,
    )
    result = PreferenceInput.model_validate(data)
    assert result.name == "Unicode profile"
    assert result.criteria.preferred_skills == ["C++", "C#", "CI/CD"]
    data["criteria"]["preferred_skills"] = ["Ｐｙｔｈｏｎ"]
    with pytest.raises(ValidationError):
        PreferenceInput.model_validate(data)


@pytest.mark.integration
async def test_preference_crud_multiple_profiles_and_weights(api):
    client, _ = api
    await register_login(client)
    first = await mutate(client, "POST", "/preferences", payload())
    assert first.status_code == 201, first.text
    second = await mutate(client, "POST", "/preferences", payload("Other profile"))
    assert second.status_code == 201
    assert (
        await mutate(client, "POST", "/preferences", payload(" MY   PROFILE "))
    ).status_code == 409
    path = f"/preferences/{first.json()['id']}"
    data = payload("Edited")
    data["criteria"]["weights"].update(skills=60, location=40)
    data["criteria"]["remote_policy"] = "remote_only"
    updated = await mutate(client, "PUT", path, data)
    assert updated.status_code == 200
    assert (await client.get("/api/v1" + path)).json()["criteria"]["weights"]["location"] == 40
    invalid = deepcopy(data)
    invalid["criteria"]["weights"]["skills"] = 0
    response = await mutate(client, "PUT", path, invalid)
    assert response.status_code == 422
    assert response.json()["error"]["issues"][0]["code"] == "weight_total"
    assert (await client.get("/api/v1" + path)).json()["name"] == "Edited"
    page = (await client.get("/api/v1/preferences?limit=1")).json()
    assert page["next_offset"] == 1 and "criteria" not in page["items"][0]
    assert (await mutate(client, "DELETE", path)).status_code == 204
    assert (await client.get("/api/v1" + path)).status_code == 404
    assert (await client.get("/api/v1/preferences/" + second.json()["id"])).json()[
        "name"
    ] == "Other profile"


@pytest.mark.integration
async def test_preference_isolation_permission_and_csrf(api):
    client, app = api
    assert (await client.get("/api/v1/preferences")).status_code == 401
    await register_login(client)
    response = await mutate(client, "POST", "/preferences", payload())
    path = "/preferences/" + response.json()["id"]
    assert (await client.put("/api/v1" + path, json=payload())).status_code == 403
    client.cookies.clear()
    await register_login(client, "other@example.com")
    assert (await client.get("/api/v1/preferences")).json()["items"] == []
    assert (await client.get("/api/v1" + path)).status_code == 404
    assert (await mutate(client, "PUT", path, payload())).status_code == 404
    assert (await mutate(client, "DELETE", path)).status_code == 404
    assert (
        await mutate(client, "POST", "/preferences", {**payload(), "user_id": "injected"})
    ).status_code == 422
    assert (await mutate(client, "POST", "/preferences", payload())).status_code == 201
    async with app.state.database.sessions() as db, db.begin():
        permission = await db.scalar(
            select(Permission.id).where(Permission.code == "preferences:read:self")
        )
        await db.execute(delete(RolePermission).where(RolePermission.permission_id == permission))
    assert (await client.get("/api/v1/preferences")).status_code == 403


@pytest.mark.integration
@pytest.mark.parametrize("action", ["read", "create", "update", "delete"])
async def test_each_preference_permission_is_enforced(api, action):
    client, app = api
    await register_login(client)
    created = await mutate(client, "POST", "/preferences", payload())
    path = "/preferences/" + created.json()["id"]
    async with app.state.database.sessions() as db, db.begin():
        permission = await db.scalar(
            select(Permission.id).where(Permission.code == f"preferences:{action}:self")
        )
        await db.execute(delete(RolePermission).where(RolePermission.permission_id == permission))
    if action == "read":
        assert (await client.get("/api/v1/preferences")).status_code == 403
        assert (await client.get("/api/v1" + path)).status_code == 403
    else:
        method, target = {
            "create": ("POST", "/preferences"),
            "update": ("PUT", path),
            "delete": ("DELETE", path),
        }[action]
        assert (await mutate(client, method, target, payload())).status_code == 403
