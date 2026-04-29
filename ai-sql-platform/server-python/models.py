from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Project(Base):
    __tablename__ = "projects"

    project_id = Column(Integer, primary_key=True)
    project_name = Column(String)
    status = Column(String)