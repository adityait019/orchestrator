from sqlalchemy.ext.asyncio import async_sessionmaker
from database.engine import engine

AsyncSessionLocal=async_sessionmaker(engine,expire_on_commit=False)