from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from scripts import sync_line_role_menus as menus
from scripts.line_menu_publication import PublicationError, ResourcePublisher


@pytest.mark.asyncio
async def test_legacy_apply_never_deletes_or_activates(monkeypatch, tmp_path):
    from services.api.app.infrastructure.line import messaging_api_adapter as adapter_module

    adapter = AsyncMock()
    adapter.list_rich_menus.return_value = [{"name": "strayhub-default", "richMenuId": "old-menu"}]
    adapter.create_rich_menu.return_value = "new-menu"
    monkeypatch.setattr(adapter_module, "LineMessagingApiAdapter", lambda: adapter)
    monkeypatch.setattr(adapter_module, "close_shared_line_client", AsyncMock())
    (tmp_path / "default.png").write_bytes(b"synthetic-image")
    definition = menus.load_role_definition(Path("infra/local/line-rich-menu-default.yaml"))
    try:
        await menus.apply({"default": definition}, tmp_path)
    except (TypeError, ValueError):
        # The compatibility entry must refuse calls without explicit identity/manifest.
        pass
    adapter.delete_rich_menu.assert_not_awaited()
    adapter.link_rich_menu.assert_not_awaited()


def test_production_api_passes_hub_id():
    import yaml

    compose = yaml.safe_load(Path("infra/gce/docker-compose.production.yml").read_text())
    assert compose["services"]["api"]["environment"]["LINE_RICH_MENU_ADOPTION_HUB_ID"] == (
        "${LINE_RICH_MENU_ADOPTION_HUB_ID:-}"
    )
    for name in ("worker", "celery-worker", "celery-beat"):
        assert "LINE_RICH_MENU_ADOPTION_HUB_ID" not in compose["services"][name]["environment"]


@pytest.fixture
def plan():
    definitions = menus.discover_definitions()
    return menus.publication_plan(
        {"default": definitions["default"]}, Path("infra/local/rich-menu-images")
    )


class FakeLine:
    """All requests terminate here; never reaches a real HTTP transport."""

    def __init__(self):
        self.resources = {"richmenu-old": {"name": "strayhub-default"}}
        self.images = {}
        self.calls = []
        self.fail_upload = False
        self.create_timeout = False
        self.persist_create = True
        self.bad_readback = False
        self.bot = "@synthetic"

    def handle(self, request):
        import json

        path = request.url.path.removeprefix("/v2/bot/")
        self.calls.append((request.method, path))
        if request.method == "GET" and path == "info":
            return httpx.Response(200, json={"basicId": self.bot, "userId": "synthetic-bot"})
        if request.method == "GET" and path == "richmenu/list":
            return httpx.Response(
                200,
                json={
                    "richmenus": [
                        {**value, "richMenuId": key} for key, value in self.resources.items()
                    ]
                },
            )
        if request.method == "POST" and path == "richmenu":
            rid = f"richmenu-new-{len(self.resources)}"
            if self.persist_create:
                self.resources[rid] = json.loads(request.content)
            if self.create_timeout:
                raise httpx.ReadTimeout("sensitive-upstream-detail")
            return httpx.Response(200, json={"richMenuId": rid})
        rid = path.split("/")[1]
        if path.endswith("/content"):
            if request.method == "POST":
                if self.fail_upload:
                    return httpx.Response(503, text="sensitive-upstream-detail")
                self.images[rid] = request.content
                return httpx.Response(200)
            content = self.images.get(rid)
            return (
                httpx.Response(404)
                if content is None
                else httpx.Response(200, content=b"mismatch" if self.bad_readback else content)
            )
        if request.method == "GET" and rid in self.resources:
            return httpx.Response(200, json={**self.resources[rid], "richMenuId": rid})
        raise AssertionError(f"Forbidden API: {request.method} {path}")


async def publish(fake, plan, path):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(fake.handle),
        headers={"Authorization": "Bearer synthetic-secret"},
    ) as client:
        return await ResourcePublisher(client).publish(plan, path, "@synthetic", "a" * 40)


