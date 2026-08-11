import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, joinedload, defer
from crear_base import Candidato, Vacante, Postulacion, Base
import pypdf
import re
from datetime import datetime, timedelta

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

# --- CONSULTAS CACHEADAS ---
@st.cache_data(ttl=60)
def obtener_postulaciones_optimizado():
    """Trae las postulaciones con JOINs optimizados y defer para excluir los archivos PDF pesados."""
    session = SessionFactory()
    try:
        results = session.query(Postulacion)\
            .options(
                joinedload(Postulacion.candidato).defer(Candidato.archivo_cv),
                joinedload(Postulacion.vacante)
            ).all()
        session.expunge_all() # Desconecta de la sesión para ser mutable en cache
        return results
    except Exception:
        return []
    finally:
        session.close()

@st.cache_data(ttl=60)
def obtener_vacantes_cached():
    session = SessionFactory()
    try:
        results = session.query(Vacante).all()
        session.expunge_all()
        return results
    except Exception:
        return []
    finally:
        session.close()

def descargar_cv_por_id(candidato_id):
    """Consulta rápida en base de datos únicamente cuando el usuario pide descargar el PDF."""
    session = SessionFactory()
    try:
        cand = session.query(Candidato).filter(Candidato.id == candidato_id).first()
        return cand.archivo_cv if cand else None
    finally:
        session.close()

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
    "Contratado",
    "Archivado Histórico"
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
    elif estado == "Archivado Histórico":
        return "#f3f4f6", "#6b7280" # Gris oscuro
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

# --- FUNCIÓN DE LIMPIEZA Y ARCHIVADO (90 DÍAS) ---
def archivar_postulantes_antiguos(dias_limite=90):
    """
    Busca postulantes en 'No Aplica' que llevan más de X días en la base de datos,
    elimina el binario del PDF para liberar espacio en la BD y cambia su estado a 'Archivado Histórico'.
    """
    session = get_session()
    try:
        fecha_corte = datetime.now() - timedelta(days=dias_limite)
        
        # Consultamos las postulaciones en descartados
        postulaciones_descartadas = session.query(Postulacion).join(Candidato).filter(
            Postulacion.estado_proceso.in_(["No Aplica", "Rechazado"])
        ).all()
        
        contador = 0
        for post in postulaciones_descartadas:
            # Si el modelo Candidato tiene fecha o evaluamos la pos:
            # Eliminamos el PDF pesado de la BD para liberar espacio en la nube
            if post.candidato:
                post.candidato.archivo_cv = None
                post.candidato.ruta_cv = None
            
            post.estado_proceso = "Archivado Histórico"
            contador += 1
            
        session.commit()
        st.cache_data.clear() # Limpiamos caché para refrescar vistas
        return contador
    except Exception as e:
        session.rollback()
        return 0
    finally:
        session.close()

