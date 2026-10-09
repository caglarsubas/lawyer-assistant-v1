import hashlib
import json
import os
import secrets
from datetime import datetime, timezone

from cryptography.fernet import Fernet
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return secrets.token_hex(16)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    firm_id: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(24), default="lawyer")
    password_hash: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class LoginSession(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    csrf: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[str] = mapped_column(String(40))


class Record(Base):
    """Encrypted aggregate payloads, with only access-routing metadata in plaintext."""

    __tablename__ = "records"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    firm_id: Mapped[str] = mapped_column(String(64), index=True)
    matter_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    owner_id: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    __mapper_args__ = {"version_id_col": revision, "version_id_generator": False}


class Membership(Base):
    __tablename__ = "memberships"
    matter_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)


class CustomerAssignment(Base):
    __tablename__ = "customer_assignments"
    customer_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    firm_id: Mapped[str] = mapped_column(String(64), index=True)
    scope: Mapped[str] = mapped_column(String(24))
    assigned_by: Mapped[str] = mapped_column(String(64))
    assigned_at: Mapped[str] = mapped_column(String(40), default=now)


class WorkspaceCustomerLink(Base):
    __tablename__ = "workspace_customer_links"
    matter_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    firm_id: Mapped[str] = mapped_column(String(64), index=True)


class CaseResponsibility(Base):
    __tablename__ = "case_responsibilities"
    matter_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    firm_id: Mapped[str] = mapped_column(String(64), index=True)
    supervisor: Mapped[bool] = mapped_column(Boolean, default=False)
    responsible: Mapped[bool] = mapped_column(Boolean, default=False)


class WorkParticipant(Base):
    """Routing only; assignment never grants case access. History stays encrypted."""
    __tablename__ = "work_participants"
    work_id: Mapped[str] = mapped_column(ForeignKey("records.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    response_id: Mapped[str] = mapped_column(ForeignKey("records.id"), unique=True)
    firm_id: Mapped[str] = mapped_column(String(64), index=True)
    matter_id: Mapped[str] = mapped_column(String(64), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AccessConfiguration(Base):
    __tablename__ = "access_configurations"
    target_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    firm_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(24))
    revision: Mapped[int] = mapped_column(Integer, default=1)


class ScopeMigration(Base):
    __tablename__ = "scope_migrations"
    firm_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class FirmRole(Base):
    __tablename__ = "firm_roles"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    firm_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(100))
    permissions: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    starter: Mapped[bool] = mapped_column(Boolean, default=False)


class Employee(Base):
    __tablename__ = "firm_employees"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    firm_id: Mapped[str] = mapped_column(String(64), index=True)
    manager_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)


class EmployeeRole(Base):
    __tablename__ = "employee_roles"
    user_id: Mapped[str] = mapped_column(ForeignKey("firm_employees.user_id"), primary_key=True)
    role_id: Mapped[str] = mapped_column(ForeignKey("firm_roles.id"), primary_key=True)


class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    actor_id: Mapped[str] = mapped_column(String(64))
    matter_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    object_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class Store:
    def __init__(self, settings):
        settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        key = settings.encryption_key
        if not key and settings.demo_mode:
            key_file = settings.data_dir / "demo-encryption.key"
            if not key_file.exists():
                fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(Fernet.generate_key())
            key = key_file.read_text().strip()
        if not key:
            raise ValueError("LA_ENCRYPTION_KEY is required outside explicit demo mode")
        self.cipher = Fernet(key.encode())
        db_url = settings.database_url
        if db_url.startswith("sqlite"):
            if not settings.demo_mode:
                raise ValueError("Production requires PostgreSQL; SQLite is restricted to explicit demo mode")
            if db_url == "sqlite:///./.data/workspace.db":
                db_url = f"sqlite:///{settings.data_dir / 'workspace.db'}"
        self.engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False} if db_url.startswith("sqlite") else {},
            pool_pre_ping=True,
        )
        self.session = sessionmaker(self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

    def encode(self, data):
        return self.cipher.encrypt(json.dumps(data, ensure_ascii=False).encode()).decode()

    def decode(self, record):
        return json.loads(self.cipher.decrypt(record.payload.encode()))

    def view(self, record):
        return {
            **self.decode(record),
            "id": record.id,
            "created_at": record.created_at,
            "revision": record.revision,
        }

    def add(self, session, kind, user, data, matter_id=None, record_id=None):
        rec = Record(
            id=record_id or uid(),
            kind=kind,
            firm_id=user.firm_id,
            owner_id=user.id,
            matter_id=matter_id,
            payload=self.encode(data),
        )
        session.add(rec)
        session.flush()
        return rec

    def update(self, record, data):
        record.payload = self.encode(data)
        record.revision += 1


def digest(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()
