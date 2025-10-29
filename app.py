# --- Archivo: app.py (V6.1 - Fix Bucle Pop-up) ---

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
from supabase import create_client, Client
import json
import time 

# Importamos nuestros módulos locales (asumiendo que database.py y ui_views.py están en la misma carpeta)
import database as db
import ui_views as views


# --- 1. CONEXIÓN Y CARGA DE DATOS ---

@st.cache_resource
def init_supabase_connection():
    """Inicializa la conexión con Supabase usando los secretos."""
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"Error al conectar con Supabase: {e}")
        st.stop()

def init_session_state(supabase_client, user_id, force_load=False):
    """Carga todos los datos del usuario desde Supabase al session_state."""
    # V5.0 Lógica de carga sin cambios
    if 'transactions_df' not in st.session_state or force_load:
        # Cargar todo desde Supabase
        st.session_state.transactions_df = db.load_data(supabase_client, db.TRANSACTIONS_TABLE, user_id, db.DEFAULT_TRANSACTIONS)
        st.session_state.accounts_df = db.load_data(supabase_client, db.ACCOUNTS_TABLE, user_id, db.DEFAULT_ACCOUNTS)
        st.session_state.goals_df = db.load_data(supabase_client, db.GOALS_TABLE, user_id, db.DEFAULT_GOALS)
        st.session_state.categories = db.load_categories(supabase_client, user_id)
        st.session_state.members = db.load_members(supabase_client, user_id)
        
        # Cargar configuraciones
        st.session_state.budget_config = db.load_budget_config(supabase_client, user_id)
        st.session_state.category_budgets = db.load_category_budgets(supabase_client, user_id)
        st.session_state['data_loaded'] = True # Indicador de que la carga inicial ha ocurrido
        
    # V5.0 Lógica de filtros y metas sin cambios
    force_recalc = st.session_state.get('force_filter_recalc', False) 

    if 'active_tab' not in st.session_state or force_load or force_recalc:
        date_min_data = st.session_state.transactions_df['Fecha'].min().date() if not st.session_state.transactions_df.empty else datetime.now().date()
        date_max_data = st.session_state.transactions_df['Fecha'].max().date() if not st.session_state.transactions_df.empty else datetime.now().date()
        max_input_value = datetime.now().date()
        thirty_days_ago = max(date_min_data, max_input_value - timedelta(days=30))
        
        if force_recalc or force_load:
             default_start = date_min_data
        else:
             default_start = thirty_days_ago

        st.session_state.filter_start_date = default_start
        st.session_state.filter_end_date = date_max_data
        st.session_state.filter_dates = [default_start, date_max_data]
        
        if 'active_tab' not in st.session_state: 
             st.session_state.filter_type = 'Todos'
             st.session_state.filter_member = 'Todos'
             st.session_state.active_tab = "📊 Dash" 
        
        if force_recalc:
             st.session_state.force_filter_recalc = False 

    # Sincronizar metas
    if 'goals_df' in st.session_state and 'Monto Objetivo' in st.session_state.goals_df.columns:
        transactions_to_use = st.session_state.transactions_df.copy() if 'transactions_df' in st.session_state else pd.DataFrame()
        st.session_state.goals_df = db.update_goal_progress(
            transactions_to_use,
            st.session_state.goals_df.copy()
        )
        db.save_data(supabase_client, db.GOALS_TABLE, st.session_state.goals_df, user_id)
    elif 'goals_df' not in st.session_state and not force_load:
         st.session_state.goals_df = db.DEFAULT_GOALS.copy()
         db.save_data(supabase_client, db.GOALS_TABLE, st.session_state.goals_df, user_id)


def handle_logout(supabase_client):
    """Cierra la sesión en Supabase y limpia el estado de Streamlit."""
    try:
        supabase_client.auth.sign_out()
    except Exception as e:
        st.warning(f"Error al cerrar sesión en Supabase: {e}")
        
    keys_to_delete = ['user', 'logged_in', 'data_loaded', 'active_tab', 'transactions_df', 'accounts_df', 'goals_df', 'categories', 'members', 'budget_config', 'category_budgets', 'auth_popup_open']
    for key in keys_to_delete:
        if key in st.session_state:
            del st.session_state[key]
            
    st.rerun() 


