# --- Archivo: database.py ---
# Versión 5.2: Base de datos en la Nube (Supabase)

import streamlit as st
import pandas as pd
import json
from datetime import datetime, timedelta
import os
import numpy as np
from supabase import Client

# --- 1. CONFIGURACIÓN Y CONSTANTES ---

# Nombres de las tablas en Supabase
TRANSACTIONS_TABLE = 'transacciones'
ACCOUNTS_TABLE = 'cuentas'
GOALS_TABLE = 'metas'
CATEGORIES_TABLE = 'categorias'
MEMBERS_TABLE = 'miembros'
CONFIG_TABLE = 'configuracion'

# Claves para la Tabla de Configuración
BUDGET_KEY = 'budget_config'
CATEGORY_BUDGET_KEY = 'category_budgets'

# --- Datos por Defecto (se usan si la DB está vacía) ---
DEFAULT_CATEGORIES = {
    'Ingreso': ['Salario', 'Freelance', 'Regalo', 'Inversión', 'Otros Ingresos'],
    'Gasto': ['Alquiler', 'Comida', 'Transporte', 'Servicios', 'Entretenimiento', 'Deudas', 'Otros Gastos']
}
DEFAULT_TRANSACTIONS = pd.DataFrame({
    'Fecha': pd.Series(dtype='datetime64[ns]'), 'Tipo': pd.Series(dtype='object'),
    'Categoría': pd.Series(dtype='object'), 'Cuenta': pd.Series(dtype='object'),
    'Monto': pd.Series(dtype='float64'), 'Descripción': pd.Series(dtype='object'),
    'Miembro': pd.Series(dtype='object'), 'Destino': pd.Series(dtype='object'),
    'Recurrente': pd.Series(dtype='bool'), 'Frecuencia': pd.Series(dtype='object')
})
DEFAULT_ACCOUNTS = pd.DataFrame({
    'Nombre': ['Efectivo'], 'Tipo': ['Efectivo'], 'Saldo Inicial': [0.0]
})
DEFAULT_MEMBERS = []
DEFAULT_GOALS = pd.DataFrame({
    'Nombre': pd.Series(dtype='object'), 'Monto Objetivo': pd.Series(dtype='float64'),
    'Monto Aportado': pd.Series(dtype='float64'), 'Fecha Objetivo': pd.Series(dtype='object')
})
DEFAULT_CATEGORY_BUDGETS = {}

# Constantes de lógica
FREQUENCY_MULTIPLIER = {
    'Mensual': 1.0, 'Quincenal': 2.0, 'Semanal': (52/12),
    'Bimensual': 0.5, 'Trimestral': 1/3, 'Anual': 1/12,
    'Única/N/A': 0.0,
}
INCOME_FREQUENCIES = ['Quincenal', 'Mensual', 'Semanal', 'Bimensual', 'Anual']
DAY_NAMES_MAP = {
    'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
    'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
}


# --- 2. FUNCIONES DE BASE DE DATOS (NUEVAS PARA SUPABASE) ---

def load_data(supabase_client: Client, table_name: str, user_id: str, default_df: pd.DataFrame):
    """Carga un DataFrame desde Supabase para un usuario específico."""
    try:
        # Cargar todos los datos que coincidan con el user_id
        response = supabase_client.table(table_name).select("*").eq("user_id", user_id).execute()

        if response.data:
            df = pd.DataFrame(response.data)
            # Limpieza de columnas de Supabase (id, user_id)
            df = df.drop(columns=['id', 'user_id'], errors='ignore')

            # --- Lógica de limpieza de tipos (muy importante) ---
            if table_name == TRANSACTIONS_TABLE:
                df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce')
                df['Monto'] = pd.to_numeric(df['Monto'], errors='coerce').fillna(0.0)
                df = df.dropna(subset=['Fecha'])
                # Asegurar columnas opcionales
                for col, default_val in [('Recurrente', False), ('Frecuencia', 'Única/N/A'), ('Miembro', 'N/A'), ('Destino', 'N/A')]:
                    if col not in df.columns: df[col] = default_val

            elif table_name == GOALS_TABLE:
                df = df.rename(columns={"Monto Objetivo": "Monto Objetivo", "Monto Aportado": "Monto Aportado", "Fecha Objetivo": "Fecha Objetivo"})
                df['Fecha Objetivo'] = pd.to_datetime(df['Fecha Objetivo'], errors='coerce').dt.date
                df['Monto Objetivo'] = pd.to_numeric(df['Monto Objetivo'], errors='coerce').fillna(0.0)
                df['Monto Aportado'] = pd.to_numeric(df['Monto Aportado'], errors='coerce').fillna(0.0)

            elif table_name == ACCOUNTS_TABLE:
                df = df.rename(columns={"Saldo Inicial": "Saldo Inicial"})
                df['Saldo Inicial'] = pd.to_numeric(df['Saldo Inicial'], errors='coerce').fillna(0.0)

            return df
        else:
            return default_df.copy() # Retorna el DataFrame por defecto si no hay datos

    except Exception as e:
        st.error(f"Error al cargar datos de '{table_name}': {e}")
        return default_df.copy()

