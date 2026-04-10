from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import httpx

from bot.config import Config


class XUIError(RuntimeError):
    pass


@dataclass
class XUIClientData:
    uuid: str
    email: str
    expiry_ms: int


class XUIClient:
    def __init__(self, config: Config) -> None:
        self.config = config
        self._http = httpx.AsyncClient(
            base_url=config.xui_base_url,
            timeout=20.0,
            follow_redirects=True,
        )
        self._authenticated = False

    async def close(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        response = await self._http.request(method, endpoint, **kwargs)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and data.get("success") is False:
            raise XUIError(data.get("msg", "X-UI API returned success=false"))
        return data

    async def login(self) -> None:
        if self._authenticated:
            return
        payload = {
            "username": self.config.xui_username,
            "password": self.config.xui_password,
        }
        await self._request("POST", self.config.xui_login_endpoint, data=payload)
        self._authenticated = True

    async def _ensure_login(self) -> None:
        if not self._authenticated:
            await self.login()

    async def _post_with_fallbacks(
        self,
        endpoints: list[str],
        payload_json: dict[str, Any] | None = None,
        payload_form: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        last_exc: Exception | None = None
        for endpoint in endpoints:
            try:
                if payload_json is not None:
                    return await self._request("POST", endpoint, json=payload_json)
                if payload_form is not None:
                    return await self._request("POST", endpoint, data=payload_form)
                return await self._request("POST", endpoint)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                continue
        raise XUIError(f"All X-UI endpoints failed: {endpoints}. Last error: {last_exc}")

    async def add_client(self, client: XUIClientData) -> None:
        await self._ensure_login()
        payload = {
            "id": self.config.xui_inbound_id,
            "settings": json.dumps(
                {
                    "clients": [
                        {
                            "id": client.uuid,
                            "email": client.email,
                            "enable": True,
                            "expiryTime": client.expiry_ms,
                            "limitIp": 0,
                            "totalGB": 0,
                            "subId": secrets.token_hex(8),
                            "tgId": "",
                            "reset": 0,
                        }
                    ]
                }
            ),
        }
        await self._request("POST", self.config.xui_add_client_endpoint, json=payload)

    async def update_client_expiry(self, client_id: str, email: str, expiry_ms: int) -> None:
        await self._ensure_login()
        payload = {
            "id": self.config.xui_inbound_id,
            "settings": json.dumps(
                {
                    "clients": [
                        {
                            "id": client_id,
                            "email": email,
                            "enable": True,
                            "expiryTime": expiry_ms,
                            "limitIp": 0,
                            "totalGB": 0,
                            "tgId": "",
                            "reset": 0,
                        }
                    ]
                }
            ),
        }
        endpoints = [
            self.config.xui_update_client_endpoint.format(
                client_id=client_id,
                inbound_id=self.config.xui_inbound_id,
                sub_id=client_id,
            ),
            f"/panel/api/inbounds/updateClient/{client_id}",
            f"/panel/api/inbounds/updateClientInbounds/{client_id}",
        ]
        await self._post_with_fallbacks(endpoints=endpoints, payload_json=payload)

    async def delete_client(self, client_id: str) -> None:
        await self._ensure_login()
        endpoints = [
            self.config.xui_delete_client_endpoint.format(
                client_id=client_id,
                inbound_id=self.config.xui_inbound_id,
                sub_id=client_id,
            ),
            f"/panel/api/inbounds/delClient/{client_id}",
            f"/panel/api/inbounds/{self.config.xui_inbound_id}/delClient/{client_id}",
        ]
        payload = {"id": self.config.xui_inbound_id, "clientId": client_id}
        await self._post_with_fallbacks(endpoints=endpoints, payload_json=payload)

    @staticmethod
    def build_client(email: str, expiry_at: datetime, forced_uuid: str | None = None) -> XUIClientData:
        uuid = forced_uuid or str(uuid4())
        expiry_ms = int(expiry_at.timestamp() * 1000)
        return XUIClientData(uuid=uuid, email=email, expiry_ms=expiry_ms)

    def render_key(self, uuid: str, xui_email: str) -> str:
        host = self.config.vpn_host or self.config.xui_base_url.replace("https://", "").replace("http://", "")
        path_q = quote(self.config.vless_xhttp_path, safe="")
        sni = self.config.vless_reality_sni or host
        tls_sni = self.config.vless_tls_sni or host
        xhttp_host = self.config.vless_xhttp_host or tls_sni
        kwargs = {
            "uuid": uuid,
            "vpn_host": host,
            "vpn_port": self.config.vpn_port,
            "xui_email": xui_email,
            "vless_path_q": path_q,
            "xhttp_mode": self.config.vless_xhttp_mode,
            "tls_sni": tls_sni,
            "xhttp_host": xhttp_host,
            "reality_pbk": self.config.vless_reality_pbk,
            "reality_sid": self.config.vless_reality_sid,
            "reality_sni": sni,
            "reality_fp": self.config.vless_reality_fp,
        }
        used = set(re.findall(r"\{(\w+)\}", self.config.key_template))
        return self.config.key_template.format(**{k: v for k, v in kwargs.items() if k in used})

    @staticmethod
    def now_utc() -> datetime:
        return datetime.now(UTC)
