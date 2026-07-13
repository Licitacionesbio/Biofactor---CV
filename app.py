import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from crear_base import Candidato, Vacante, Postulacion, Base
import pypdf
import re

# Conexión limpia a la base de datos
engine = create_engine('sqlite:///bolsa_empleo.db')

# Esta línea detectará la nueva columna y la sumará si no existe
Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)
session = Session()

st.set_page_config(page_title="Biofactor", layout="wide")
st.image("logo.png", width=120)
st.title("Vacante y Postulantes")
st.markdown("---")

# Navegación por pestañas
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
                st.error(f"Error: {e}")

# --- PESTAÑA 1: PANEL DE GESTIÓN RRHH ---
with tab1:
    st.subheader("🔍 Buscador de Talento")
    busqueda = st.text_input("Filtrar candidatos por palabra clave:", value="")
    st.markdown("---")
    
    col1, col2 = st.columns([1, 2])
    
    if "puesto_seleccionado" not in st.session_state:
        st.session_state.puesto_seleccionado = None

    with col1:
        st.subheader("🎯 Puestos Activos")
        if st.button("✨ Ver Todos los Postulantes", use_container_width=True):
            st.session_state.puesto_seleccionado = None
            st.rerun()
            
        st.write("---")
        for vac in session.query(Vacante).all():
            es_activo = st.session_state.puesto_seleccionado == vac.id
            label_boton = f"📌 {vac.titulo} ({vac.departamento})" if es_activo else f"{vac.titulo} ({vac.departamento})"
            if st.button(label_boton, key=f"btn_vac_{vac.id}", use_container_width=True, type="primary" if es_activo else "secondary"):
                st.session_state.puesto_seleccionado = vac.id
                st.rerun()
        
    with col2:
        if st.session_state.puesto_seleccionado:
            vac_actual = session.query(Vacante).filter(Vacante.id == st.session_state.puesto_seleccionado).first()
            if vac_actual:
                st.subheader(f"👤 Postulantes para: {vac_actual.titulo}")
            else:
                st.subheader("👤 Todos los Postulantes")
        else:
            st.subheader("👤 Todos los Postulantes")
            
        for post in session.query(Postulacion).all():
            if st.session_state.puesto_seleccionado and post.vacante_id != st.session_state.puesto_seleccionado:
                continue
                
            cand = session.query(Candidato).filter(Candidato.id == post.candidato_id).first()
            vac = session.query(Vacante).filter(Vacante.id == post.vacante_id).first()
            
            if cand and vac:
                dir_texto = cand.direccion if cand.direccion else ""
                texto_completo = f"{cand.nombre} {cand.email} {str(post.notas)} {vac.titulo} {dir_texto}".lower()
                if busqueda.lower() not in texto_completo:
                    continue
                    
                with st.expander(f"👤 {cand.nombre} -> 🎯 {vac.titulo} | [{post.estado_proceso}]"):
                    st.write(f"📧 **Email:** {cand.email} | 📞 **Teléfono:** {cand.telefono}")
                    st.write(f"📍 **Ubicación / Barrio:** {cand.direccion if cand.direccion else 'No especificado'}")
                    
                    # --- BOTÓN DE DESCARGA DIRECTA DEL CV ---
                    if cand.archivo_cv:
                        st.download_button(
                            label="📥 Descargar CV (PDF)",
                            data=cand.archivo_cv,
                            file_name=f"CV_{cand.nombre.replace(' ', '_')}.pdf",
                            mime="application/pdf",
                            key=f"dl_{cand.id}"
                        )
                    else:
                        st.info("No hay un archivo PDF guardado para este candidato.")
                    
                    st.write("---")
                    
                    # Formulario individual de actualización rápida
                    with st.form(key=f"form_update_{post.id}"):
                        estados = ["CV Recibido", "Entrevista RRHH", "Prueba Técnica", "Entrevista Manager", "Oferta", "Rechazado", "Contratado"]
                        idx_actual = estados.index(post.estado_proceso) if post.estado_proceso in estados else 0
                        
                        nuevo_est = st.selectbox("Cambiar Etapa:", estados, index=idx_actual)
                        notas_actuales = post.notas if post.notas else ""
                        nuevas_notas = st.text_area("Notas / Comentarios del candidato:", value=notas_actuales, placeholder="Escribe aquí el feedback...")
                        
                        if st.form_submit_button("Guardar Cambios"):
                            post.estado_proceso = nuevo_est
                            post.notas = nuevas_notas
                            session.commit()
                            st.success("¡Candidato actualizado!")
                            st.rerun()

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
                # Extraemos los bytes puros del PDF subido
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
                        # Guardamos los bytes en archivo_cv y mantenemos la compatibilidad anterior
                        nuevo_c = Candidato(
                            nombre=nom, 
                            email=email, 
                            telefono=telef, 
                            direccion=direccion, 
                            archivo_cv=bytes_pdf,
                            ruta_cv=archivo.name
                        )
                        session.add(nuevo_c)
                        session.flush()
                        
                        session.add(Postulacion(candidato_id=nuevo_c.id, vacante_id=opciones_vacantes[puesto_sel], estado_proceso="CV Recibido", notas="CV subido al sistema Biofactor."))
                        session.commit()
                        st.success(f"¡{nom} registrado con éxito!")
                        st.rerun()
            except Exception as e:
                st.error(f"Error al procesar: {e}")

session.close()
