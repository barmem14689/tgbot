from __future__ import annotations

import asyncio
import logging

from bot.app import VPNPaymentBot
from bot.config import load_config
from bot.db import init_db
from bot.repository import Repository
from bot.xui_client import XUIClient


async def amain() -> None:
    config = load_config()
    await init_db(str(config.database_path))
    repository = Repository(str(config.database_path))
    xui = XUIClient(config)
    app = VPNPaymentBot(config=config, repository=repository, xui=xui)
    await app.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(amain())
