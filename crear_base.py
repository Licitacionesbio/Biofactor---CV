from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Text, LargeBinary
from sqlalchemy.orm import declarative_base, relationship

# 1. Configurar la conexión (Crea el archivo de la base de datos local)
engine = create_engine('sqlite:///bolsa_empleo.db', echo=True)
Base = declarative_base()

# 2. Modelo de la Tabla: Candidatos (Datos personales)
class Candidato(Base):
    __tablename__ = 'candidatos'
    
    id = Column(Integer, primary_key=True)
    nombre = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    telefono = Column(String(20))
    linkedin = Column(String(200))
    ruta_cv = Column(String(250))  # Aquí guardaremos la ubicación de su PDF
    
    # --- COLUMNA DE DIRECCIÓN ---
    direccion = Column(String(200))  # Aquí guardamos la dirección/barrio/localidad
    
    # --- NUEVA COLUMNA DE ARCHIVO BINARIO (Para la descarga directa) ---
    archivo_cv = Column(LargeBinary) # Aquí se guardará el PDF real en bytes
    
    # Relación con las postulaciones (Apunta a la propiedad 'candidato' en Postulacion)
    postulaciones = relationship("Postulacion", back_populates="candidato")

# 3. Modelo de la Tabla: Vacantes (Puestos de trabajo en la empresa)
class Vacante(Base):
    __tablename__ = 'vacantes'
    
    id = Column(Integer, primary_key=True)
    titulo = Column(String(100), nullable=False)
    departamento = Column(String(50))
    estado = Column(String(20), default="Abierta")  # Abierta o Cerrada
    
    # Relación con las postulaciones (Apunta a la propiedad 'vacante' en Postulacion)
    postulaciones = relationship("Postulacion", back_populates="vacante")

# 4. Modelo de la Tabla: Postulaciones (Une al Candidato con la Vacante)
class Postulacion(Base):
    __tablename__ = 'postulaciones'
    
    id = Column(Integer, primary_key=True)
    candidato_id = Column(Integer, ForeignKey('candidatos.id'), nullable=False)
    vacante_id = Column(Integer, ForeignKey('vacantes.id'), nullable=False)
    fecha_postulacion = Column(DateTime, default=datetime.utcnow)
    estado_proceso = Column(String(50), default="Recibido")  # Recibido, Entrevista, Rechazado, etc.
    notas = Column(Text)
    
    # RELACIONES CORREGIDAS: Apuntan a la lista de 'postulaciones' de los padres
    candidato = relationship("Candidato", back_populates="postulaciones")
    vacante = relationship("Vacante", back_populates="postulaciones")

# 5. Crear físicamente las tablas en el archivo .db
if __name__ == "__main__":
    Base.metadata.create_all(engine)
    print("\n" + "="*50)
    print("¡Base de datos y tablas creadas con éxito!")
    print("Se ha generado el archivo 'bolsa_empleo.db' en esta carpeta.")
    print("="*50 + "\n")