def save_data(supabase_client: Client, table_name: str, df: pd.DataFrame, user_id: str):
    """
    Guarda un DataFrame completo en Supabase para un usuario.
    Esto BORRA y REEMPLAZA todos los datos de esa tabla para ese usuario.
    """
    try:
        # 1. Borrar todos los datos existentes de este usuario en esta tabla
        supabase_client.table(table_name).delete().eq("user_id", user_id).execute()

        # 2. Preparar los nuevos datos para insertar
        if not df.empty:
            df_to_save = df.copy()

            # Añadir el user_id a cada fila
            df_to_save['user_id'] = user_id

            # Renombrar columnas de Pandas a las de la DB
            if table_name == GOALS_TABLE:
                df_to_save = df_to_save.rename(columns={"Monto Objetivo": "Monto Objetivo", "Monto Aportado": "Monto Aportado", "Fecha Objetivo": "Fecha Objetivo"})
            elif table_name == ACCOUNTS_TABLE:
                 df_to_save = df_to_save.rename(columns={"Saldo Inicial": "Saldo Inicial"})

            # Convertir fechas a strings ISO para que Supabase (JSON) las entienda
            if 'Fecha' in df_to_save.columns:
                 df_to_save['Fecha'] = pd.to_datetime(df_to_save['Fecha']).dt.isoformat()
            if 'Fecha Objetivo' in df_to_save.columns:
                df_to_save['Fecha Objetivo'] = pd.to_datetime(df_to_save['Fecha Objetivo']).dt.isoformat()

            # Convertir DataFrame a lista de diccionarios
            data_to_insert = df_to_save.to_dict('records')

            # 3. Insertar los nuevos datos
            supabase_client.table(table_name).insert(data_to_insert).execute()

    except Exception as e:
        st.error(f"Error fatal al guardar datos en '{table_name}': {e}")

# --- Funciones de Carga/Guardado Específicas ---

def load_categories(supabase_client: Client, user_id: str):
    """Carga las categorías del usuario."""
    try:
        response = supabase_client.table(CATEGORIES_TABLE).select("tipo, nombre").eq("user_id", user_id).execute()
        if response.data:
            categories = {}
            for row in response.data:
                if row['tipo'] not in categories:
                    categories[row['tipo']] = []
                categories[row['tipo']].append(row['nombre'])
            return categories
        else:
            return DEFAULT_CATEGORIES.copy()
    except Exception as e:
        st.error(f"Error al cargar categorías: {e}")
        return DEFAULT_CATEGORIES.copy()

def save_categories(supabase_client: Client, categories: dict, user_id: str):
    """Guarda el diccionario de categorías (borra y reemplaza)."""
    try:
        # 1. Borrar todas las categorías del usuario
        supabase_client.table(CATEGORIES_TABLE).delete().eq("user_id", user_id).execute()

        # 2. Preparar nuevas
        rows_to_insert = []
        for tipo, nombres in categories.items():
            for nombre in nombres:
                rows_to_insert.append({'user_id': user_id, 'tipo': tipo, 'nombre': nombre})

        # 3. Insertar
        if rows_to_insert:
            supabase_client.table(CATEGORIES_TABLE).insert(rows_to_insert).execute()
    except Exception as e:
        st.error(f"Error al guardar categorías: {e}")

def load_members(supabase_client: Client, user_id: str):
    """Carga los miembros del usuario."""
    try:
        response = supabase_client.table(MEMBERS_TABLE).select("nombre").eq("user_id", user_id).execute()
        if response.data:
            return sorted([row['nombre'] for row in response.data])
        else:
            return DEFAULT_MEMBERS.copy()
    except Exception as e:
        st.error(f"Error al cargar miembros: {e}")
        return DEFAULT_MEMBERS.copy()

