import os
import streamlit as st
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Text, LargeBinary
from sqlalchemy.orm import declarative_base, relationship

# --- CONEXIÓN INTELIGENTE A NEON (NUBE) O LOCAL ---
if "database" in st.secrets:
    DATABASE_URL = st.secrets["database"]["url"]
    # Reemplazo estricto para forzar el uso de psycopg2 con Neon en SQLAlchemy
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
    elif DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
    
    # Neon requiere explícitamente pasar el parámetro de SSL en los argumentos de conexión
    engine = create_engine(
        DATABASE_URL, 
        echo=True,
        connect_args={"sslmode": "require"}
    )
else:
    DATABASE_URL = 'sqlite:///bolsa_empleo.db'
    engine = create_engine(DATABASE_URL, echo=True)

Base = declarative_base()

class Candidato(Base):
    __tablename__ = 'candidatos'
    
    id = Column(Integer, primary_key=True)
    nombre = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    telefono = Column(String(20))
    linkedin = Column(String(200))
    ruta_cv = Column(String(250))
    direccion = Column(String(200))
    archivo_cv = Column(LargeBinary)
    
    postulaciones = relationship("Postulacion", back_populates="candidato")

class Vacante(Base):
    __tablename__ = 'vacantes'
    
    id = Column(Integer, primary_key=True)
    titulo = Column(String(100), nullable=False)
    departamento = Column(String(50))
    estado = Column(String(20), default="Abierta")
    
    postulaciones = relationship("Postulacion", back_populates="vacante")

class Postulacion(Base):
    __tablename__ = 'postulaciones'
    
    id = Column(Integer, primary_key=True)
    candidato_id = Column(Integer, ForeignKey('candidatos.id'), nullable=False)
    vacante_id = Column(Integer, ForeignKey('vacantes.id'), nullable=False)
    fecha_postulacion = Column(DateTime, default=datetime.utcnow)
    estado_proceso = Column(String(50), default="Recibido")
    notes = Column(Text) # Mantenemos el estándar de notas
    
    candidato = relationship("Candidato", back_populates="postulaciones")
    vacante = relationship("Vacante", back_populates="postulaciones")

if __name__ == "__main__":
    Base.metadata.create_all(engine)
