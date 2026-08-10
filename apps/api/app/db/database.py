from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

is_sqlite = settings.DATABASE_URL.startswith("sqlite")
engine_options = {
    "pool_pre_ping": True,
    "pool_recycle": settings.DATABASE_POOL_RECYCLE_SECONDS,
}
if is_sqlite:
    engine_options["connect_args"] = {"check_same_thread": False}
else:
    engine_options["pool_size"] = settings.DATABASE_POOL_SIZE
    engine_options["max_overflow"] = settings.DATABASE_MAX_OVERFLOW

engine = create_engine(settings.DATABASE_URL, **engine_options)

# Enforce foreign key constraints on SQLite connections
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if is_sqlite:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    if is_sqlite:
        columns = {
            "approval_status": "VARCHAR NOT NULL DEFAULT 'NOT_REQUIRED'",
            "approved_at": "DATETIME",
            "approved_by": "VARCHAR",
            "integration_mode": "VARCHAR",
            "evidence_trust": "VARCHAR",
            "risk_assessment_json": "JSON",
            "writeback_result_json": "JSON",
            "github_result_json": "JSON",
        }
        with engine.begin() as connection:
            existing = {column["name"] for column in inspect(connection).get_columns("investigations")}
            for name, definition in columns.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE investigations ADD COLUMN {name} {definition}"))
