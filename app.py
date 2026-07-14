import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from crear_base import Candidato, Vacante, Postulacion, Base
import pypdf
import re
import base64  # Requerido para mostrar el PDF dentro de la app de forma segura

st.set_page_config(page_title="Biofactor", layout="wide")

# --- CONEXIÓN INTELIGENTE A NEON (NUBE) O LOCAL ---
connection_successful = False

if "database" in st.secrets:
    DATABASE_URL = st.secrets["database"]["url"]
    # Reemplazo estricto para asegurar compatibilidad con SQLAlchemy + Neon (psycopg2)
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
    elif DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
    
    try:
        # Intentamos conectar a Neon usando sslmode obligatorio
        engine = create_engine(
            DATABASE_URL, 
            connect_args={"sslmode": "require"}
        )
        # Probamos ejecutar una consulta ultra simple para verificar si el canal de datos responde
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
        st.success("🔌 ¡Conexión exitosa a la base de datos de Neon en la nube!")
        connection_successful = True
    except Exception as e:
        # Mostramos en pantalla el error técnico específico de PostgreSQL
        st.error(f"🚨 Error al intentar conectar a Neon: {e}")
        st.warning("Se cayó o falló la conexión con Neon. Usando base temporal local SQLite para que la app no se apague.")
        DATABASE_URL = 'sqlite:///bolsa_empleo.db'
        engine = create_engine(DATABASE_URL)
else:
    st.warning("⚠️ No se detectaron Secrets de base de datos en Streamlit. Usando base local SQLite.")
    DATABASE_URL = 'sqlite:///bolsa_empleo.db'
    engine = create_engine(DATABASE_URL)

Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)
session = Session()

