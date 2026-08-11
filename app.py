import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session
from crear_base import Candidato, Vacante, Postulacion, Base
import pypdf
import re

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Biofactor RRHH", layout="wide", initial_sidebar_state="collapsed")

# --- INYECCIÓN DE ESTILOS CSS MODERNOS Y MINIMALISTAS ---
st.markdown("""
    <style>
    /* Estilos globales */
    .main {
        background-color: #f8fafc !important;
    }
    
    /* Tipografía y títulos */
    h1, h2, h3 {
        color: #0f172a !important;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
        font-weight: 600 !important;
    }
    
    /* Tarjetas de Expanders / Candidatos */
    div[data-testid="stExpander"] {
        background-color: #ffffff !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 12px !important;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05) !important;
        margin-bottom: 16px !important;
        transition: all 0.2s ease !important;
    }
    
    div[data-testid="stExpander"]:hover {
        border-color: #cbd5e1 !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.07) !important;
    }
    
    div[data-testid="stExpander"] summary {
        font-weight: 600 !important;
        font-size: 15px !important;
        color: #1e293b !important;
        padding: 12px 16px !important;
    }

    /* Botones primarios y secundarios */
    .stButton>button {
        border-radius: 8px !important;
        font-weight: 500 !important;
        font-size: 14px !important;
        border: 1px solid #cbd5e1 !important;
    }
    
    /* Pestañas */
    button[data-baseweb="tab"] {
        font-size: 15px !important;
        font-weight: 600 !important;
        color: #64748b !important;
    }
    
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #0f766e !important;
    }
    
    /* Modificación de Inputs */
    .stTextInput>div>div>input, .stSelectbox>div>div>div {
        border-radius: 8px !important;
        border: 1px solid #cbd5e1 !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- CONEXIÓN A BASE DE DATOS ---
@st.cache_resource
def get_db_engine():
    if "database" in st.secrets:
        DATABASE_URL = st.secrets["database"]["url"]
        if DATABASE_URL.startswith("postgres://"):
            DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
        elif DATABASE_URL.startswith("postgresql://"):
            DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
        
        DATABASE_URL = DATABASE_URL.replace("-pooler.", ".")
        DATABASE_URL = DATABASE_URL.replace("&channel_binding=require", "")
        
        try:
            engine = create_engine(
                DATABASE_URL, 
                connect_args={"sslmode": "require", "connect_timeout": 5},
                pool_pre_ping=True,
                pool_recycle=300
            )
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return engine, True
        except Exception:
            return create_engine('sqlite:///bolsa_empleo.db'), False
    else:
        return create_engine('sqlite:///bolsa_empleo.db'), False

engine, connection_successful = get_db_engine()
Base.metadata.create_all(engine)

@st.cache_resource
def get_session_factory(_engine):
    return sessionmaker(bind=_engine)

SessionFactory = get_session_factory(engine)

def get_session():
    return SessionFactory()

# --- ETAPAS DEL PROCESO ---
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

ETAPAS_ACTIVAS = [
    "CV Recibido",
    "Entrevista Director Comercial",
    "Entrevista RRHH",
    "Entrevista Presencial",
    "Entrevista Gerencia",
    "Aplica",
    "Preocupacional"
]

# Auxiliar para colores de badges de estado
def obtener_color_badge(estado):
    if estado == "Contratado":
        return "#dcfce7", "#166534" # Verde
    elif estado in ["No Aplica", "Rechazado"]:
        return "#fee2e2", "#991b1b" # Rojo
    elif estado == "Aplica":
        return "#e0f2fe", "#075985" # Azul
    else:
        return "#f1f5f9", "#334155" # Gris neutro

# Auxiliar para WhatsApp
def obtener_link_whatsapp(telefono_str):
    if not telefono_str:
        return None
    numeros = re.sub(r'\D', '', telefono_str)
    if not numeros:
        return None
    if len(numeros) <= 10 and not numeros.startswith("54"):
        numeros = "54" + numeros
    return f"https://wa.me/{numeros}"

# --- ENCABEZADO ---
header_col1, header_col2, header_col3 = st.columns([1, 8, 3])
with header_col1:
    st.image("logo.png", width=55)
with header_col2:
    st.markdown("<h2 style='margin:0; padding-top:5px;'>Gestión de Talentos — Biofactor</h2>", unsafe_allow_html=True)
with header_col3:
    if connection_successful:
        st.markdown("<div style='text-align:right; color:#16a34a; font-size:13px; padding-top:12px;'>🟢 Nube Conectada</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div style='text-align:right; color:#d97706; font-size:13px; padding-top:12px;'>🟡 Base Local</div>", unsafe_allow_html=True)

st.markdown("<div style='margin-bottom:20px;'></div>", unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["📋 Panel de Postulantes", "➕ Cargar Candidato (PDF)", "🎯 Configurar Puestos"])

# --- PESTAÑA 1: PANEL RRHH ---
with tab1:
    session = get_session()
    try:
        total_todos = session.query(Postulacion).count()
        total_activos = session.query(Postulacion).filter(Postulacion.estado_proceso.in_(ETAPAS_ACTIVAS)).count()
        total_contratados = session.query(Postulacion).filter(Postulacion.estado_proceso == "Contratado").count()
        total_no_aplica = session.query(Postulacion).filter(Postulacion.estado_proceso.in_(["No Aplica", "Rechazado", "Perfil en Reserva"])).count()
    except Exception:
        total_todos = total_activos = total_contratados = total_no_aplica = 0
    finally:
        session.close()

    if "filtro_estado" not in st.session_state:
        st.session_state.filtro_estado = "Todos"

    # Tarjetas de Métricas / Filtros Rápidos superiores
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        if st.button(f"👥 Todos ({total_todos})", use_container_width=True, type="primary" if st.session_state.filtro_estado == "Todos" else "secondary"):
            st.session_state.filtro_estado = "Todos"
            st.rerun()
    with m2:
        if st.button(f"⚡ En Selección ({total_activos})", use_container_width=True, type="primary" if st.session_state.filtro_estado == "Activos" else "secondary"):
            st.session_state.filtro_estado = "Activos"
            st.rerun()
    with m3:
        if st.button(f"🎉 Contratados ({total_contratados})", use_container_width=True, type="primary" if st.session_state.filtro_estado == "Contratados" else "secondary"):
            st.session_state.filtro_estado = "Contratados"
            st.rerun()
    with m4:
        if st.button(f"📁 Archivados ({total_no_aplica})", use_container_width=True, type="primary" if st.session_state.filtro_estado == "No Aplica" else "secondary"):
            st.session_state.filtro_estado = "No Aplica"
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # Filtros de Puesto y Búsqueda
    session = get_session()
    try:
        vacantes_db = session.query(Vacante).all()
    except Exception:
        vacantes_db = []
    finally:
        session.close()
        
    opciones_puestos = ["Todos los Puestos"] + [v.titulo for v in vacantes_db]

    f_col1, f_col2 = st.columns([1, 1])
    with f_col1:
        puesto_seleccionado = st.selectbox("Filtrar por Puesto:", opciones_puestos)
    with f_col2:
        busqueda = st.text_input("Buscar candidato o palabra clave:", placeholder="Ej: Nombre, email, ciudad...")

    st.markdown("<hr style='border:none; border-top: 1px solid #e2e8f0; margin: 20px 0;'>", unsafe_allow_html=True)

    session = get_session()
    try:
        postulaciones_db = session.query(Postulacion).all()
    except Exception as e:
        st.error(f"Error consultando base de datos: {e}")
        postulaciones_db = []

    candidatos_mostrados = 0

    for post in postulaciones_db:
        if st.session_state.filtro_estado == "Activos" and post.estado_proceso not in ETAPAS_ACTIVAS:
            continue
        elif st.session_state.filtro_estado == "Contratados" and post.estado_proceso != "Contratado":
            continue
        elif st.session_state.filtro_estado == "No Aplica" and post.estado_proceso not in ["No Aplica", "Rechazado", "Perfil en Reserva"]:
            continue

        cand = session.query(Candidato).filter(Candidato.id == post.candidato_id).first()
        vac = session.query(Vacante).filter(Vacante.id == post.vacante_id).first()

        if cand and vac:
            if puesto_seleccionado != "Todos los Puestos" and vac.titulo != puesto_seleccionado:
                continue

            dir_texto = cand.direccion if cand.direccion else ""
            notes_texto = post.notes if post.notes else ""
            texto_completo = f"{cand.nombre} {cand.email} {str(notes_texto)} {vac.titulo} {dir_texto}".lower()
            if busqueda and busqueda.lower() not in texto_completo:
                continue

            candidatos_mostrados += 1
            
            bg_badge, fg_badge = obtener_color_badge(post.estado_proceso)
            
            label_expander = f"{cand.nombre}  —  {vac.titulo}"
            
            with st.expander(label_expander):
                col_c1, col_c2 = st.columns([3, 1])
                with col_c1:
                    st.markdown(
                        f"<span style='background-color:{bg_badge}; color:{fg_badge}; font-weight:600; padding:4px 12px; border-radius:12px; font-size:13px;'>"
                        f"Etapa: {post.estado_proceso}"
                        f"</span>", 
                        unsafe_allow_html=True
                    )
                
                st.markdown("<br>", unsafe_allow_html=True)

                info_col1, info_col2, info_col3 = st.columns([2, 2, 1.5])
                
                with info_col1:
                    st.caption("DATOS DE CONTACTO")
                    st.write(f"📧 **Email:** {cand.email}")
                    st.write(f"📍 **Ubicación:** {cand.direccion if cand.direccion else 'No especificada'}")
                
                with info_col2:
                    st.caption("TELÉFONO Y ACCIÓN")
                    st.write(f"📞 {cand.telefono if cand.telefono else 'No registrado'}")
                    link_wa = obtener_link_whatsapp(cand.telefono)
                    if link_wa:
                        st.markdown(f"[💬 Abrir Chat de WhatsApp]({link_wa})")

                with info_col3:
                    st.caption("CURRÍCULUM")
                    if cand.archivo_cv:
                        st.download_button(
                            label="📄 Descargar CV",
                            data=cand.archivo_cv,
                            file_name=f"CV_{cand.nombre.replace(' ', '_')}.pdf",
                            mime="application/pdf",
                            key=f"dl_{cand.id}_{post.id}",
                            use_container_width=True
                        )
                    else:
                        st.caption("Sin archivo PDF")

                st.markdown("<hr style='border:none; border-top: 1px dashed #e2e8f0; margin:15px 0;'>", unsafe_allow_html=True)

                # Formulario de Actualización
                with st.form(key=f"form_quick_update_{post.id}"):
                    st.caption("ACTUALIZAR PROCESO DE SELECCIÓN")
                    
                    estado_actual = post.estado_proceso
                    if estado_actual == "CV recibido": estado_actual = "CV Recibido"
                    elif estado_actual in ["Rechazado", "Perfil en Reserva"]: estado_actual = "No Aplica"
                    elif estado_actual in ["Entrevista con Gerencia", "Entrevista con gerencia"]: estado_actual = "Entrevista Gerencia"
                    
                    idx_actual = ETAPAS_PROCESO.index(estado_actual) if estado_actual in ETAPAS_PROCESO else 0
                    
                    col_sel, col_notes = st.columns([1, 2])
                    with col_sel:
                        nuevo_est = st.selectbox("Cambiar Etapa:", ETAPAS_PROCESO, index=idx_actual, key=f"sel_{post.id}")
                    with col_notes:
                        nuevas_notas = st.text_input("Notas de entrevista / comentarios:", value=post.notes if post.notes else "", key=f"notes_{post.id}")

                    btn1, btn2 = st.columns([3, 1])
                    with btn1:
                        if st.form_submit_button("Guardar Cambios", use_container_width=True):
                            try:
                                post.estado_proceso = nuevo_est
                                post.notes = nuevas_notas
                                session.commit()
                                st.success("Guardado correctamente.")
                                st.rerun()
                            except Exception as e:
                                session.rollback()
                                st.error(f"Error: {e}")
                    with btn2:
                        if st.form_submit_button("🗑️ Eliminar", use_container_width=True):
                            try:
                                session.delete(post)
                                session.commit()
                                st.rerun()
                            except Exception as e:
                                session.rollback()
                                st.error(f"Error: {e}")

                # Edición de Contacto Plegable
                with st.popover("✏️ Editar datos de contacto"):
                    with st.form(key=f"form_contact_{post.id}"):
                        nuevo_nombre = st.text_input("Nombre Completo:", value=cand.nombre)
                        nuevo_email = st.text_input("Email:", value=cand.email)
                        nuevo_telefono = st.text_input("Teléfono:", value=cand.telefono if cand.telefono else "")
                        nueva_direccion = st.text_input("Dirección:", value=cand.direccion if cand.direccion else "")
                        
                        if st.form_submit_button("Actualizar Contacto", use_container_width=True):
                            try:
                                cand.nombre = nuevo_nombre
                                cand.email = nuevo_email
                                cand.telefono = nuevo_telefono
                                cand.direccion = nueva_direccion
                                session.commit()
                                st.success("Contacto actualizado.")
                                st.rerun()
                            except Exception as e:
                                session.rollback()
                                st.error(f"Error: {e}")

    if candidatos_mostrados == 0:
        st.info("No se encontraron postulantes con los filtros seleccionados.")
    
    session.close()

# --- PESTAÑA 2: LECTOR PDF ---
with tab2:
    st.subheader("Cargar Nuevo Postulante")
    session = get_session()
    try:
        lista_vacantes = session.query(Vacante).all()
    except Exception:
        lista_vacantes = []
    finally:
        session.close()

    if not lista_vacantes:
        st.warning("⚠️ Primero debes crear al menos un puesto laboral.")
    else:
        opciones_vacantes = {v.titulo: v.id for v in lista_vacantes}
        archivo = st.file_uploader("Adjuntar archivo PDF del Curriculum", type=["pdf"])

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
                    st.write("### Confirmar información detectada")
                    puesto_sel = st.selectbox("Puesto al que postula:", list(opciones_vacantes.keys()))
                    nom = st.text_input("Nombre completo:", value=nom_sug)
                    email = st.text_input("Email de contacto:", value=em.group(0) if em else "")
                    telef = st.text_input("Teléfono:", value=tel.group(0).strip() if tel else "")
                    direccion = st.text_input("Dirección / Localidad:", value=dir_sug)

                    if st.form_submit_button("Guardar Postulante", use_container_width=True) and nom and email:
                        session_pdf = get_session()
                        try:
                            candidato_existente = session_pdf.query(Candidato).filter(Candidato.email == email).first()

                            if candidato_existente:
                                candidato_existente.nombre = nom
                                candidato_existente.telefono = telef
                                candidato_existente.direccion = direccion
                                candidato_existente.archivo_cv = bytes_pdf
                                candidato_existente.ruta_cv = archivo.name
                                candidato_id = candidato_existente.id
                            else:
                                nuevo_c = Candidato(
                                    nombre=nom, email=email, telefono=telef, direccion=direccion,
                                    archivo_cv=bytes_pdf, ruta_cv=archivo.name
                                )
                                session_pdf.add(nuevo_c)
                                session_pdf.flush()
                                candidato_id = nuevo_c.id

                            postulacion_existente = session_pdf.query(Postulacion).filter(
                                Postulacion.candidato_id == candidato_id,
                                Postulacion.vacante_id == opciones_vacantes[puesto_sel]
                            ).first()

                            if postulacion_existente:
                                st.warning(f"Este candidato ya está registrado en este puesto ({postulacion_existente.estado_proceso}).")
                            else:
                                session_pdf.add(Postulacion(
                                    candidato_id=candidato_id,
                                    vacante_id=opciones_vacantes[puesto_sel],
                                    estado_proceso="CV Recibido",
                                    notes="CV registrado en el sistema."
                                ))
                                session_pdf.commit()
                                st.success(f"¡{nom} registrado con éxito!")
                                st.rerun()
                        except Exception as e:
                            session_pdf.rollback()
                            st.error(f"Error guardando postulante: {e}")
                        finally:
                            session_pdf.close()
            except Exception as e:
                st.error(f"Error al procesar el documento PDF: {e}")

# --- PESTAÑA 3: CREAR VACANTE ---
with tab3:
    st.subheader("Crear Puesto Laboral")
    with st.form("form_crear_vacante"):
        nuevo_titulo = st.text_input("Nombre de la Vacante / Puesto:")
        depto_seleccionado = st.selectbox("Área:", [
            "Area Comercial", "Area Tecnica", "Area Gerencial", "Area Contable", "Area Operativo"
        ])

        if st.form_submit_button("Crear Puesto") and nuevo_titulo:
            session_v = get_session()
            try:
                session_v.add(Vacante(titulo=nuevo_titulo, departamento=depto_seleccionado, estado="Abierta"))
                session_v.commit()
                st.success(f"Puesto '{nuevo_titulo}' creado con éxito.")
                st.rerun()
            except Exception as e:
                session_v.rollback()
                st.error(f"Error al guardar: {e}")
            finally:
                session_v.close()