def save_members(supabase_client: Client, members: list, user_id: str):
    """Guarda la lista de miembros (borra y reemplaza)."""
    try:
        supabase_client.table(MEMBERS_TABLE).delete().eq("user_id", user_id).execute()
        if members:
            rows_to_insert = [{'user_id': user_id, 'nombre': nombre} for nombre in members]
            supabase_client.table(MEMBERS_TABLE).insert(rows_to_insert).execute()
    except Exception as e:
        st.error(f"Error al guardar miembros: {e}")


def load_config_key(supabase_client: Client, user_id: str, key: str, default_value: any):
    """Carga una clave específica de la tabla de configuración."""
    try:
        response = supabase_client.table(CONFIG_TABLE).select("valor").eq("user_id", user_id).eq("clave", key).execute()
        if response.data:
            return response.data[0]['valor'] # El valor ya es un JSON/dict
        else:
            return default_value
    except Exception as e:
        st.error(f"Error al cargar configuración '{key}': {e}")
        return default_value

def save_config_key(supabase_client: Client, user_id: str, key: str, value: any):
    """Guarda (actualiza o inserta) una clave en la tabla de configuración."""
    try:
        # 'upsert' = update or insert
        supabase_client.table(CONFIG_TABLE).upsert({
            'user_id': user_id,
            'clave': key,
            'valor': value # Supabase maneja la conversión a JSONB
        }, on_conflict='user_id, clave').execute()
    except Exception as e:
        st.error(f"Error al guardar configuración '{key}': {e}")

# --- Funciones de Lógica Específicas (adaptadas) ---

def load_budget_config(supabase_client: Client, user_id: str):
    """Carga la configuración de presupuesto guardada."""
    today = datetime.now().date()
    default_config = {
        'period_start': today.isoformat(),
        'period_end': (today + timedelta(days=15)).isoformat(),
        'budget_amount': 1000.0
    }

    config = load_config_key(supabase_client, user_id, BUDGET_KEY, default_config)

    # Convertir strings de vuelta a objetos de fecha
    try:
        config['period_start'] = datetime.fromisoformat(config['period_start']).date()
        config['period_end'] = datetime.fromisoformat(config['period_end']).date()
    except: # Si falla, usa los defaults
        config['period_start'] = today
        config['period_end'] = (today + timedelta(days=15))

    return config

def load_category_budgets(supabase_client: Client, user_id: str):
    """Carga los presupuestos por categoría."""
    return load_config_key(supabase_client, user_id, CATEGORY_BUDGET_KEY, DEFAULT_CATEGORY_BUDGETS)


# --- Lógica de Cálculo (Sin cambios, operan en DataFrames) ---

def calculate_balance(df):
    df_neto = df[df['Tipo'] != 'Transferencia'].copy()
    ingresos = df_neto[df_neto['Tipo'] == 'Ingreso']['Monto'].sum()
    gastos = df_neto[df_neto['Tipo'] == 'Gasto']['Monto'].sum()
    return ingresos, gastos, ingresos - gastos

def calculate_daily_budget(start_date, end_date, budget_total, df_transactions):
    if not all([start_date, end_date]) or budget_total < 0:
        return 0.0, 0, 0.0
    today = datetime.now().date()
    df_transactions_filtered = df_transactions.copy()
    if pd.api.types.is_datetime64_any_dtype(df_transactions_filtered['Fecha']):
        df_transactions_filtered['Fecha'] = df_transactions_filtered['Fecha'].dt.date
    else:
        df_transactions_filtered['Fecha'] = pd.to_datetime(df_transactions_filtered['Fecha']).dt.date

    gastos_realizados = df_transactions_filtered[
        (df_transactions_filtered['Tipo'] == 'Gasto') &
        (df_transactions_filtered['Fecha'] >= start_date) &
        (df_transactions_filtered['Fecha'] <= end_date)
    ]['Monto'].sum()
    presupuesto_restante = budget_total - gastos_realizados
    if today > end_date:
        days_left = 0
    elif today < start_date:
        days_left = (end_date - start_date).days + 1
    else:
        days_left = (end_date - today).days + 1
    if days_left > 0:
        daily_budget = presupuesto_restante / days_left
    else:
        daily_budget = 0.0
    return daily_budget, days_left, presupuesto_restante

