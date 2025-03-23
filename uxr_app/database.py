import sqlite3
import hashlib
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, ARRAY
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.dialects.sqlite import BLOB  # Import BLOB
from datetime import datetime
from uuid import uuid4

Base = declarative_base()

# --- User Table ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)  # In a real app, store a hashed password!
    user_id = Column(String, unique=True, nullable=False)

    projects = relationship("Project", back_populates="user")


# --- Project Table ---
class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True)
    project_name = Column(String)
    user_group_desc = Column(Text)
    product_desc = Column(Text)
    project_uuid = Column(String, unique=True)
    user_id = Column(String, ForeignKey("users.user_id"))
    creation_date = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="projects")
    persona_archetypes = relationship("PersonaArchetype", back_populates="project")
    personas = relationship("Persona", back_populates="project")
    uxr_researcher = relationship("UXRResearcher", back_populates="project", uselist=False)
    interviews = relationship("Interview", back_populates="project")

class Persona(Base):
    __tablename__ = "personas"
    id = Column(Integer, primary_key=True)
    persona_name = Column(String)
    persona_desc = Column(Text)
    persona_arch_uuids = Column(Text)  # Store as comma-separated string; better would be a many-to-many
    project_uuid = Column(String, ForeignKey("projects.project_uuid"))
    persona_uuid = Column(String, unique=True)

    project = relationship("Project", back_populates="personas")
    interviews = relationship("Interview", back_populates="persona")

class PersonaArchetype(Base):
    __tablename__ = "persona_archetypes"
    project_uuid = Column(String, ForeignKey("projects.project_uuid"))
    persona_archetype_name = Column(String)
    persona_archetype_desc = Column(Text)
    persona_arch_uuid = Column(String, primary_key=True)

    project = relationship("Project", back_populates="persona_archetypes")

# --- UXR Researcher Table ---
class UXRResearcher(Base):
    __tablename__ = "uxr_researcher"
    id = Column(Integer, primary_key=True)
    uxr_persona_name = Column(String)
    uxr_persona_desc = Column(Text)
    project_uuid = Column(String, ForeignKey("projects.project_uuid"))
    uxr_persona_uuid = Column(String, unique=True)

    project = relationship("Project", back_populates="uxr_researcher")
    interviews = relationship("Interview", back_populates="uxr_persona")

# --- Interview Table ---
class Interview(Base):
    __tablename__ = "interviews"
    id = Column(Integer, primary_key=True)
    persona_uuid = Column(String, ForeignKey("personas.persona_uuid"))
    uxr_persona_uuid = Column(String, ForeignKey("uxr_researcher.uxr_persona_uuid"))
    interview_transcript = Column(Text)
    project_uuid = Column(String, ForeignKey("projects.project_uuid"))
    datetime = Column(DateTime, default=datetime.utcnow)
    interview_uuid = Column(String, unique=True)

    persona = relationship("Persona", back_populates="interviews")
    uxr_persona = relationship("UXRResearcher", back_populates="interviews")
    project = relationship("Project", back_populates="interviews")


DATABASE_URL = "sqlite:///./uxr_app.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}) #For SQLite
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    Base.metadata.create_all(bind=engine)

# --- Helper DB Functions ---
def create_user(db, email, password):
    user_id = hashlib.md5((email + password).encode()).hexdigest()
    new_user = User(email=email, password=password, user_id=user_id)  # Hash password!
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

def get_user_by_email(db, email):
    return db.query(User).filter(User.email == email).first()

def create_project(db, user_id, user_group_desc, product_desc, project_name):
    project_uuid = hashlib.md5((project_name + user_group_desc + product_desc + user_id).encode()).hexdigest()
    new_project = Project(project_name=project_name, user_group_desc=user_group_desc, product_desc=product_desc, project_uuid=project_uuid, user_id=user_id)
    db.add(new_project)
    db.commit()
    db.refresh(new_project)
    return new_project

