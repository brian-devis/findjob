"""CLI 工具：创建管理员。

用法：python -m app.cli create-admin --username admin --password xxx
"""
import argparse
import asyncio

from app.core.database import async_session_factory
from app.core.security import hash_password
from app.repositories.admin import AdminRepository


async def _create_admin(username: str, password: str) -> None:
    async with async_session_factory() as session:
        repo = AdminRepository(session)
        if await repo.get_by_username(username) is not None:
            print(f"管理员 {username} 已存在")
            return
        await repo.create(username, hash_password(password))
        await session.commit()
        print(f"已创建管理员 {username}")


def main() -> None:
    parser = argparse.ArgumentParser(description="AIJob 管理工具")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create-admin", help="创建管理员")
    p.add_argument("--username", required=True)
    p.add_argument("--password", required=True)

    args = parser.parse_args()
    if args.command == "create-admin":
        asyncio.run(_create_admin(args.username, args.password))


if __name__ == "__main__":
    main()