@pytest.mark.asyncio
async def test_create_verify_resume_and_no_activation(plan, tmp_path):
    import json

    fake = FakeLine()
    manifest = tmp_path / "manifest.json"
    first = await publish(fake, plan, manifest)
    writes = [call for call in fake.calls if call[0] != "GET"]
    assert writes == [("POST", "richmenu"), ("POST", f"richmenu/{first['default']}/content")]
    second = await publish(fake, plan, manifest)
    assert second == first
    assert [call for call in fake.calls if call[0] != "GET"] == writes
    assert "richmenu-old" in fake.resources
    record = next(iter(json.loads(manifest.read_text())["resources"].values()))
    assert record["stage"] == "ready" and record["verified"]
    assert json.loads(manifest.read_text())["git_sha"] == "a" * 40
    assert "synthetic-secret" not in manifest.read_text()
    assert "synthetic-bot" not in manifest.read_text()


@pytest.mark.asyncio
async def test_publication_requires_immutable_source_identity(plan, tmp_path):
    fake = FakeLine()
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handle)) as client:
        publisher = ResourcePublisher(client)
        with pytest.raises(PublicationError, match="Git SHA"):
            await publisher.publish(plan, tmp_path / "manifest.json", "@synthetic", "short")
    assert fake.calls == []


@pytest.mark.asyncio
async def test_upload_failure_resumes_without_recreate(plan, tmp_path):
    fake = FakeLine()
    fake.fail_upload = True
    path = tmp_path / "manifest.json"
    with pytest.raises(PublicationError, match="HTTP 503") as error:
        await publish(fake, plan, path)
    assert "sensitive" not in str(error.value)
    fake.fail_upload = False
    await publish(fake, plan, path)
    assert fake.calls.count(("POST", "richmenu")) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("persisted", [True, False])
async def test_unknown_create_reconciles_without_retry(plan, tmp_path, persisted):
    fake = FakeLine()
    fake.create_timeout = True
    fake.persist_create = persisted
    path = tmp_path / "manifest.json"
    if persisted:
        await publish(fake, plan, path)
    else:
        with pytest.raises(PublicationError, match="unknown"):
            await publish(fake, plan, path)
    fake.create_timeout = False
    if persisted:
        await publish(fake, plan, path)
    else:
        with pytest.raises(PublicationError, match="unresolved"):
            await publish(fake, plan, path)
    assert fake.calls.count(("POST", "richmenu")) == 1


@pytest.mark.asyncio
async def test_image_mismatch_is_not_ready_or_overwritten(plan, tmp_path):
    import json

    fake = FakeLine()
    fake.bad_readback = True
    path = tmp_path / "manifest.json"
    for _ in range(2):
        with pytest.raises(PublicationError, match="image mismatch"):
            await publish(fake, plan, path)
    assert sum(method == "POST" and path.endswith("/content") for method, path in fake.calls) == 1
    assert not next(iter(json.loads(path.read_text())["resources"].values()))["verified"]


@pytest.mark.asyncio
async def test_wrong_bot_refuses_all_writes(plan, tmp_path):
    fake = FakeLine()
    fake.bot = "@different"
    with pytest.raises(PublicationError, match="identity mismatch"):
        await publish(fake, plan, tmp_path / "manifest.json")
    assert fake.calls == [("GET", "info")]


@pytest.mark.asyncio
async def test_ambiguous_matches_stop(plan, tmp_path):
    fake = FakeLine()
    fake.resources = {
        "richmenu-one": plan["default"]["definition"],
        "richmenu-two": plan["default"]["definition"],
    }
    with pytest.raises(PublicationError, match="ambiguous"):
        await publish(fake, plan, tmp_path / "manifest.json")
    assert all(method == "GET" for method, _ in fake.calls)


@pytest.mark.asyncio
async def test_existing_complete_content_reused_without_manifest(plan, tmp_path):
    fake = FakeLine()
    fake.resources["richmenu-existing"] = plan["default"]["definition"]
    fake.images["richmenu-existing"] = plan["default"]["image"]
    assert await publish(fake, plan, tmp_path / "manifest.json") == {"default": "richmenu-existing"}
    assert all(method == "GET" for method, _ in fake.calls)