# --- 2. VISTA DE LOGIN Y ENRUTAMIENTO ---

def view_login_page(supabase_client, app_url):
    st.title("🛡️ ¡Bienvenido a Guardian Doméstico!")
    st.write("Tu asistente de finanzas personales, ahora en la nube.")
    st.markdown("---")
    
    # V5.7 CORRECCIÓN CRÍTICA DE PROTOCOLO: Forzar HTTPS para el redireccionamiento.
    if not app_url.startswith("https://"):
        redirect_url_base = app_url.replace("http://", "https://")
    else:
        redirect_url_base = app_url
        
    # Aseguramos que la URL base termine SIN la barra final
    if redirect_url_base.endswith("/"):
        redirect_url_base = redirect_url_base[:-1]
    
    # V6.1: La URL de redirección DEBE apuntar al manejador HTML para cerrar el pop-up
    popup_redirect_url = f"{redirect_url_base}/auth_handler.html"

    st.info("⚠️ Configuración CRÍTICA: La **URL de Redirección (Callback)** en Supabase y Google Cloud DEBE ser:")
    st.code(popup_redirect_url, language='text')

    if st.button("Iniciar sesión con Google", use_container_width=True, type="primary"):
        try:
            # 1. Obtener la URL de autenticación de Supabase
            auth_url_response = supabase_client.auth.sign_in_with_oauth({
                "provider": "google",
                "options": {
                    "redirect_to": popup_redirect_url # Usamos la URL del manejador HTML
                }
            })
            
            auth_url = auth_url_response.url
            
            # 2. Abrir el pop-up (con código HTML/JS inyectado)
            st.session_state['auth_popup_open'] = True
            
            # Inyectamos el JS para abrir el pop-up
            js_code = f"""
            <script>
                // Abrir una ventana de pop-up con las dimensiones adecuadas
                window.open('{auth_url}', 'SupabaseAuth', 'width=600,height=800,scrollbars=yes');
            </script>
            """
            st.components.v1.html(js_code, height=0, width=0)
            
            st.warning("Se ha abierto una nueva ventana para el inicio de sesión. Por favor, complétalo y la ventana se cerrará automáticamente.")
            st.info("Una vez que la ventana se cierre, haz clic en 'Comprobar Sesión' a continuación.")

    
        except Exception as e:
            st.error(f"Error al iniciar sesión con Google: {e}")
            st.error("Asegúrate de haber configurado el nuevo 'auth_handler.html' como URL de redirección.")
            st.session_state['auth_popup_open'] = False

    # Botón para comprobar la sesión después de que se cierre el pop-up
    if st.session_state.get('auth_popup_open', False):
        if st.button("Comprobar Sesión", use_container_width=True, type="secondary"):
             # Forzamos una recarga para verificar la sesión en el siguiente ciclo
             st.rerun() 
             
    # V6.1: Script para ESCUCHAR el mensaje del pop-up (si la recarga automática falla)
    st.markdown("""
        <script>
        function receiveMessage(event) {
            // Solo acepta mensajes de Streamlit Cloud o Supabase (por seguridad, usamos *)
            // El handler HTML envía 'authSuccess' o 'authAttempted'
            if (event.data === 'authSuccess' || event.data === 'authAttempted') {
                // Si recibe el mensaje, fuerza la recarga de la ventana principal
                window.location.reload(); 
            }
        }
        window.addEventListener("message", receiveMessage, false);
        </script>
        """, unsafe_allow_html=True)