def update_goal_progress(df_transactions, df_goals):
    if df_goals.empty or 'Nombre' not in df_goals.columns:
        return df_goals
    goal_names = df_goals['Nombre'].tolist()
    if df_transactions.empty or 'Tipo' not in df_transactions.columns:
        df_contributions = pd.DataFrame(columns=['Nombre', 'Monto Calculado'])
    else:
        df_transfers_to_goals = df_transactions[
            (df_transactions['Tipo'] == 'Transferencia') &
            (df_transactions['Destino'].isin(goal_names))
        ]
        if df_transfers_to_goals.empty:
             df_contributions = pd.DataFrame(columns=['Nombre', 'Monto Calculado'])
        else:
            df_contributions = df_transfers_to_goals.groupby('Destino')['Monto'].sum().reset_index()
            df_contributions.columns = ['Nombre', 'Monto Calculado']
    cols_to_drop = ['Monto Aportado'] if 'Monto Aportado' in df_goals.columns else []
    df_goals_no_aportado = df_goals.drop(columns=cols_to_drop, errors='ignore')
    df_updated = pd.merge(
        df_goals_no_aportado,
        df_contributions,
        on='Nombre',
        how='left'
    ).fillna({'Monto Calculado': 0.0})
    df_updated['Monto Aportado'] = df_updated['Monto Calculado']
    final_cols = list(DEFAULT_GOALS.columns)
    df_updated = df_updated.reindex(columns=final_cols, fill_value=0.0)
    df_updated['Monto Objetivo'] = df_updated['Monto Objetivo'].astype(float)
    df_updated['Monto Aportado'] = df_updated['Monto Aportado'].astype(float)
    df_updated['Fecha Objetivo'] = pd.to_datetime(df_updated['Fecha Objetivo']).dt.date
    return df_updated.drop(columns=['Monto Calculado'], errors='ignore')

def calculate_account_balances(df_transactions, df_accounts):
    if df_accounts.empty:
        return pd.DataFrame(columns=['Nombre', 'Tipo', 'Saldo Inicial', 'Saldo Actual'])
    df_acc_calc = df_accounts.copy()
    account_names = df_acc_calc['Nombre'].tolist()
    df_outflows = pd.DataFrame(columns=['Nombre', 'Salidas'])
    df_inflows = pd.DataFrame(columns=['Nombre', 'Entradas'])
    df_transfer_in = pd.DataFrame(columns=['Nombre', 'Entradas_T'])
    if not df_transactions.empty:
        df_outflows_raw = df_transactions[
            df_transactions['Tipo'].isin(['Gasto', 'Transferencia'])
        ]
        if not df_outflows_raw.empty:
            df_outflows = df_outflows_raw.groupby('Cuenta')['Monto'].sum().reset_index()
            df_outflows.columns = ['Nombre', 'Salidas']
        df_inflows_raw = df_transactions[
            df_transactions['Tipo'] == 'Ingreso'
        ]
        if not df_inflows_raw.empty:
            df_inflows = df_inflows_raw.groupby('Cuenta')['Monto'].sum().reset_index()
            df_inflows.columns = ['Nombre', 'Entradas']
        df_transfer_in_raw = df_transactions[
            (df_transactions['Tipo'] == 'Transferencia') &
            (df_transactions['Destino'].isin(account_names))
        ]
        if not df_transfer_in_raw.empty:
            df_transfer_in = df_transfer_in_raw.groupby('Destino')['Monto'].sum().reset_index()
            df_transfer_in.columns = ['Nombre', 'Entradas_T']
    df_acc_calc = pd.merge(df_acc_calc, df_inflows, on='Nombre', how='left')
    df_acc_calc = pd.merge(df_acc_calc, df_outflows, on='Nombre', how='left')
    df_acc_calc = pd.merge(df_acc_calc, df_transfer_in, on='Nombre', how='left')
    df_acc_calc.fillna({'Entradas': 0.0, 'Salidas': 0.0, 'Entradas_T': 0.0}, inplace=True)
    df_acc_calc['Saldo Inicial'] = pd.to_numeric(df_acc_calc['Saldo Inicial'], errors='coerce').fillna(0.0)
    df_acc_calc['Saldo Actual'] = (
        df_acc_calc['Saldo Inicial'] +
        df_acc_calc['Entradas'] +
        df_acc_calc['Entradas_T'] -
        df_acc_calc['Salidas']
    )
    return df_acc_calc.drop(columns=['Entradas', 'Salidas', 'Entradas_T'], errors='ignore')

def calculate_fixed_surplus(df_transactions):
    df_fixed = df_transactions[df_transactions['Recurrente'] == True].copy()
    if df_fixed.empty:
        return 0.0, 0.0, 0.0
    def get_monthly_amount(row):
        multiplier = FREQUENCY_MULTIPLIER.get(row['Frecuencia'], 0.0)
        return row['Monto'] * multiplier
    df_fixed['Monto Mensual'] = df_fixed.apply(get_monthly_amount, axis=1)
    monthly_income = df_fixed[df_fixed['Tipo'] == 'Ingreso']['Monto Mensual'].sum()
    monthly_expense = df_fixed[df_fixed['Tipo'] == 'Gasto']['Monto Mensual'].sum()
    surplus = monthly_income - monthly_expense
    return monthly_income, monthly_expense, surplus


