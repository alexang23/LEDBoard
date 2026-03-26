from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import scoped_session
# from config import settings
# from functools import lru_cache
# from typing import Iterator
# from sqlalchemy.orm import Session
# from fastapi_utils.session import FastAPISessionMaker
# from sqlalchemy.pool import NullPool
# from sqlalchemy.pool import StaticPool
# from sqlalchemy.pool import SingletonThreadPool


# SQLALCHEMY_DATABASE_URL = f"mysql+pymysql://{settings.MARIADB_USER}:{settings.MARIADB_PASSWORD}@{settings.MARIADB_HOST}:{settings.MARIADB_PORT}/{settings.MARIADB_DATABASE}"
SQLALCHEMY_DATABASE_URL = f"sqlite:///./ipc.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=20,
    max_overflow=40,
    pool_timeout=30
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

engine_log = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=30,
    max_overflow=60,
    pool_timeout=60
)
SessionLog = sessionmaker(autocommit=False, autoflush=False, bind=engine_log)

engine_alarm_event = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30
)
SessionAlarmEvent = sessionmaker(autocommit=False, autoflush=False, bind=engine_alarm_event)


# Base = declarative_base()

class Base:
    __allow_unmapped__ = True
Base = declarative_base(cls=Base)

#Base = declarative_base()

# SessionLocal2 = scoped_session(SessionLocal)
# db = SessionLocal2()

# def get_db2():
#     try:
#         db = SessionLocal()
#         yield db
#     except Exception as exc:
#         # session.rollback()
#         raise exc
#     finally:
#         db.close()

def get_db():
    try:
        db = SessionLocal()
        yield db
    except Exception as err:
        print(str(err))
        db.rollback()
        raise
    else:
        db.commit()
    finally:
        db.close()
        
# Base = declarative_base()
  
# def get_db() -> Iterator[Session]:
#     """FastAPI dependency that provides a sqlalchemy session"""
#     yield from _get_fastapi_sessionmaker().get_db()


# @lru_cache()
# def _get_fastapi_sessionmaker() -> FastAPISessionMaker:
#     """This function could be replaced with a global variable if preferred"""
#     database_uri = SQLALCHEMY_DATABASE_URL
#     return FastAPISessionMaker(database_uri)