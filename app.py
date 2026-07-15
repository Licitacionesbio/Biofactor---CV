import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from crear_base import Candidato, Vacante, Postulacion, Base
import pypdf
import re

st.set_page_config(page_title="Biofactor", layout="wide")

# --- CONEXIÓN INTELIGENTE A NEON (NUBE) O LOCAL ---
connection_successful = False

if "database" in st.secrets:
    DATABASE_URL = st.secrets["database"]["url"]
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
    elif DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
    
    try:
        engine = create_engine(DATABASE_URL, connect_args={"sslmode": "require"})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        st.success("🔌 ¡Conexión exitosa a la base de datos de Neon en la nube!")
        connection_successful = True
    except Exception as e:
        st.error(f"🚨 Error al intentar conectar a Neon: {e}")
        st.warning("Usando base temporal local SQLite para que la app no se apague.")
        DATABASE_URL = 'sqlite:///bolsa_empleo.db'
        engine = create_engine(DATABASE_URL)
else:
    st.warning("⚠️ No se detectaron Secrets de base de datos en Streamlit. Usando base local SQLite.")
    DATABASE_URL = 'sqlite:///bolsa_empleo.db'
    engine = create_engine(DATABASE_URL)

Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()

# --- DEFINICIÓN DE ETAPAS OFICIALES EN ORDEN ---
ETAPAS_PROCESO = [
    "CV Recibido",
    "Entrevista Director Comercial",
    "Entrevista RRHH",
    "Entrevista Presencial",
    "Entrevista Gerencia",
    "Aplica",
    "No Aplica",
    "Preocupacional",
    "Contratado"
]

# Etapas que se consideran activas dentro del proceso de selección
ETAPAS_ACTIVAS = [
    "CV Recibido",
    "Entrevista Director Comercial",
    "Entrevista RRHH",
    "Entrevista Presencial",
    "Entrevista Gerencia",
    "Aplica",
    "Preocupacional"
]

# --- FUNCIÓN AUXILIAR PARA LIMPIAR TELÉFONO Y CREAR LINK DE WHATSAPP ---
def obtener_link_whatsapp(telefono_str):
    if not telefono_str:
        return None
    # Nos quedamos únicamente con los dígitos numéricos
    numeros = re.sub(r'\D', '', telefono_str)
    if not numeros:
        return None
    
    # Si el número no tiene código de país (ej: empieza con 11 o 341 en Argentina), le agregamos el '54' de Argentina por defecto
    if len(numeros) <= 10 and not numeros.startswith("54"):
        numeros = "54" + numeros
        
    return f"https://wa.me/{numeros}"

# --- LOGO Y TÍTULO ---
col_logo, col_titulo = st.columns([1, 20])
with col_logo:
    st.image("logo.png", width=60) 
with col_titulo:
    st.title("BIOFACTOR S.A. - Vacante y Postulantes") 

st.markdown("---")

tab1, tab2, tab3 = st.tabs(["📋 Panel de Gestión RRHH", "➕ Registrar con CV (PDF)", "🎯 Crear Nuevo Puesto"])

# --- PESTAÑA 3: CREAR PUESTO ---
with tab3:
    st.subheader("Registrar una Nueva Búsqueda Laboral")
    with st.form("form_crear_vacante"):
        nuevo_titulo = st.text_input("Nombre del Puesto (ej: Analista, Desarrollador):")
        
        areas_preestablecidas = [
            "Area Comercial",
            "Area Tecnica",
            "Area Gerencial",
            "Area Contable",
            "Area Operativo"
        ]
        
        depto_seleccionado = st.selectbox("Área / Departamento:", areas_preestablecidas)
        
        if st.form_submit_button("Crear Puesto") and nuevo_titulo:
            try:
                session.add(Vacante(titulo=nuevo_titulo, departamento=depto_seleccionado, estado="Abierta"))
                session.commit()
                st.success(f"¡Puesto '{nuevo_titulo}' creado con éxito en el área '{depto_seleccionado}'!")
                st.rerun()
            except Exception as e:
                session.rollback()
                st.error(f"Error al guardar puesto: {e}")

