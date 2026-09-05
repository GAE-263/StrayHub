#!/usr/bin/env python3
"""Render reviewed public-tunnel contracts into ephemeral nginx/ngrok config."""

from __future__ import annotations

import argparse
import json
import re
import tempfile
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml  # type: ignore[import-untyped]

try:
    from scripts.public_tunnel_policy import (
        CompiledProfile,
        EffectiveRoute,
        PolicyError,
        RuntimeOrigin,
        compile_profile,
    )
except ModuleNotFoundError:  # Direct executable invocation puts scripts/ on sys.path.
    from public_tunnel_policy import (  # type: ignore[no-redef]
        CompiledProfile,
        EffectiveRoute,
        PolicyError,
        RuntimeOrigin,
        compile_profile,
    )

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class GeneratedRuntimeConfigs:
    profile: str
    nginx_path: Path
    traffic_policy_path: Path
    runtime_origin: RuntimeOrigin | None


def _nginx_method_guard(methods: tuple[str, ...]) -> str:
    expression = "|".join(re.escape(method) for method in methods)
    if len(methods) == 1:
        return f"if ($request_method != {methods[0]}) {{ return 404; }}"
    return f"if ($request_method !~ ^({expression})$) {{ return 404; }}"


def _nginx_location(route: EffectiveRoute) -> str:
    if route.path is not None:
        location = f"location = {route.path}"
    else:
        location = f'location ~ "{route.path_pattern}"'
    query_guard = (
        '\n            if ($is_args != "") { return 404; }'
        if route.query_policy == "reject_nonempty"
        else ""
    )
    return (
        f"        # allowlist: {route.id}\n"
        f"        {location} {{\n"
        f"            {_nginx_method_guard(route.methods)}{query_guard}\n"
        f"            proxy_pass http://strayhub_{route.upstream};\n"
        "        }"
    )


def render_nginx(
    profile: CompiledProfile,
    origin: RuntimeOrigin | None,
    *,
    api_port: int,
    web_port: int,
    gateway_port: int,
) -> str:
    locations = [_nginx_location(route) for route in profile.routes]
    locations.extend(
        (
            f"        # exact Next build asset\n"
            f"        location = {asset} {{\n"
            "            if ($request_method !~ ^(GET|HEAD)$) { return 404; }\n"
            "            proxy_pass http://strayhub_web;\n"
            "        }"
        )
        for asset in profile.exact_assets
    )
    if origin is None:
        server_name = "localhost"
        host_guard = ""
        profile_header = ""
    else:
        server_name = origin.hostname
        if origin.port is None:
            authority_pattern = re.escape(origin.hostname) + r"(?::443)?"
        else:
            authority_pattern = re.escape(origin.host)
        host_guard = f"        if ($http_host !~* ^{authority_pattern}$) {{ return 404; }}\n"
        profile_header = profile.name
    return f'''pid nginx.pid;
error_log logs/error.log notice;

events {{}}

http {{
    log_format strayhub_public_sensitive
        '$remote_addr $request_method $uri $status $body_bytes_sent '
        'rt=$request_time rid=$request_id';
    access_log logs/access.log strayhub_public_sensitive;

    map $http_upgrade $connection_upgrade {{
        default upgrade;
        "" close;
    }}

    upstream strayhub_api {{ server 127.0.0.1:{api_port}; }}
    upstream strayhub_web {{ server 127.0.0.1:{web_port}; }}

    server {{
        listen 127.0.0.1:{gateway_port};
        server_name {server_name};
{host_guard}
        if ($request_uri ~* "^/[^?]*(//|%2f|%5c|%2e|;)") {{ return 404; }}
        proxy_http_version 1.1;
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For "";
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-StrayHub-Trusted-Client-IP $http_x_strayhub_trusted_client_ip;
        proxy_set_header X-StrayHub-Public-Profile "{profile_header}";
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;

{chr(10).join(locations)}

        location / {{ return 404; }}
    }}
}}
'''


def render_traffic_policy(profile: CompiledProfile) -> str:
    headers = [
        "x-strayhub-trusted-client-ip",
        "x-strayhub-public-profile",
        "x-forwarded-for",
        "x-forwarded-proto",
    ]
    added = {
        "x-strayhub-trusted-client-ip": "${conn.client_ip}",
        "x-forwarded-proto": "https",
    }
    if profile.public_management:
        added["x-strayhub-public-profile"] = profile.name
    policy = {
        "on_http_request": [
            {"expressions": ['conn.client_ip == ""'], "actions": [{"type": "deny"}]},
            {
                "actions": [
                    {"type": "remove-headers", "config": {"headers": headers}},
                    {"type": "add-headers", "config": {"headers": added}},
                ]
            },
        ]
    }
    return yaml.safe_dump(policy, sort_keys=False)


def generate_runtime_configs(
    *,
    profile_name: str,
    output_dir: Path,
    api_port: int,
    web_port: int,
    gateway_port: int,
    build_dir: Path | None = None,
    runtime_origin: str | None = None,
    allow_loopback_for_test: bool = False,
) -> GeneratedRuntimeConfigs:
    output = output_dir.resolve()
    if output == ROOT or output.is_relative_to(ROOT):
        raise PolicyError("generated config must use an external runtime temporary directory")
    output.mkdir(parents=True, exist_ok=True)
    (output / "logs").mkdir(exist_ok=True)
    profile, origin = compile_profile(
        profile_name,
        build_dir=build_dir,
        runtime_origin=runtime_origin,
        allow_loopback_for_test=allow_loopback_for_test,
    )
    nginx_path = output / "public-tunnel.nginx.conf"
    traffic_policy_path = output / "public-tunnel.traffic-policy.yaml"
    nginx_path.write_text(
        render_nginx(
            profile,
            origin,
            api_port=api_port,
            web_port=web_port,
            gateway_port=gateway_port,
        )
    )
    traffic_policy_path.write_text(render_traffic_policy(profile))
    return GeneratedRuntimeConfigs(
        profile=profile.name,
        nginx_path=nginx_path,
        traffic_policy_path=traffic_policy_path,
        runtime_origin=origin,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="line-only")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--api-port", type=int, required=True)
    parser.add_argument("--web-port", type=int, required=True)
    parser.add_argument("--gateway-port", type=int, required=True)
    parser.add_argument("--build-dir", type=Path)
    parser.add_argument("--runtime-origin")
    parser.add_argument("--allow-loopback-for-test", action="store_true")
    args = parser.parse_args(argv)
    output_dir = args.output_dir or Path(tempfile.mkdtemp(prefix="strayhub-public-tunnel-"))
    try:
        result = generate_runtime_configs(
            profile_name=args.profile,
            output_dir=output_dir,
            api_port=args.api_port,
            web_port=args.web_port,
            gateway_port=args.gateway_port,
            build_dir=args.build_dir,
            runtime_origin=args.runtime_origin,
            allow_loopback_for_test=args.allow_loopback_for_test,
        )
    except (OSError, KeyError, TypeError, yaml.YAMLError, PolicyError) as exc:
        parser.error(str(exc))
    print(
        json.dumps(
            {
                "profile": result.profile,
                "nginx_config": str(result.nginx_path),
                "traffic_policy": str(result.traffic_policy_path),
                "runtime_origin": asdict(result.runtime_origin) if result.runtime_origin else None,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