# --- 5. FUNCIONES DE SINCRONIZACIÓN (Adaptadas para Supabase) ---

def sync_metadata_from_df(supabase_client: Client, user_id: str, df: pd.DataFrame):
    """
    Lee un DataFrame de transacciones (del CSV) y añade cualquier
    nueva Categoría, Miembro o Cuenta a las tablas de configuración.
    """
    changes_made_global = False

    # --- 1. Sincronizar Miembros ---
    try:
        current_members = set(st.session_state.get('members', []))
        csv_members = set(df['Miembro'].unique())
        new_members = [m for m in csv_members if m not in current_members and pd.notna(m) and m != 'N/A']

        if new_members:
            st.session_state.members.extend(new_members)
            st.session_state.members.sort()
            save_members(supabase_client, st.session_state.members, user_id) # Usar nueva función
            st.toast(f"👥 ¡Se añadieron {len(new_members)} nuevos miembros!", icon="👥")
            changes_made_global = True
    except Exception as e:
        st.warning(f"Error al sincronizar miembros: {e}")

    # --- 2. Sincronizar Cuentas ---
    try:
        current_accounts = set(st.session_state.get('accounts_df', pd.DataFrame(columns=['Nombre']))['Nombre'].unique())
        current_goals = set(st.session_state.get('goals_df', pd.DataFrame(columns=['Nombre']))['Nombre'].unique())
        csv_cuentas = set(df['Cuenta'].unique())
        csv_destinos_cuentas = set(df[~df['Destino'].isin(current_goals)]['Destino'].unique())
        all_csv_accounts = csv_cuentas.union(csv_destinos_cuentas)

        new_accounts_df = pd.DataFrame()
        new_account_names = []

        for acc in all_csv_accounts:
            if acc not in current_accounts and pd.notna(acc) and acc != 'N/A':
                new_account = {'Nombre': acc, 'Tipo': 'Importada', 'Saldo Inicial': 0.0}
                new_accounts_df = pd.concat([new_accounts_df, pd.DataFrame([new_account])], ignore_index=True)
                new_account_names.append(acc)

        if not new_accounts_df.empty:
            st.session_state.accounts_df = pd.concat([st.session_state.accounts_df, new_accounts_df], ignore_index=True)
            save_data(supabase_client, ACCOUNTS_TABLE, st.session_state.accounts_df, user_id) # Usar nueva función
            st.toast(f"🏦 ¡Se añadieron {len(new_account_names)} nuevas cuentas!", icon="🏦")
            changes_made_global = True
    except Exception as e:
        st.warning(f"Error al sincronizar cuentas: {e}")

    # --- 3. Sincronizar Categorías ---
    try:
        current_categories_gasto = set(st.session_state.get('categories', {}).get('Gasto', []))
        current_categories_ingreso = set(st.session_state.get('categories', {}).get('Ingreso', []))
        csv_gastos = set(df[df['Tipo'] == 'Gasto']['Categoría'].unique())
        csv_ingresos = set(df[df['Tipo'] == 'Ingreso']['Categoría'].unique())

        new_gastos = [c for c in csv_gastos if c not in current_categories_gasto and pd.notna(c) and c != 'N/A']
        new_ingresos = [c for c in csv_ingresos if c not in current_categories_ingreso and pd.notna(c) and c != 'N/A']

        changes_made_cats = False
        if new_gastos:
            st.session_state.categories.setdefault('Gasto', []).extend(new_gastos)
            st.session_state.categories['Gasto'].sort()
            changes_made_cats = True
            st.toast(f"📉 ¡Se añadieron {len(new_gastos)} nuevas categorías de gasto!", icon="📉")

        if new_ingresos:
            st.session_state.categories.setdefault('Ingreso', []).extend(new_ingresos)
            st.session_state.categories['Ingreso'].sort()
            changes_made_cats = True
            st.toast(f"📈 ¡Se añadieron {len(new_ingresos)} nuevas categorías de ingreso!", icon="📈")

        if changes_made_cats:
            save_categories(supabase_client, st.session_state.categories, user_id) # Usar nueva función
            changes_made_global = True
    except Exception as e:
        st.warning(f"Error al sincronizar categorías: {e}")

    return changes_made_global