# --- PESTAÑA 1: PANEL DE GESTIÓN RRHH ---
with tab1:
    # --- CÁLCULO DE CONTADORES EN TIEMPO REAL ---
    try:
        total_todos = session.query(Postulacion).count()
        
        total_activos = session.query(Postulacion).filter(
            Postulacion.estado_proceso.in_(ETAPAS_ACTIVAS)
        ).count()
        
        total_contratados = session.query(Postulacion).filter(
            Postulacion.estado_proceso == "Contratado"
        ).count()
        
        total_no_aplica = session.query(Postulacion).filter(
            Postulacion.estado_proceso.in_(["No Aplica", "Rechazado", "Perfil en Reserva"])
        ).count()
    except Exception:
        total_todos = total_activos = total_contratados = total_no_aplica = 0

    col1, col2 = st.columns([1, 2])
    
    if "filtro_estado" not in st.session_state:
        st.session_state.filtro_estado = "Todos"

    # --- BARRA LATERAL IZQUIERDA (FILTROS) ---
    with col1:
        st.subheader("📊 Estados")
        
        es_todos = st.session_state.filtro_estado == "Todos"
        if st.button(f"✨ Ver Todos ({total_todos})", use_container_width=True, type="primary" if es_todos else "secondary"):
            st.session_state.filtro_estado = "Todos"
            st.rerun()
            
        st.write("---")
        
        es_activos = st.session_state.filtro_estado == "Activos"
        if st.button(f"⚡ En Proceso / Aplica ({total_activos})", use_container_width=True, type="primary" if es_activos else "secondary"):
            st.session_state.filtro_estado = "Activos"
            st.rerun()
            
        es_contratados = st.session_state.filtro_estado == "Contratados"
        if st.button(f"🎉 Contratados ({total_contratados})", use_container_width=True, type="primary" if es_contratados else "secondary"):
            st.session_state.filtro_estado = "Contratados"
            st.rerun()
            
        es_no_aplica = st.session_state.filtro_estado == "No Aplica"
        if st.button(f"📁 No Aplica ({total_no_aplica})", use_container_width=True, type="primary" if es_no_aplica else "secondary"):
            st.session_state.filtro_estado = "No Aplica"
            st.rerun()
        
    # --- SECCIÓN CENTRAL / DERECHA ---
    with col2:
        st.subheader("🔍 Buscador de Talento")
        
        try:
            vacantes_db = session.query(Vacante).all()
        except Exception:
            vacantes_db = []
        opciones_puestos = ["Todos los Puestos"] + [v.titulo for v in vacantes_db]
        
        col_filtro_puesto, col_filtro_texto = st.columns([1, 1])
        with col_filtro_puesto:
            puesto_seleccionado = st.selectbox("Filtrar por Puesto Laboral:", opciones_puestos)
        with col_filtro_texto:
            busqueda = st.text_input("Filtrar por palabra clave:", value="", placeholder="Nombre, email, notas...")
            
        st.markdown("---")
        
        titulos_estado = {
            "Todos": "👤 Todos los Postulantes",
            "Activos": "👤 Postulantes Activos / En Selección",
            "Contratados": "👤 Postulantes Contratados",
            "No Aplica": "👤 Perfiles Archivo (No Aplica)"
        }
        st.write(f"### {titulos_estado.get(st.session_state.filtro_estado, 'Candidatos')}")
            
        try:
            postulaciones_db = session.query(Postulacion).all()
        except Exception as e:
            st.error(f"Error leyendo postulaciones: {e}")
            postulaciones_db = []

        for post in postulaciones_db:
            # --- FILTRADO DINÁMICO POR EL BOTÓN SELECCIONADO A LA IZQUIERDA ---
            if st.session_state.filtro_estado == "Activos":
                if post.estado_proceso not in ETAPAS_ACTIVAS:
                    continue
            elif st.session_state.filtro_estado == "Contratados":
                if post.estado_proceso != "Contratado":
                    continue
            elif st.session_state.filtro_estado == "No Aplica":
                if post.estado_proceso not in ["No Aplica", "Rechazado", "Perfil en Reserva"]:
                    continue
                
            cand = session.query(Candidato).filter(Candidato.id == post.candidato_id).first()
            vac = session.query(Vacante).filter(Vacante.id == post.vacante_id).first()
            
            if cand and vac:
                if puesto_seleccionado != "Todos los Puestos" and vac.titulo != puesto_seleccionado:
                    continue
                
                dir_texto = cand.direccion if cand.direccion else ""
                notes_texto = post.notes if post.notes else ""
                texto_completo = f"{cand.nombre} {cand.email} {str(notes_texto)} {vac.titulo} {dir_texto}".lower()
                if busqueda.lower() not in texto_completo:
                    continue
                
                # --- [CAMBIO 1] TUERCA ⚙️ EN CADA EXPANDER DE CANDIDATO ---
                with st.expander(f"⚙️ {cand.nombre} -> 🎯 {vac.titulo} | [{post.estado_proceso}]"):
                    st.write(f"📧 **Email:** {cand.email}")
                    
                    # --- MOSTRAR TELÉFONO CON ACCESO DIRECTO A WHATSAPP ---
                    link_wa = obtener_link_whatsapp(cand.telefono)
                    col_tel, col_wa = st.columns([1, 1])
                    with col_tel:
                        st.write(f"📞 **Teléfono:** {cand.telefono if cand.telefono else 'No registrado'}")
                    with col_wa:
                        if link_wa:
                            boton_html = (
                                f'<a href="{link_wa}" target="_blank" style="text-decoration: none;">'
                                f'<button style="background-color: #25D366; color: white; border: none; padding: 8px 14px; '
                                f'border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 14px; display: inline-flex; '
                                f'align-items: center; gap: 8px; box-shadow: 0px 2px 4px rgba(0,0,0,0.1);">'
                                f'<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" viewBox="0 0 16 16">'
                                f'<path d="M13.601 2.326A7.85 7.85 0 0 0 8 0a7.85 7.85 0 0 0-7.3 4.7 7.86 7.86 0 0 0-.012 5.56L0 16l5.85-1.535a7.86 7.86 0 0 0 3.84 1.15H8a7.85 7.85 0 0 0 7.3-4.7 7.85 7.85 0 0 0-.7-8.59M8 14.377a6.55 6.55 0 0 1-3.336-.908l-.239-.142-3.481.913.93-3.39-.155-.247a6.55 6.55 0 0 1-1.124-3.666c0-3.62 2.953-6.57 6.574-6.57 1.75 0 3.396.68 4.63 1.914a6.55 6.55 0 0 1 1.91 4.65c-.001 3.62-2.953 6.57-6.573 6.57m3.191-4.415c-.176-.088-1.039-.513-1.2-.572-.162-.06-.279-.088-.396.088-.117.176-.45.572-.551.687-.101.117-.203.13-.379.043-.176-.088-.743-.274-1.416-.874-.524-.467-.878-1.045-.98-1.219-.101-.176-.01-.271.078-.358.079-.078.176-.205.264-.307.09-.102.119-.176.178-.293.06-.117.03-.22-.015-.307-.044-.088-.396-.954-.543-1.307-.143-.347-.289-.299-.396-.305-.101-.005-.218-.005-.335-.005-.117 0-.308.043-.469.218-.161.176-.615.601-.615 1.464s.626 1.696.714 1.815c.088.118 1.23 1.877 2.981 2.631.417.18.742.287.996.368.419.133.801.114 1.102.069.336-.05 1.039-.425 1.186-.835.147-.41.147-.762.103-.835-.045-.074-.162-.118-.338-.206"/>'
                                f'</svg>'
                                f'Enviar WhatsApp'
                                f'</button></a>'
                            )
                            st.markdown(boton_html, unsafe_allow_html=True)
                    
                    st.write(f"📍 **Ubicación:** {cand.direccion if cand.direccion else 'No especificado'}")
                    
                    # --- GESTIÓN DE CV PDF ---
                    if cand.archivo_cv:
                        st.download_button(
                            label="📥 Descargar CV (PDF)",
                            data=cand.archivo_cv,
                            file_name=f"CV_{cand.nombre.replace(' ', '_')}.pdf",
                            mime="application/pdf",
                            key=f"dl_{cand.id}_{post.id}",
                            use_container_width=True
                        )
                    else:
                        st.info("No hay un archivo PDF guardado.")
                    
                    st.write("---")
                    
                    # --- FORMULARIO DE EDICIÓN AMPLIADO ---
                    with st.form(key=f"form_update_{post.id}"):
                        st.markdown("✏️ **Corregir / Editar Ficha del Postulante**")
                        
                        # Campos de edición directa del candidato
                        nuevo_nombre = st.text_input("Nombre del Candidato:", value=cand.nombre)
                        nuevo_email = st.text_input("Email:", value=cand.email)
                        nuevo_telefono = st.text_input("Teléfono:", value=cand.telefono if cand.telefono else "")
                        nueva_direccion = st.text_input("Dirección:", value=cand.direccion if cand.direccion else "")
                        
                        st.markdown("---")
                        
                        # Gestión del proceso
                        estado_actual = post.estado_proceso
                        
                        # Normalizar textos viejos de la base de datos
                        if estado_actual == "CV recibido":
                            estado_actual = "CV Recibido"
                        elif estado_actual in ["Rechazado", "Perfil en Reserva"]:
                            estado_actual = "No Aplica"
                        elif estado_actual in ["Entrevista con Gerencia", "Entrevista con gerencia"]:
                            estado_actual = "Entrevista Gerencia"
                            
                        idx_actual = ETAPAS_PROCESO.index(estado_actual) if estado_actual in ETAPAS_PROCESO else 0
                        
                        nuevo_est = st.selectbox("Cambiar Etapa:", ETAPAS_PROCESO, index=idx_actual)
                        notes_actuales = post.notes if post.notes else ""
                        nuevas_notas = st.text_area("Notas / Comentarios Internos:", value=notes_actuales)
                        
                        # --- NUEVA SECCIÓN DE 3 BOTONES ALINEADOS ABAJO DE LAS NOTAS ---
                        col_save, col_edit, col_del = st.columns([1, 1, 1])
                        
                        with col_save:
                            if st.form_submit_button("💾 Guardar", use_container_width=True):
                                try:
                                    # Actualizamos datos del Candidato
                                    cand.nombre = nuevo_nombre
                                    cand.email = nuevo_email
                                    cand.telefono = nuevo_telefono
                                    cand.direccion = nueva_direccion
                                    
                                    # Actualizamos datos de la Postulacion
                                    post.estado_proceso = nuevo_est
                                    post.notes = nuevas_notas
                                    
                                    session.commit()
                                    st.success("¡Datos guardados con éxito!")
                                    st.rerun()
                                except Exception as e:
                                    session.rollback()
                                    st.error(f"Error al intentar guardar los cambios: {e}")
                                    
                        with col_edit:
                            if st.form_submit_button("✏️ Corregir", use_container_width=True):
                                try:
                                    # Mismo guardado pero con feedback visual de "corregido"
                                    cand.nombre = nuevo_nombre
                                    cand.email = nuevo_email
                                    cand.telefono = nuevo_telefono
                                    cand.direccion = nueva_direccion
                                    
                                    post.estado_proceso = nuevo_est
                                    post.notes = nuevas_notas
                                    
                                    session.commit()
                                    st.success("¡Ficha corregida con éxito!")
                                    st.rerun()
                                except Exception as e:
                                    session.rollback()
                                    st.error(f"Error al intentar aplicar la corrección: {e}")
                                    
                        with col_del:
                            if st.form_submit_button("🗑️ Eliminar", use_container_width=True):
                                try:
                                    session.delete(post)
                                    session.commit()
                                    st.warning("Postulación eliminada.")
                                    st.rerun()
                                except Exception as e:
                                    session.rollback()
                                    st.error(f"No se pudo eliminar: {e}")