def get_project_by_uuid(db, project_uuid):
    return db.query(Project).filter(Project.project_uuid == project_uuid).first()

def create_persona_archetype(db, project_uuid, name, desc):
    persona_arch_uuid = hashlib.md5((project_uuid + name + desc).encode()).hexdigest()
    new_archetype = PersonaArchetype(project_uuid=project_uuid, persona_archetype_name=name, persona_archetype_desc=desc, persona_arch_uuid=persona_arch_uuid)
    db.add(new_archetype)
    db.commit()
    db.refresh(new_archetype)
    return new_archetype

def get_archetypes_by_project(db, project_uuid):
     return db.query(PersonaArchetype).filter(PersonaArchetype.project_uuid == project_uuid).all()

def create_persona(db, project_uuid, arch_uuids, name, desc):
    persona_uuid = hashlib.md5((name + desc).encode()).hexdigest()
    new_persona = Persona(project_uuid=project_uuid, persona_arch_uuids=arch_uuids, persona_name=name, persona_desc=desc, persona_uuid=persona_uuid)
    db.add(new_persona)
    db.commit()
    db.refresh(new_persona)
    return new_persona

def get_personas_by_project(db, project_uuid):
    return db.query(Persona).filter(Persona.project_uuid == project_uuid).all()

def create_uxr_researcher(db, project_uuid, name, desc):
    uxr_persona_uuid = str(uuid4())
    new_researcher = UXRResearcher(project_uuid=project_uuid, uxr_persona_name=name, uxr_persona_desc=desc, uxr_persona_uuid=uxr_persona_uuid)
    db.add(new_researcher)
    db.commit()
    db.refresh(new_researcher)
    return new_researcher

def get_uxr_researcher_by_project(db, project_uuid):
    return db.query(UXRResearcher).filter(UXRResearcher.project_uuid == project_uuid).first()

def create_interview(db, persona_uuid, uxr_persona_uuid, project_uuid, transcript):
     interview_uuid = hashlib.md5((persona_uuid + uxr_persona_uuid + project_uuid + transcript).encode()).hexdigest()
     new_interview = Interview(persona_uuid=persona_uuid, uxr_persona_uuid=uxr_persona_uuid, project_uuid=project_uuid, interview_transcript=transcript, interview_uuid=interview_uuid)
     db.add(new_interview)
     db.commit()
     db.refresh(new_interview)
     return new_interview

def get_interviews_by_project(db, project_uuid):
    return db.query(Interview).filter(Interview.project_uuid == project_uuid).all()

def update_project(db, project_uuid, update_data):
    project = db.query(Project).filter(Project.project_uuid == project_uuid).first()
    if project:
        for key, value in update_data.items():
            setattr(project, key, value)
        db.commit()
        db.refresh(project)
    return project
def update_persona_archetype(db, persona_arch_uuid, update_data):
    archetype = db.query(PersonaArchetype).filter(PersonaArchetype.persona_arch_uuid == persona_arch_uuid).first()
    if archetype:
        for key, value in update_data.items():
            setattr(archetype, key, value)
        db.commit()
        db.refresh(archetype)
    return archetype

def update_persona(db, persona_uuid, update_data):
    persona = db.query(Persona).filter(Persona.persona_uuid == persona_uuid).first()
    if persona:
        for key, value in update_data.items():
            setattr(persona, key, value)
        db.commit()
        db.refresh(persona)
    return persona

def update_uxr_researcher(db, uxr_persona_uuid, update_data):
    researcher = db.query(UXRResearcher).filter(UXRResearcher.uxr_persona_uuid == uxr_persona_uuid).first()
    if researcher:
        for key, value in update_data.items():
            setattr(researcher, key, value)
        db.commit()
        db.refresh(researcher)

def get_existing_persona_names(db, project_uuid):
    personas = get_personas_by_project(db, project_uuid)
    return [persona.persona_name for persona in personas]