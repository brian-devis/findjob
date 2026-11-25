"""AIJob Local Agent CLI 入口。"""
import asyncio
import logging
import signal

from agent.client import AgentAuthError, LocalAgentClient
from agent.config import AgentSettings


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


async def _run() -> int:
    settings = AgentSettings()
    _setup_logging(settings.log_level)
    client = LocalAgentClient(settings)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, client.stop)
        except NotImplementedError:
            # Windows 事件循环不支持 add_signal_handler，依赖 KeyboardInterrupt
            pass

    try:
        await client.run_forever()
    except AgentAuthError:
        return 2
    except KeyboardInterrupt:
        pass
    finally:
        await client.close()
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