def test_dry_run_never_constructs_client(monkeypatch, capsys):
    import sys

    monkeypatch.setattr(sys, "argv", ["menus"])

    def forbidden(*args, **kwargs):
        raise AssertionError("dry run must not construct network client")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    menus.main()
    assert "DRY RUN" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_partial_batch_keeps_completed_role(plan, tmp_path):
    import copy
    import json

    fake = FakeLine()
    other = copy.deepcopy(plan["default"])
    other["fingerprint"] = "synthetic-second-fingerprint"
    other["definition"]["name"] = "strayhub-volunteer-synthetic"
    batch = {**plan, "volunteer": other}
    original = fake.handle

    def fail_second(request):
        if request.method == "POST" and request.url.path.endswith("/richmenu-new-2/content"):
            fake.fail_upload = True
        return original(request)

    path = tmp_path / "manifest.json"
    async with httpx.AsyncClient(transport=httpx.MockTransport(fail_second)) as client:
        with pytest.raises(PublicationError):
            await ResourcePublisher(client).publish(batch, path, "@synthetic", "a" * 40)
    records = json.loads(path.read_text())["resources"]
    assert records[plan["default"]["fingerprint"]]["stage"] == "ready"
    fake.fail_upload = False
    await publish(fake, batch, path)
    assert fake.calls.count(("POST", "richmenu")) == 2


@pytest.mark.asyncio
async def test_definition_tampering_invalidates_ready(plan, tmp_path):
    import json

    fake = FakeLine()
    path = tmp_path / "manifest.json"
    result = await publish(fake, plan, path)
    fake.resources[result["default"]] = {"name": "different-definition"}
    fake.calls.clear()
    with pytest.raises(PublicationError, match="definition mismatch"):
        await publish(fake, plan, path)
    assert all(method == "GET" for method, _ in fake.calls)
    assert not next(iter(json.loads(path.read_text())["resources"].values()))["verified"]


@pytest.mark.asyncio
async def test_manifest_bot_mismatch_and_lock_fail_before_writes(plan, tmp_path):
    import fcntl
    import json

    fake = FakeLine()
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"schema": 1, "bot": {}, "resources": {}}))
    with pytest.raises(PublicationError, match="Manifest Bot"):
        await publish(fake, plan, path)
    assert all(method == "GET" for method, _ in fake.calls)
    fake.calls.clear()
    with path.with_suffix(".json.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(PublicationError, match="locked"):
            await publish(fake, plan, path)
    assert not fake.calls


def test_volunteer_has_two_equal_columns_and_no_checkin():
    doc = menus.discover_definitions()["volunteer"]
    areas = menus.to_line_rich_menu(doc)["areas"]
    assert [area["bounds"] for area in areas] == [
        {"x": 0, "y": 0, "width": 1250, "height": 1686},
        {"x": 1250, "y": 0, "width": 1250, "height": 1686},
    ]
    assert [area["action"]["data"] for area in areas] == [
        "action=walk_report",
        "action=back_to_default_menu",
    ]


@pytest.mark.asyncio
async def test_same_version_name_but_different_definition_is_not_reused(plan, tmp_path):
    import copy

    fake = FakeLine()
    old = copy.deepcopy(plan["default"]["definition"])
    old["chatBarText"] = "different"
    fake.resources["richmenu-old"] = old
    result = await publish(fake, plan, tmp_path / "manifest.json")
    assert result["default"] != "richmenu-old"
    assert fake.resources["richmenu-old"] == old


@pytest.mark.asyncio
async def test_upload_timeout_after_success_is_not_reuploaded(plan, tmp_path):
    fake = FakeLine()
    original = fake.handle

    def timeout_after_upload(request):
        response = original(request)
        if request.method == "POST" and request.url.path.endswith("/content"):
            raise httpx.ReadTimeout("sensitive-upstream-detail")
        return response

    path = tmp_path / "manifest.json"
    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout_after_upload)) as client:
        with pytest.raises(PublicationError, match="unknown"):
            await ResourcePublisher(client).publish(plan, path, "@synthetic", "a" * 40)
    await publish(fake, plan, path)
    assert sum(method == "POST" and path.endswith("/content") for method, path in fake.calls) == 1