# --- PESTAÑA 2: LECTOR DE PDF ---
with tab2:
    st.subheader("Cargar Currículum en PDF")
    try:
        lista_vacantes = session.query(Vacante).all()
    except Exception:
        lista_vacantes = []
        
    if not lista_vacantes:
        st.warning("⚠️ Primero debes crear al menos un puesto en la pestaña 'Crear Nuevo Puesto'.")
    else:
        opciones_vacantes = {v.titulo: v.id for v in lista_vacantes}
        archivo = st.file_uploader("Arrastra el CV aquí", type=["pdf"])
        
        if archivo is not None:
            try:
                bytes_pdf = archivo.getvalue()
                lector = pypdf.PdfReader(archivo)
                texto_cv = "".join([pagina.extract_text() + "\n" for pagina in lector.pages])
                
                em = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', texto_cv)
                tel = re.search(r'\+?\d[\d\s-]{7,14}\d', texto_cv)
                nom_sug = archivo.name.replace(".pdf", "").replace("_", " ").replace("-", " ").title()
                
                match_dir = re.search(r'(dirección|direccion|domicilio|barrio|localidad|vive en|residencia)[:\s]+([^\n]{3,40})', texto_cv, re.IGNORECASE)
                dir_sug = match_dir.group(2).strip() if match_dir else ""
                
                with st.form("form_confirmar_pdf"):
                    puesto_sel = st.selectbox("¿A qué puesto aplica?", list(opciones_vacantes.keys()))
                    nom = st.text_input("Nombre:", value=nom_sug)
                    email = st.text_input("Email:", value=em.group(0) if em else "")
                    telef = st.text_input("Teléfono:", value=tel.group(0).strip() if tel else "")
                    direccion = st.text_input("Dirección / Barrio / Localidad:", value=dir_sug)
                    
                    if st.form_submit_button("Confirmar Postulación") and nom and email:
                        candidato_existente = session.query(Candidato).filter(Candidato.email == email).first()
                        
                        if candidato_existente:
                            candidato_existente.nombre = nom
                            candidato_existente.telefono = telef
                            candidato_existente.direccion = direccion
                            candidato_existente.archivo_cv = bytes_pdf
                            candidato_existente.ruta_cv = archivo.name
                            candidato_id = candidato_existente.id
                            st.info("ℹ️ Se actualizaron los datos del candidato existente.")
                        else:
                            nuevo_c = Candidato(
                                nombre=nom, email=email, telefono=telef, direccion=direccion, 
                                archivo_cv=bytes_pdf, ruta_cv=archivo.name
                            )
                            session.add(nuevo_c)
                            session.flush()
                            candidato_id = nuevo_c.id
                        
                        postulacion_existente = session.query(Postulacion).filter(
                            Postulacion.candidato_id == candidato_id,
                            Postulacion.vacante_id == opciones_vacantes[puesto_sel]
                        ).first()
                        
                        if postulacion_existente:
                            st.warning(f"⚠️ Ya existe la postulación. Estado: '{postulacion_existente.estado_proceso}'.")
                        else:
                            session.add(Postulacion(
                                candidato_id=candidato_id, 
                                vacante_id=opciones_vacantes[puesto_sel], 
                                estado_proceso="CV Recibido", 
                                notes="CV subido al sistema Biofactor."
                            ))
                            session.commit()
                            st.success(f"¡{nom} registrado con éxito!")
                            st.rerun()
            except Exception as e:
                st.error(f"Error al procesar: {e}")

session.close()
