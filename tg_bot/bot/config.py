from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: set[int]
    database_path: Path
    subscription_periods: list[int]
    grace_period_days: int
    cleanup_interval_minutes: int
    xui_base_url: str
    xui_username: str
    xui_password: str
    xui_inbound_id: int
    xui_login_endpoint: str
    xui_get_inbound_endpoint: str
    xui_add_client_endpoint: str
    xui_update_client_endpoint: str
    xui_delete_client_endpoint: str
    key_template: str
    vpn_host: str
    vpn_port: int


def _parse_admin_ids(raw: str) -> set[int]:
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        ids.add(int(part))
    return ids


def _parse_periods(raw: str) -> list[int]:
    result = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        result.append(int(part))
    return sorted(set(result))


def load_config() -> Config:
    load_dotenv()

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise ValueError("BOT_TOKEN is required in .env")

    admin_ids_raw = os.getenv("ADMIN_IDS", "").strip()
    if not admin_ids_raw:
        raise ValueError("ADMIN_IDS is required in .env")

    subscription_periods = _parse_periods(os.getenv("SUBSCRIPTION_PERIODS", "30,90,180,365"))
    if not subscription_periods:
        raise ValueError("SUBSCRIPTION_PERIODS must contain at least one period")

    return Config(
        bot_token=bot_token,
        admin_ids=_parse_admin_ids(admin_ids_raw),
        database_path=Path(os.getenv("DATABASE_PATH", "bot.db")),
        subscription_periods=subscription_periods,
        grace_period_days=int(os.getenv("GRACE_PERIOD_DAYS", "3")),
        cleanup_interval_minutes=int(os.getenv("CLEANUP_INTERVAL_MINUTES", "30")),
        xui_base_url=os.getenv("XUI_BASE_URL", "").rstrip("/"),
        xui_username=os.getenv("XUI_USERNAME", ""),
        xui_password=os.getenv("XUI_PASSWORD", ""),
        xui_inbound_id=int(os.getenv("XUI_INBOUND_ID", "1")),
        xui_login_endpoint=os.getenv("XUI_LOGIN_ENDPOINT", "/login"),
        xui_get_inbound_endpoint=os.getenv(
            "XUI_GET_INBOUND_ENDPOINT", "/panel/api/inbounds/get/{inbound_id}"
        ),
        xui_add_client_endpoint=os.getenv("XUI_ADD_CLIENT_ENDPOINT", "/panel/api/inbounds/addClient"),
        xui_update_client_endpoint=os.getenv(
            "XUI_UPDATE_CLIENT_ENDPOINT", "/panel/api/inbounds/updateClient/{client_id}"
        ),
        xui_delete_client_endpoint=os.getenv(
            "XUI_DELETE_CLIENT_ENDPOINT", "/panel/api/inbounds/delClient/{client_id}"
        ),
        key_template=os.getenv(
            "KEY_TEMPLATE",
            "vless://{uuid}@{vpn_host}:{vpn_port}?security=none&type=tcp#{xui_email}",
        ),
        vpn_host=os.getenv("VPN_HOST", ""),
        vpn_port=int(os.getenv("VPN_PORT", "443")),
    )
