"""Minimal TCP ingress for the isolated local staging runtime.

The proxy container is the only staging service attached to the non-internal
ingress network. It carries no application configuration or secrets.
"""

from __future__ import annotations

import asyncio


async def _copy(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while chunk := await reader.read(64 * 1024):
            writer.write(chunk)
            await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        writer.close()


async def _proxy(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    *,
    upstream_host: str,
    upstream_port: int,
) -> None:
    try:
        upstream_reader, upstream_writer = await asyncio.open_connection(
            upstream_host, upstream_port
        )
    except OSError:
        client_writer.close()
        await client_writer.wait_closed()
        return
    await asyncio.gather(
        _copy(client_reader, upstream_writer),
        _copy(upstream_reader, client_writer),
    )


async def main() -> None:
    api = await asyncio.start_server(
        lambda reader, writer: _proxy(reader, writer, upstream_host="api", upstream_port=8080),
        "0.0.0.0",
        8081,
    )
    web = await asyncio.start_server(
        lambda reader, writer: _proxy(reader, writer, upstream_host="web", upstream_port=8080),
        "0.0.0.0",
        8080,
    )
    async with api, web:
        await asyncio.gather(api.serve_forever(), web.serve_forever())


if __name__ == "__main__":
    asyncio.run(main())
