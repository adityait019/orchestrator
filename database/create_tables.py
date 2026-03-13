import asyncio
from engine import engine
from models import Base

async def create():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("Table created successfully!")


asyncio.run(create())