# --- LOGO Y TÍTULO EN LA MISMA FILA ---
col_logo, col_titulo = st.columns([1, 20])  # Proporción ideal para pantalla completa

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
        depto = st.text_input("Área / Departamento:", value="Biofactor Hub")
        if st.form_submit_button("Crear Puesto") and nuevo_titulo:
            try:
                session.add(Vacante(titulo=nuevo_titulo, departamento=depto, estado="Abierta"))
                session.commit()
                st.success(f"¡Puesto '{nuevo_titulo}' creado con éxito!")
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
            Postulacion.estado_proceso.in_(["CV Recibido", "Entrevista Director Comercial", "Entrevista RRHH", "Entrevista Presencial"])
        ).count()
        total_contratados = session.query(Postulacion).filter(Postulacion.estado_proceso == "Contratado").count()
        # Modificado: Ahora busca y cuenta bajo la nueva etiqueta suavizada
        total_reservados = session.query(Postulacion).filter(
            Postulacion.estado_proceso.in_(["Perfil en Reserva", "Rechazado"])
        ).count()
    except Exception:
        total_todos = total_activos = total_contratados = total_reservados = 0

    col1, col2 = st.columns([1, 2])
    
    # Inicializamos el estado del filtro de la barra lateral si no existe
    if "filtro_estado" not in st.session_state:
        st.session_state.filtro_estado = "Todos"

    # --- BARRA LATERAL IZQUIERDA (ESTADOS CON CONTADORES) ---
    with col1:
        st.subheader("📊 Estados")
        
        # Botón para limpiar filtros y ver todos con contador
        es_todos = st.session_state.filtro_estado == "Todos"
        if st.button(f"✨ Ver Todos ({total_todos})", 
                     use_container_width=True, 
                     type="primary" if es_todos else "secondary"):
            st.session_state.filtro_estado = "Todos"
            st.rerun()
            
        st.write("---")
        
        # Botón para filtrar "Activos" con contador
        es_activos = st.session_state.filtro_estado == "Activos"
        if st.button(f"⚡ Activos ({total_activos})", 
                     use_container_width=True, 
                     type="primary" if es_activos else "secondary"):
            st.session_state.filtro_estado = "Activos"
            st.rerun()
            
        # Botón para filtrar "Contratados" con contador
        es_contratados = st.session_state.filtro_estado == "Contratados"
        if st.button(f"🎉 Contratados ({total_contratados})", 
                     use_container_width=True, 
                     type="primary" if es_contratados else "secondary"):
            st.session_state.filtro_estado = "Contratados"
            st.rerun()
            
        # Modificado: Botón suavizado para filtrar perfiles guardados
        es_reservados = st.session_state.filtro_estado == "Reserva"
        if st.button(f"📁 Perfil en Reserva ({total_reservados})", 
                     use_container_width=True, 
                     type="primary" if es_reservados else "secondary"):
            st.session_state.filtro_estado = "Reserva"
            st.rerun()
        
    # --- SECCIÓN CENTRAL / DERECHA (FILTROS Y LISTADO) ---
    with col2:
        st.subheader("🔍 Buscador de Talento")
        
        # Obtener puestos reales de la base para el filtro combinado
        try:
            vacantes_db = session.query(Vacante).all()
        except Exception:
            vacantes_db = []
        opciones_puestos = ["Todos los Puestos"] + [v.titulo for v in vacantes_db]
        
        # Grid de filtros lado a lado
        col_filtro_puesto, col_filtro_texto = st.columns([1, 1])
        with col_filtro_puesto:
            puesto_seleccionado = st.selectbox("Filtrar por Puesto Laboral:", opciones_puestos)
        with col_filtro_texto:
            busqueda = st.text_input("Filtrar por palabra clave:", value="", placeholder="Nombre, email, notas...")
            
        st.markdown("---")
        
        # Cambiamos el título dinámico según el estado seleccionado
        titulos_estado = {
            "Todos": "👤 Todos los Postulantes",
            "Activos": "👤 Postulantes Activos (En Proceso)",
            "Contratados": "👤 Postulantes Contratados",
            "Reserva": "👤 Perfiles en Reserva / Archivo"
        }
        st.write(f"### {titulos_estado.get(st.session_state.filtro_estado, 'Candidatos')}")
            
        try:
            postulaciones_db = session.query(Postulacion).all()
        except Exception as e:
            st.error(f"Error leyendo postulaciones: {e}")
            postulaciones_db = []

        for post in postulaciones_db:
            # --- FILTRADO 1: ESTADO (BOTONES DE LA IZQUIERDA) ---
            if st.session_state.filtro_estado == "Activos":
                if post.estado_proceso not in ["CV Recibido", "Entrevista RRHH", "Entrevista Director Comercial"]:
                    continue
            elif st.session_state.filtro_estado == "Contratados":
                if post.estado_proceso != "Contratado":
                    continue
            elif st.session_state.filtro_estado == "Reserva":
                # Muestra tanto los nuevos como si hubiera quedado alguno con la etiqueta vieja
                if post.estado_proceso not in ["Perfil en Reserva", "Rechazado"]:
                    continue
                
            cand = session.query(Candidato).filter(Candidato.id == post.candidato_id).first()
            vac = session.query(Vacante).filter(Vacante.id == post.vacante_id).first()
            
            if cand and vac:
                # --- FILTRADO 2: PUESTO (SELECTBOX) ---
                if puesto_seleccionado != "Todos los Puestos" and vac.titulo != puesto_seleccionado:
                    continue
                
                # --- FILTRADO 3: PALABRA CLAVE (TEXT INPUT) ---
                dir_texto = cand.direccion if cand.direccion else ""
                notes_texto = post.notes if post.notes else ""
                texto_completo = f"{cand.nombre} {cand.email} {str(notes_texto)} {vac.titulo} {dir_texto}".lower()
                if busqueda.lower() not in texto_completo:
                    continue
                    
                with st.expander(f"👤 {cand.nombre} -> 🎯 {vac.titulo} | [{post.estado_proceso}]"):
                    st.write(f"📧 **Email:** {cand.email} | 📞 **Teléfono:** {cand.telefono}")
                    st.write(f"📍 **Ubicación / Barrio:** {cand.direccion if cand.direccion else 'No especificado'}")
                    
                    # --- COMPONENTE DE CV (DESCARGA Y PREVISUALIZADOR MEJORADO) ---
                    if cand.archivo_cv:
                        col_btn1, col_btn2 = st.columns([1, 1])
                        with col_btn1:
                            st.download_button(
                                label="📥 Descargar CV (PDF)",
                                data=cand.archivo_cv,
                                file_name=f"CV_{cand.nombre.replace(' ', '_')}.pdf",
                                mime="application/pdf",
                                key=f"dl_{cand.id}_{post.id}"
                            )
                        with col_btn2:
                            ver_pdf = st.checkbox("👀 Previsualizar CV en pantalla", key=f"ver_{cand.id}_{post.id}")
                        
                        # Si se activa la previsualización, se renderiza de forma robusta y sin bloqueos
                        if ver_pdf:
                            try:
                                base64_pdf = base64.b64encode(cand.archivo_cv).decode('utf-8')
                                
                                # Botón seguro de escape: Abre en pestaña nueva sin ninguna restricción
                                pdf_link = (
                                    f'<a href="data:application/pdf;base64,{base64_pdf}" target="_blank" style="text-decoration: none;">'
                                    f'<button style="background-color: #2e7d32; color: white; border: none; padding: 10px 20px; '
                                    f'border-radius: 8px; cursor: pointer; font-weight: bold; width: 100%; margin-bottom: 10px;">'
                                    f'🔓 Abrir visualizador en pestaña completa (Evita restricciones de Chrome)'
                                    f'</button></a>'
                                )
                                st.markdown(pdf_link, unsafe_allow_html=True)
                                
                                # Visor nativo usando la etiqueta <object> con soporte de fallback
                                pdf_display = (
                                    f'<object data="data:application/pdf;base64,{base64_pdf}" '
                                    f'type="application/pdf" width="100%" height="600">'
                                    f'<div style="text-align: center; padding: 20px; border: 1px dashed #ccc; border-radius: 8px;">'
                                    f'⚠️ Tu configuración de Chrome bloqueó la previsualización directa.<br><br>'
                                    f'<a href="data:application/pdf;base64,{base64_pdf}" download="CV_{cand.nombre.replace(" ", "_")}.pdf" '
                                    f'style="color: #FF4B4B; font-weight: bold;">[Haz clic aquí para descargar y ver directamente]</a>'
                                    f'</div>'
                                    f'</object>'
                                )
                                st.markdown(pdf_display, unsafe_allow_html=True)
                            except Exception as e:
                                st.error(f"No se pudo previsualizar el PDF: {e}")
                    else:
                        st.info("No hay un archivo PDF guardado para este candidato.")
                    
                    st.write("---")
                    
                    # Formulario para editar la postulación con el nuevo botón integrado de eliminación
                    with st.form(key=f"form_update_{post.id}"):
                        # Modificado: Se reemplazó "Rechazado" por "Perfil en Reserva"
                        estados = ["CV Recibido", "Entrevista RRHH", "Entrevista Director Comercial", "Perfil en Reserva", "Contratado"]
                        
                        # Manejo de compatibilidad en caso de que existan registros viejos guardados como "Rechazado"
                        estado_actual = post.estado_proceso
                        if estado_actual == "Rechazado":
                            estado_actual = "Perfil en Reserva"
                            
                        idx_actual = estados.index(estado_actual) if estado_actual in estados else 0
                        
                        nuevo_est = st.selectbox("Cambiar Etapa:", estados, index=idx_actual)
                        notes_actuales = post.notes if post.notes else ""
                        nuevas_notas = st.text_area("Notas / Comentarios del candidato:", value=notes_actuales, placeholder="Escribe aquí el feedback...")
                        
                        # Dos columnas para acomodar los botones al final del formulario
                        col_save, col_del = st.columns([1, 1])
                        
                        with col_save:
                            if st.form_submit_button("Guardar Cambios", use_container_width=True):
                                post.estado_proceso = nuevo_est
                                post.notes = nuevas_notas
                                session.commit()
                                st.success("¡Candidato actualizado!")
                                st.rerun()
                                
                        with col_del:
                            if st.form_submit_button("🗑️ Eliminar Postulación", use_container_width=True):
                                try:
                                    session.delete(post)
                                    session.commit()
                                    st.warning("Postulación eliminada por completo de la base de datos.")
                                    st.rerun()
                                except Exception as e:
                                    session.rollback()
                                    st.error(f"No se pudo eliminar: {e}")

