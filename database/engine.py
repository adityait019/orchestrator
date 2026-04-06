from sqlalchemy.ext.asyncio import create_async_engine
import os
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL=os.getenv("DATABASE_URL","")

engine=create_async_engine(
    DATABASE_URL,
    echo=False,
)