# --- FRAGMENTO DE TARJETA DE CANDIDATO ---
@st.fragment
def renderizar_tarjeta_candidato(post):
    """Aisla la interacción de cada tarjeta para evitar recargar toda la interfaz de usuario."""
    cand = post.candidato
    vac = post.vacante
    
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
            # Carga diferida bajo demanda del binario PDF
            if cand.ruta_cv:
                archivo_bytes = descargar_cv_por_id(cand.id)
                if archivo_bytes:
                    st.download_button(
                        label="📄 Descargar CV",
                        data=archivo_bytes,
                        file_name=f"CV_{cand.nombre.replace(' ', '_')}.pdf",
                        mime="application/pdf",
                        key=f"dl_{cand.id}_{post.id}",
                        use_container_width=True
                    )
                else:
                    st.caption("PDF no disponible")
            else:
                st.caption("PDF depurado / Sin archivo")

        st.markdown("<hr style='border:none; border-top: 1px dashed #e2e8f0; margin:15px 0;'>", unsafe_allow_html=True)

        # Formulario de Actualización Rápida
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
                    session = SessionFactory()
                    try:
                        p = session.query(Postulacion).get(post.id)
                        p.estado_proceso = nuevo_est
                        p.notes = nuevas_notas
                        session.commit()
                        st.cache_data.clear() # Invalida la caché de búsquedas
                        st.success("Guardado correctamente.")
                        st.rerun()
                    except Exception as e:
                        session.rollback()
                        st.error(f"Error: {e}")
                    finally:
                        session.close()

            with btn2:
                if st.form_submit_button("🗑️ Eliminar", use_container_width=True):
                    session = SessionFactory()
                    try:
                        p = session.query(Postulacion).get(post.id)
                        session.delete(p)
                        session.commit()
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        session.rollback()
                        st.error(f"Error: {e}")
                    finally:
                        session.close()

        # Edición de Contacto Plegable
        with st.popover("✏️ Editar datos de contacto"):
            with st.form(key=f"form_contact_{post.id}"):
                nuevo_nombre = st.text_input("Nombre Completo:", value=cand.nombre)
                nuevo_email = st.text_input("Email:", value=cand.email)
                nuevo_telefono = st.text_input("Teléfono:", value=cand.telefono if cand.telefono else "")
                nueva_direccion = st.text_input("Dirección:", value=cand.direccion if cand.direccion else "")
                
                if st.form_submit_button("Actualizar Contacto", use_container_width=True):
                    session = SessionFactory()
                    try:
                        c = session.query(Candidato).get(cand.id)
                        c.nombre = nuevo_nombre
                        c.email = nuevo_email
                        c.telefono = nuevo_telefono
                        c.direccion = nueva_direccion
                        session.commit()
                        st.cache_data.clear()
                        st.success("Contacto actualizado.")
                        st.rerun()
                    except Exception as e:
                        session.rollback()
                        st.error(f"Error: {e}")
                    finally:
                        session.close()

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
    postulaciones_db = obtener_postulaciones_optimizado()

    # Cálculo rápido de métricas sobre datos cacheados (Excluyendo archivados históricos de los conteos primarios)
    total_todos = sum(1 for p in postulaciones_db if p.estado_proceso != "Archivado Histórico")
    total_activos = sum(1 for p in postulaciones_db if p.estado_proceso in ETAPAS_ACTIVAS)
    total_contratados = sum(1 for p in postulaciones_db if p.estado_proceso == "Contratado")
    total_no_aplica = sum(1 for p in postulaciones_db if p.estado_proceso in ["No Aplica", "Rechazado", "Perfil en Reserva"])

    if "filtro_estado" not in st.session_state:
        st.session_state.filtro_estado = "Todos"

    # Tarjetas de Métricas / Filtros Rápidos superiores
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        if st.button(f"👥 Activos ({total_todos})", use_container_width=True, type="primary" if st.session_state.filtro_estado == "Todos" else "secondary"):
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
        if st.button(f"📁 Descartados ({total_no_aplica})", use_container_width=True, type="primary" if st.session_state.filtro_estado == "No Aplica" else "secondary"):
            st.session_state.filtro_estado = "No Aplica"
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # Filtros de Puesto y Búsqueda
    vacantes_db = obtener_vacantes_cached()
    opciones_puestos = ["Todos los Puestos"] + [v.titulo for v in vacantes_db]

    f_col1, f_col2 = st.columns([1, 1])
    with f_col1:
        puesto_seleccionado = st.selectbox("Filtrar por Puesto:", opciones_puestos)
    with f_col2:
        busqueda = st.text_input("Buscar candidato o palabra clave:", placeholder="Ej: Nombre, email, ciudad...")

    st.markdown("<hr style='border:none; border-top: 1px solid #e2e8f0; margin: 20px 0;'>", unsafe_allow_html=True)

    # Filtrado de Candidatos en memoria
    postulaciones_filtradas = []
    for post in postulaciones_db:
        # Por defecto, nunca mostramos Archivados Históricos a menos que se busque específicamente
        if post.estado_proceso == "Archivado Histórico" and not busqueda:
            continue

        if st.session_state.filtro_estado == "Todos" and post.estado_proceso == "Archivado Histórico":
            continue
        elif st.session_state.filtro_estado == "Activos" and post.estado_proceso not in ETAPAS_ACTIVAS:
            continue
        elif st.session_state.filtro_estado == "Contratados" and post.estado_proceso != "Contratado":
            continue
        elif st.session_state.filtro_estado == "No Aplica" and post.estado_proceso not in ["No Aplica", "Rechazado", "Perfil en Reserva"]:
            continue

        cand = post.candidato
        vac = post.vacante

        if cand and vac:
            if puesto_seleccionado != "Todos los Puestos" and vac.titulo != puesto_seleccionado:
                continue

            dir_texto = cand.direccion if cand.direccion else ""
            notes_texto = post.notes if post.notes else ""
            texto_completo = f"{cand.nombre} {cand.email} {str(notes_texto)} {vac.titulo} {dir_texto}".lower()
            if busqueda and busqueda.lower() not in texto_completo:
                continue

            postulaciones_filtradas.append(post)

    # Paginador simple para acelerar la vista del DOM
    POSTULANTES_POR_PAGINA = 15
    total_postulantes = len(postulaciones_filtradas)

    if total_postulantes > 0:
        if total_postulantes > POSTULANTES_POR_PAGINA:
            total_paginas = max(1, (total_postulantes + POSTULANTES_POR_PAGINA - 1) // POSTULANTES_POR_PAGINA)
            col_pag1, col_pag2 = st.columns([3, 1])
            with col_pag2:
                pagina_actual = st.number_input("Página:", min_value=1, max_value=total_paginas, step=1, value=1)
            inicio = (pagina_actual - 1) * POSTULANTES_POR_PAGINA
            fin = inicio + POSTULANTES_POR_PAGINA
            postulaciones_pagina = postulaciones_filtradas[inicio:fin]
        else:
            postulaciones_pagina = postulaciones_filtradas

        # Renderizado optimizado
        for post in postulaciones_pagina:
            renderizar_tarjeta_candidato(post)
    else:
        st.info("No se encontraron postulantes con los filtros seleccionados.")

    # --- SECCIÓN INFERIOR DE MANTENIMIENTO ---
    st.markdown("<br><br>", unsafe_allow_html=True)
    with st.expander("⚙️ Mantenimiento y Depuración de Base de Datos"):
        st.write("Esta herramienta busca postulantes en estado **'No Aplica'**, elimina el archivo PDF binario para liberar espacio en el servidor de PostgreSQL y los oculta de la vista principal pasándolos a **'Archivado Histórico'**.")
        if st.button("📦 Archivar y Liberar Espacio de Descartados (+90 días)", use_container_width=False):
            procesados = archivar_postulantes_antiguos(dias_limite=90)
            if procesados > 0:
                st.success(f"Se archivaron y liberaron {procesados} candidatos descartados correctamente.")
                st.rerun()
            else:
                st.info("No hay postulantes descartados pendientes de depurar.")

# --- PESTAÑA 2: LECTOR PDF ---
with tab2:
    st.subheader("Cargar Nuevo Postulante")
    lista_vacantes = obtener_vacantes_cached()

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
                                st.cache_data.clear() # Limpia la caché al crear un nuevo candidato
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
            "Area Comercial", 
            "Area Comercio Exterior", 
            "Area Tecnica", 
            "Area Gerencial", 
            "Area Contable", 
            "Area Operativo"
        ])

        if st.form_submit_button("Crear Puesto") and nuevo_titulo:
            session_v = get_session()
            try:
                session_v.add(Vacante(titulo=nuevo_titulo, departamento=depto_seleccionado, estado="Abierta"))
                session_v.commit()
                st.cache_data.clear() # Limpia la caché al agregar puesto
                st.success(f"Puesto '{nuevo_titulo}' creado con éxito.")
                st.rerun()
            except Exception as e:
                session_v.rollback()
                st.error(f"Error al guardar: {e}")
            finally:
                session_v.close()