def main_app_content(supabase_client, user_id, user_email):
    """Contiene la aplicación principal (Sidebar y Vistas de Pestaña)."""
    
    # Cargar todos los datos del usuario en el session_state
    force_load = st.session_state.get('wizard_completed', False) or not st.session_state.get('data_loaded', False)
    init_session_state(supabase_client, user_id, force_load=force_load)
    if st.session_state.get('wizard_completed', False):
        st.session_state.wizard_completed = False # Resetear la bandera

    # --- NAVEGACIÓN EN BARRA LATERAL ---
    st.sidebar.title("🛡️ Guardian Doméstico")
    st.sidebar.markdown(f"**Versión:** 6.1 (Fix Bucle Pop-up)")
    st.sidebar.markdown("---")
    st.sidebar.write(f"Sesión iniciada como:")
    st.sidebar.success(f"**{user_email}**")
    st.sidebar.button("🔴 Cerrar Sesión", type="secondary", use_container_width=True, on_click=handle_logout, args=(supabase_client,))


    tab_names_icons = {
        "📊 Dash": "📊 Dash",
        "📝 Registrar": "📝 Registrar",
        "📋 Historial": "📋 Historial",
        "⚙️ Configurar": "⚙️ Configurar"
    }
    st.sidebar.radio(
        "Navegación Principal",
        options=tab_names_icons.keys(),
        key="active_tab",
        label_visibility="collapsed"
    )
    st.sidebar.markdown("---")

    # --- FILTROS EN BARRA LATERAL ---
    df_transactions_current = st.session_state.get('transactions_df', pd.DataFrame())
    df_filtered_for_analysis = views.view_sidebar_filters(df_transactions_current)

    # --- LÓGICA DEL ASISTENTE DE CONFIGURACIÓN ---
    # La aplicación se considera "no configurada" si no hay cuentas ni transacciones.
    if st.session_state.accounts_df.empty and st.session_state.transactions_df.empty:
         st.session_state.wizard_mode = True
    
    if st.session_state.get('wizard_mode', False):
        views.run_setup_wizard(supabase_client, user_id)
        return # Detener la app aquí hasta que el wizard termine

    # --- ENRUTADOR DE PÁGINAS (ROUTER) ---
    active_tab_key = st.session_state.get('active_tab', list(tab_names_icons.keys())[0])
    if active_tab_key == "📊 Dash":
        views.view_dash(df_filtered_for_analysis)
    elif active_tab_key == "📝 Registrar":
        views.view_register(supabase_client, user_id)
    elif active_tab_key == "⚙️ Configurar":
        views.view_config(supabase_client, user_id)
    elif active_tab_key == "📋 Historial":
        views.view_history(supabase_client, user_id)


# --- 3. FUNCIÓN PRINCIPAL DE LA APLICACIÓN ---

def main():
    st.set_page_config(
        page_title="Guardian Doméstico V6.1 - Fix Bucle Pop-up",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    supabase_client = init_supabase_connection()
    
    # --- Obtención de URL pública para redirección (Fix de localhost) ---
    app_url = os.environ.get("STREAMLIT_URL", "http://localhost:8501")
    if app_url.endswith("/"):
        app_url = app_url[:-1]

    # --- Lógica CRÍTICA para obtener la sesión del usuario directamente ---
    
    # En la solución Pop-up, el token se guarda en el fragmento (#access_token=...) 
    # de la URL del pop-up, no en los query params (?code=...) de la ventana principal.
    # Por lo tanto, Streamlit DEBE verificar si la sesión ya existe usando la API.
    
    # 1. Intentar obtener la sesión activa de Supabase
    try:
        session_info = supabase_client.auth.get_session()
        
        # 2. Si hay una sesión válida, guarda la info en session_state y procede.
        if session_info and session_info.user:
            st.session_state['user'] = session_info.user
            st.session_state['logged_in'] = True
            
        else:
            # Si no hay sesión válida, se considera no logueado.
            if 'logged_in' in st.session_state:
                del st.session_state['logged_in']
            if 'user' in st.session_state:
                del st.session_state['user']

    except Exception as e:
        # Esto sucede si no hay sesión o si la API falla.
        # Simplemente aseguramos que el estado de login esté limpio.
        if 'logged_in' in st.session_state:
            del st.session_state['logged_in']


    # --- 4. Lógica principal de enrutamiento ---
    
    # Si el usuario ya está logueado (la sesión fue guardada o persistió)
    if st.session_state.get('logged_in', False) and st.session_state.get('user'):
        user_info = st.session_state['user']
        main_app_content(supabase_client, user_info.id, user_info.email)
        
    else:
        # Usuario no logueado: Muestra la página de login
        view_login_page(supabase_client, app_url)


if __name__ == '__main__':
    main()