# --- PESTAÑA 2: LECTOR DE PDF (CON PREVENCION DE DUPLICADOS) ---
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
                        # --- CONTROL INTELIGENTE DE DUPLICADOS ---
                        candidato_existente = session.query(Candidato).filter(Candidato.email == email).first()
                        
                        if candidato_existente:
                            # Si ya existe, actualizamos sus datos de perfil con la información más nueva
                            candidato_existente.nombre = nom
                            candidato_existente.telefono = telef
                            candidato_existente.direccion = direccion
                            candidato_existente.archivo_cv = bytes_pdf
                            candidato_existente.ruta_cv = archivo.name
                            candidato_id = candidato_existente.id
                            st.info("ℹ️ Se detectó que el correo ya existe. Se actualizaron los datos personales y el CV del candidato.")
                        else:
                            # Si es nuevo, lo creamos
                            nuevo_c = Candidato(
                                nombre=nom, 
                                email=email, 
                                telefono=telef, 
                                direccion=direccion, 
                                archivo_cv=bytes_pdf,
                                ruta_cv=archivo.name
                            )
                            session.add(nuevo_c)
                            session.flush()  # Generamos el ID temporalmente para la relación
                            candidato_id = nuevo_c.id
                        
                        # Verificamos si ya está postulado a este puesto en particular
                        postulacion_existente = session.query(Postulacion).filter(
                            Postulacion.candidato_id == candidato_id,
                            Postulacion.vacante_id == opciones_vacantes[puesto_sel]
                        ).first()
                        
                        if postulacion_existente:
                            st.warning(f"⚠️ El candidato ya se postuló previamente para '{puesto_sel}'. Estado actual: '{postulacion_existente.estado_proceso}'. No se duplicó el registro.")
                        else:
                            # Agregamos la nueva postulación
                            session.add(Postulacion(
                                candidato_id=candidato_id, 
                                vacante_id=opciones_vacantes[puesto_sel], 
                                estado_proceso="CV Recibido", 
                                notes="CV subido al sistema Biofactor."
                            ))
                            session.commit()
                            st.success(f"¡{nom} registrado con éxito en '{puesto_sel}'!")
                            st.rerun()
            except Exception as e:
                st.error(f"Error al procesar: {e}")

session.close()
