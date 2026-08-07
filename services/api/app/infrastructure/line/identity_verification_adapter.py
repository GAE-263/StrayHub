import httpx


class LineIdentityVerifier:
    def __init__(self, channel_id: str, *, client: httpx.AsyncClient | None = None) -> None:
        self.channel_id = channel_id
        self.client = client

    async def verify(self, token: str) -> str:
        if not token:
            raise ValueError("LINE identity token is required")
        client = self.client or httpx.AsyncClient()
        response = await client.get(
            "https://api.line.me/oauth2/v2.1/verify",
            params={"id_token": token, "client_id": self.channel_id},
        )
        if self.client is None:
            await client.aclose()
        response.raise_for_status()
        user_id = response.json().get("sub")
        if not user_id:
            raise ValueError("LINE identity response has no user id")
        return user_id
