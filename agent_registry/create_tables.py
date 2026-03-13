import asyncio
from database import engine,Base

from models import AgentRegistry

async def create():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("Table created successfully!")


asyncio.run(create())