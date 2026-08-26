import asyncio
import json
import time
from urllib.parse import parse_qs

import httpx
import pytest
from services.api.app.domain.moa_import import (
    normalize,
    normalize_official_name,
    parse_name_detail,
    select_records,
)
from services.api.app.infrastructure.moa_open_data import DETAIL_URL, MoaOpenDataClient
from tests.unit.test_moa_import import record


def response(name="  歪歪\u00a0 15M029  ", **changes):
    return {
        "Success": True,
        "Message": json.dumps(
            [
                {
                    "收容編號": "AAACG455402",
                    "公告收容所": record()["shelter_name"],
                    "動物名": name,
                    "AnimalName": name,
                    **changes,
                }
            ]
        ),
    }


@pytest.mark.parametrize(
    "value,expected",
    [
        ("  歪歪\u00a0 15M029  ", "歪歪 15M029"),
        ("皮皮7F037", "皮皮7F037"),
        ("來福", "來福"),
        ("麻薯", "麻薯"),
        ("賽巴斯汀(小霸王)11M001(10M098)", "賽巴斯汀(小霸王)11M001(10M098)"),
        (None, None),
        ("", None),
        (" \n\u00a0 ", None),
        ("---", None),
    ],
)
def test_whitespace_only_normalization_and_official_empty(value, expected):
    assert normalize_official_name(value) == expected


def test_detail_validates_identity_before_accepting_entire_name():
    value = parse_name_detail(response(), normalize(record()))
    assert value.normalized_name == "歪歪 15M029"
    assert value.raw_name == "  歪歪\u00a0 15M029  "
    assert value.error_code is None


@pytest.mark.parametrize(
    "payload",
    [
        {"Success": False, "Message": "[]"},
        {"Success": True, "Message": "not json"},
        {"Success": True, "Message": "[]"},
        {"Success": True, "Message": "{}"},
        response(**{"收容編號": "FOREIGN"}),
        response(**{"公告收容所": "其他收容所"}),
        response(AnimalName="different"),
        response(name=123),
        response(name="x" * 201),
        response(name=" " * 1025),
        response(name="a\x00b"),
    ],
)
def test_bad_detail_is_not_treated_as_empty(payload):
    with pytest.raises(ValueError):
        parse_name_detail(payload, normalize(record()))


async def test_fixed_endpoint_official_tag_lookup_no_cookie_and_failure_isolation(monkeypatch):
    calls = []

    def reply(request):
        assert str(request.url) == DETAIL_URL
        assert "cookie" not in request.headers
        body = parse_qs(request.content.decode())
        assert body["Method"] == ["AnimalsFront"]
        payload = json.loads(body["Param"][0])
        calls.append(payload)
        if payload["action"] == "AnimalsGetShelter":
            return httpx.Response(
                200,
                json={
                    "Success": True,
                    "Message": json.dumps(
                        [{"ShelterName": record()["shelter_name"], "UserTag": "NOT_A_PREFIX"}]
                    ),
                },
                headers={"set-cookie": "session=test"},
            )
        assert payload["_FrontParam"]["Shelter"] == "NOT_A_PREFIX"
        if payload["_FrontParam"]["AcNum"] == "AAACG455403":
            return httpx.Response(200, content=b"bad json")
        return httpx.Response(200, json=response())

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(reply), cookies={"old": "value"}
    ) as http:
        client = MoaOpenDataClient(http)
        monkeypatch.setattr(client, "_detail_interval", 0)
        batch = select_records(
            [record(), record(455403)], shelter=record()["shelter_name"], kind="dog", limit=60
        )
        names = await client.fetch_names(batch)
    assert names["455402"].normalized_name == "歪歪 15M029"
    assert names["455403"].error_code
    assert client.name_detail_requests == 2
    assert len(calls) == 3


@pytest.mark.parametrize("mode", ["timeout", "redirect", "oversize"])
async def test_detail_transport_is_bounded_and_never_follows_redirect(mode, monkeypatch):
    calls = []

    def reply(request):
        calls.append(request)
        if mode == "timeout":
            raise httpx.ReadTimeout("secret upstream error")
        if mode == "redirect":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})
        return httpx.Response(200, content=b"x" * 65537)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(reply), follow_redirects=True
    ) as http:
        client = MoaOpenDataClient(http)
        monkeypatch.setattr(client, "_detail_interval", 0)
        with pytest.raises(ValueError, match="^name_[a-z_]+$"):
            await client._post_detail("AnnounceMentDataDetail", {"_FrontParam": {}})
    assert len(calls) == (3 if mode == "timeout" else 1)


async def test_detail_workers_share_rate_limit_and_max_two_inflight(monkeypatch):
    starts = []
    inflight = 0
    maximum = 0

    async def reply(request):
        nonlocal inflight, maximum
        payload = json.loads(parse_qs(request.content.decode())["Param"][0])
        starts.append(time.monotonic())
        inflight += 1
        maximum = max(maximum, inflight)
        await asyncio.sleep(0.025)
        inflight -= 1
        if payload["action"] == "AnimalsGetShelter":
            return httpx.Response(
                200,
                json={
                    "Success": True,
                    "Message": json.dumps(
                        [{"ShelterName": record()["shelter_name"], "UserTag": "AAACG"}]
                    ),
                },
            )
        return httpx.Response(200, json=response(**{"收容編號": payload["_FrontParam"]["AcNum"]}))

    async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as http:
        client = MoaOpenDataClient(http)
        assert client._detail_interval == 0.5
        monkeypatch.setattr(client, "_detail_interval", 0.01)
        batch = select_records(
            [record(i) for i in range(1, 5)], shelter=record()["shelter_name"], kind="dog", limit=60
        )
        names = await client.fetch_names(batch)
    assert len(names) == 4 and all(n.error_code is None for n in names.values())
    assert maximum == 2
    assert all(b - a >= 0.009 for a, b in zip(starts, starts[1:], strict=False))


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {"Success": True, "Message": "null"},
        {
            "Success": True,
            "Message": json.dumps(
                [{"收容編號": "AAACG455402", "公告收容所": record()["shelter_name"]}]
            ),
        },
    ],
)
def test_missing_field_or_malformed_envelope_fails_closed(payload):
    with pytest.raises(ValueError, match="name_invalid_response"):
        parse_name_detail(payload, normalize(record()))
