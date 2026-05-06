from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from database import Base


class Instance(Base):
    __tablename__ = "instances"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), unique=True, nullable=False, index=True)
    container_id = Column(String(128), nullable=True)
    api_port = Column(Integer, unique=True, nullable=False)
    console_port = Column(Integer, unique=True, nullable=False)
    access_key = Column(String(64), nullable=False)
    secret_key = Column(String(64), nullable=False)
    # status: creating | running | stopped | error
    status = Column(String(16), default="creating", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
