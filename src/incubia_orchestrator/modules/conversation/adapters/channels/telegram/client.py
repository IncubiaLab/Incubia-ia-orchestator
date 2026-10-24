import httpx


class TelegramTransportError(RuntimeError):
    def __init__(self, code: str, retry_after: int | None = None):
        super().__init__(code)
        self.code, self.retry_after = code, retry_after


class TelegramClient:
    def __init__(self, token: str, client: httpx.Client | None = None):
        if not token.strip():
            raise ValueError("Telegram token is required")
        self._base_url = f"https://api.telegram.org/bot{token}"
        self._client = client or httpx.Client(timeout=35)

    def get_me(self) -> dict:
        response = self._client.get(f"{self._base_url}/getMe")
        response.raise_for_status()
        data = response.json()
        if not data.get("ok") or not isinstance(data.get("result"), dict):
            raise TelegramTransportError("INVALID_RESPONSE")
        return data["result"]

    def get_webhook_info(self) -> dict:
        response = self._client.get(f"{self._base_url}/getWebhookInfo")
        response.raise_for_status()
        return response.json().get("result", {})

    def get_updates(self, offset: int | None = None) -> list[dict]:
        response = self._client.get(f"{self._base_url}/getUpdates", params={"offset": offset, "timeout": 30, "allowed_updates": '["message"]'})
        if response.status_code == 409:
            raise TelegramTransportError("POLLING_CONFLICT")
        response.raise_for_status()
        body = response.json()
        if not body.get("ok") or not isinstance(body.get("result"), list):
            raise RuntimeError("Telegram invalid response")
        return body["result"]

    def send_message(self, chat_id: str, text: str) -> str:
        try:
            response = self._client.post(f"{self._base_url}/sendMessage", json={"chat_id": chat_id, "text": text})
        except (httpx.ReadTimeout, httpx.ReadError, httpx.RemoteProtocolError):
            raise TelegramTransportError("UNKNOWN_EFFECT") from None
        except (httpx.ConnectError, httpx.ConnectTimeout):
            raise TelegramTransportError("RETRYABLE") from None
        if response.status_code == 429:
            try:
                seconds = response.json().get("parameters", {}).get("retry_after")
            except ValueError:
                seconds = None
            raise TelegramTransportError("RATE_LIMIT", seconds if isinstance(seconds, int) else None)
        if response.status_code >= 500:
            # A 5xx may follow a send Telegram already accepted: outcome is uncertain, never retried.
            raise TelegramTransportError("UNKNOWN_EFFECT")
        if response.status_code in (400, 403):
            raise TelegramTransportError("PERMANENT")
        response.raise_for_status()
        body = response.json()
        if not body.get("ok") or "message_id" not in body.get("result", {}):
            raise RuntimeError("Telegram invalid response")
        return str(body["result"]["message_id"])
