# --- Archivo: ui_views.py ---
# Versión 5.2: Funcionalidad Final

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import time
from supabase import Client

# Importamos nuestra caja de lógica
import database as db

# --- 5. VISTAS DE PESTAÑA (STREAMLIT) ---

# --- 5.1 Pestaña: Registrar Transacción ---
def view_register(supabase_client: Client, user_id: str):
    st.header("📝 Registrar Nueva Transacción")
    st.caption("Añade nuevos movimientos a tu historial financiero.")

    if st.session_state.get('submitted_success', False):
        if 'is_recurring_checkbox' in st.session_state:
            st.session_state.is_recurring_checkbox = False
        if 'frequency_select_live' in st.session_state:
             del st.session_state.frequency_select_live
        st.session_state.submitted_success = False

    col_tipo, col_miembro = st.columns(2)
    with col_tipo:
        transaction_type = st.radio("Tipo de Movimiento",
                                    ('Gasto', 'Ingreso', 'Transferencia'),
                                    key='transaction_type', horizontal=True)
    with col_miembro:
        if not st.session_state.get('members'):
            st.warning("No hay miembros configurados. Añade uno en 'Configurar'.")
            selected_member = "N/A"
        else:
            selected_member = st.selectbox("Miembro", st.session_state.members, key="member_select_register")

    is_recurring = False
    if transaction_type in ['Ingreso', 'Gasto']:
        is_recurring = st.checkbox("🔁 ¿Es Recurrente (Fijo)?", key='is_recurring_checkbox', value=st.session_state.get('is_recurring_checkbox', False))

    with st.form("transaction_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            date_input = st.date_input("🗓️ Fecha", datetime.now().date())
            amount = st.number_input("💲 Monto", min_value=0.01, format="%.2f", step=1.0, key='amount_input')

        with col2:
            account_options = st.session_state.get('accounts_df', pd.DataFrame(columns=['Nombre']))['Nombre'].tolist()
            goal_options = st.session_state.get('goals_df', pd.DataFrame(columns=['Nombre']))['Nombre'].tolist()

            if not account_options:
                st.error("⛔ No hay cuentas configuradas. Añade una en 'Configurar' para poder registrar.")
                st.form_submit_button("Guardar Transacción", disabled=True)
                return

            frequency = 'Única/N/A' # Valor por defecto

            if transaction_type == 'Transferencia':
                account = st.selectbox("💳 Cuenta de Origen", account_options, key='account_origen')
                destination_options = [g for g in goal_options if g != 'N/A'] + account_options
                if not destination_options:
                     st.error("⛔ No hay cuentas o metas de destino configuradas.")
                     st.form_submit_button("Guardar Transacción", disabled=True)
                     return
                destination = st.selectbox("🎯 Destino (Cuenta o Meta)", destination_options, key='account_destino')
                category = 'N/A'
            else: # Ingreso o Gasto
                account = st.selectbox("🏦 Cuenta / Método", account_options, key='account_normal')
                category_options = st.session_state.get('categories', {}).get(transaction_type, ['Otros'])
                category = st.selectbox("🏷️ Categoría", category_options, key='category_input')
                destination = 'N/A'

                if is_recurring:
                    frequency = st.selectbox(
                        "🔄 Frecuencia",
                        list(db.FREQUENCY_MULTIPLIER.keys()),
                        index=list(db.FREQUENCY_MULTIPLIER.keys()).index(st.session_state.get('frequency_select_live','Mensual')),
                        key='frequency_select_live'
                    )

        description = st.text_area("🗒️ Descripción (Opcional)")

        submitted = st.form_submit_button("💾 Guardar Transacción")

        if submitted:
            if transaction_type == 'Transferencia' and account == destination:
                st.error("❌ Error: La Cuenta de Origen no puede ser igual al Destino.")
            else:
                current_selected_member = st.session_state.get("member_select_register", selected_member)
                current_frequency = st.session_state.get("frequency_select_live", frequency) if is_recurring else 'Única/N/A'

                new_entry = pd.DataFrame([{
                    'Fecha': pd.to_datetime(date_input),
                    'Tipo': transaction_type,
                    'Categoría': category,
                    'Cuenta': account,
                    'Monto': float(amount),
                    'Descripción': description,
                    'Miembro': current_selected_member,
                    'Destino': destination,
                    'Recurrente': is_recurring,
                    'Frecuencia': current_frequency
                }])

                st.session_state.transactions_df = pd.concat(
                    [st.session_state.get('transactions_df', db.DEFAULT_TRANSACTIONS.copy()), new_entry],
                    ignore_index=True
                ).sort_values(by='Fecha', ascending=False)

                # Guardar en Supabase
                db.save_data(supabase_client, db.TRANSACTIONS_TABLE, st.session_state.transactions_df, user_id)

                st.session_state.goals_df = db.update_goal_progress(
                    st.session_state.transactions_df.copy(),
                    st.session_state.get('goals_df', db.DEFAULT_GOALS.copy()).copy()
                )
                db.save_data(supabase_client, db.GOALS_TABLE, st.session_state.goals_df, user_id)

                st.success(f"✅ ¡{transaction_type} registrado con éxito!")
                st.session_state.submitted_success = True
                st.rerun()

# --- 5.2 Pestaña: Dashboard ---
def view_dash(df_filtered):
    st.header("📊 Dashboard: Flujo y Presupuesto")

    # Modificado: Saludo genérico
    st.subheader("¡Bienvenido!")
    st.caption("Aquí tienes un resumen de la salud financiera de tu hogar.")

    df_transactions = st.session_state.get('transactions_df', pd.DataFrame()).copy()
    df_accounts = st.session_state.get('accounts_df', pd.DataFrame()).copy()

    if df_transactions.empty and df_accounts.empty:
        st.info("ℹ️ Aún no hay transacciones ni cuentas para analizar.")
        st.info("Empieza por añadir una cuenta en 'Configurar' o registrar una transacción.")
        return

    st.subheader("🏦 Resumen de Saldos", divider="rainbow")
    try:
        df_balances = db.calculate_account_balances(df_transactions, df_accounts)
        if not df_balances.empty:
            account_cols = st.columns(min(len(df_balances), 4))
            col_idx = 0
            for i, row in df_balances.iterrows():
                delta_color = "normal"
                change = row['Saldo Actual'] - row['Saldo Inicial']
                if change > 0: delta_color = "normal"
                elif change < 0: delta_color = "inverse"
                with account_cols[col_idx % len(account_cols)]:
                    st.metric(
                        label=f"{row['Nombre']} ({row['Tipo']})",
                        value=f"${row['Saldo Actual']:,.2f}",
                        delta=f"{change:,.2f} vs. Inicial",
                        delta_color=delta_color
                    )
                col_idx += 1
        else:
            st.info("ℹ️ No hay cuentas configuradas. Añade una en 'Configurar' para ver los saldos.")
    except Exception as e:
        st.error(f"❌ Error al calcular saldos de cuentas: {e}")
        st.markdown("---")

    if df_transactions.empty:
        st.info("ℹ️ Aún no hay transacciones registradas para mostrar más análisis.")
        return

    st.subheader("📈 Métricas Clave (KPIs)", divider="rainbow")
    ingresos, gastos, balance_total = db.calculate_balance(df_transactions)
    income_fixed, expense_fixed, surplus_fixed = db.calculate_fixed_surplus(df_transactions)
    config = st.session_state.get('budget_config', {'period_start': datetime.now().date(), 'period_end': datetime.now().date(), 'budget_amount': 0.0})

    daily_budget, days_left, presupuesto_restante = db.calculate_daily_budget(
        config['period_start'], config['period_end'], config['budget_amount'], df_transactions
    )

    balance_icon = "💹" if balance_total >= 0 else "📉"
    surplus_icon = "🚀" if surplus_fixed > 0 else "⚠️"

    col_b1, col_b2, col_b3, col_b4 = st.columns(4)
    col_b1.metric("Balance Neto Total", f"{balance_icon} ${balance_total:,.2f}", help=f"Ingresos: ${ingresos:,.2f} | Gastos: ${gastos:,.2f}")
    col_b2.metric("Presup. Restante (Global)", f"💰 ${presupuesto_restante:,.2f}", help=f"Presupuesto Periodo: ${config.get('budget_amount', 0):,.2f} (Hasta {config.get('period_end', datetime.now().date()).strftime('%d-%b-%Y')})")
    col_b3.metric("Superávit Fijo Mensual", f"{surplus_icon} ${surplus_fixed:,.2f}", help=f"Ingreso Fijo Proy.: ${income_fixed:,.2f} | Gasto Fijo Proy.: ${expense_fixed:,.2f}")
    col_b4.metric("Presup. Diario Restante", f"⏳ ${daily_budget:,.2f}", help=f"Días restantes en período: {days_left}")

    st.subheader("🏷️ Control Presupuesto por Categoría", divider="rainbow")
    if st.session_state.get('category_budgets'):
        config = st.session_state.get('budget_config')
        start_date = pd.to_datetime(config['period_start'])
        end_date = pd.to_datetime(config['period_end']) + timedelta(days=1)
        df_period_spending = df_transactions[
            (df_transactions['Tipo'] == 'Gasto') &
            (df_transactions['Fecha'] >= start_date) &
            (df_transactions['Fecha'] < end_date)
        ].copy()
        spending_by_cat = df_period_spending.groupby('Categoría')['Monto'].sum().reset_index()
        spending_by_cat.columns = ['Categoría', 'Gastado']
        budget_data = []
        for category, budget in st.session_state.category_budgets.items():
            if budget > 0.0:
                spent = spending_by_cat[spending_by_cat['Categoría'] == category]['Gastado'].iloc[0] if not spending_by_cat[spending_by_cat['Categoría'] == category].empty else 0.0
                budget_data.append({'Categoría': category, 'Presupuesto': budget, 'Gastado': spent, 'Porcentaje': (spent / budget) * 100 if budget > 0 else 0, 'Excedido': spent > budget})
        df_budget_chart = pd.DataFrame(budget_data)
        if not df_budget_chart.empty:
            df_budget_chart = df_budget_chart.sort_values(by='Gastado', ascending=False)
            color_map = {True: 'crimson', False: 'mediumseagreen'}
            fig_budget = px.bar(df_budget_chart, y='Categoría', x='Gastado', orientation='h',
                                title=f"Gasto vs. Presupuesto ({config.get('period_start', datetime.now().date()).strftime('%d %b')} - {config.get('period_end', datetime.now().date()).strftime('%d %b')})",
                                color='Excedido', color_discrete_map=color_map, text='Gastado',
                                template='plotly_white')
            for i, row in df_budget_chart.iterrows():
                fig_budget.add_shape(type='line', y0=i - 0.4, y1=i + 0.4, x0=row['Presupuesto'], x1=row['Presupuesto'],
                                     line=dict(color='royalblue', width=2, dash='dash'))
                fig_budget.add_annotation(x=row['Presupuesto'], y=i,
                                          text=f" P: ${row['Presupuesto']:,.0f}", showarrow=False,
                                          xanchor="left", yshift=10, font=dict(color='royalblue', size=10))
            fig_budget.update_layout(xaxis_title="Monto Gastado ($)", yaxis_title=None, showlegend=False,
                                     yaxis={'categoryorder':'total descending'})
            fig_budget.update_traces(texttemplate='$%{text:,.2f}', textposition='outside')
            st.plotly_chart(fig_budget, use_container_width=True)
        else: st.info("ℹ️ No hay presupuestos activos (> $0.0) asignados o transacciones en el período actual.")
    else: st.info("ℹ️ No hay presupuestos asignados por categoría.")

    st.subheader("🔍 Análisis Detallado (Según Filtros)", divider="rainbow")
    if df_filtered.empty:
        st.info("ℹ️ No hay transacciones que cumplan con los filtros de la barra lateral.")
        return

    # (El resto de los gráficos no necesitan cambios)
    col_top5, col_pattern = st.columns([1, 1])
    with col_top5:
        st.subheader("🏆 Top 5 Gastos", divider="grey")
        df_gastos_filtrados = df_filtered[df_filtered['Tipo'] == 'Gasto'].copy()
        if not df_gastos_filtrados.empty:
            df_top5 = df_gastos_filtrados.groupby('Categoría')['Monto'].sum().nlargest(5).reset_index()
            fig_top5 = px.bar(df_top5, x='Monto', y='Categoría', orientation='h',
                              color='Monto', color_continuous_scale=px.colors.sequential.OrRd,
                              labels={'Monto': 'Monto ($)', 'Categoría': ''},
                              template='plotly_white')
            fig_top5.update_layout(yaxis={'categoryorder':'total ascending'}, xaxis_title=None, yaxis_title=None)
            st.plotly_chart(fig_top5, use_container_width=True)
        else: st.info("ℹ️ No hay gastos para mostrar con los filtros aplicados.")
    with col_pattern:
        st.subheader("🗓️ Patrón Gasto Diario", divider="grey")
        df_day_pattern = df_transactions[df_transactions['Tipo'] == 'Gasto'].copy()
        if not df_day_pattern.empty:
            df_day_pattern['Dia'] = df_day_pattern['Fecha'].dt.day_name().map(db.DAY_NAMES_MAP)
            df_gasto_promedio = df_day_pattern.groupby('Dia')['Monto'].mean().reset_index()
            df_gasto_promedio.columns = ['Día de la Semana', 'Gasto Promedio ($)']
            day_order = list(db.DAY_NAMES_MAP.values())
            df_gasto_promedio['Día de la Semana'] = pd.Categorical(df_gasto_promedio['Día de la Semana'], categories=day_order, ordered=True)
            df_gasto_promedio = df_gasto_promedio.sort_values('Día de la Semana')
            fig_day_pattern = px.bar(df_gasto_promedio, x='Día de la Semana', y='Gasto Promedio ($)',
                                     color_discrete_sequence=['#4CAF50'],
                                     labels={'Gasto Promedio ($)': 'Gasto Promedio ($)'},
                                     template='plotly_white')
            fig_day_pattern.update_layout(xaxis_title=None)
            st.plotly_chart(fig_day_pattern, use_container_width=True)
        else: st.info("ℹ️ No hay suficientes gastos para analizar patrones.")
    st.subheader("📉 Tendencia Flujo de Caja", divider="grey")
    df_flujo = df_filtered[df_filtered['Tipo'].isin(['Ingreso', 'Gasto'])].copy()
    if not df_flujo.empty:
        df_flujo['Fecha_Dia'] = df_flujo['Fecha'].dt.normalize()
        df_pivot = df_flujo.pivot_table(index='Fecha_Dia', columns='Tipo', values='Monto', aggfunc='sum').fillna(0)
        if 'Ingreso' not in df_pivot.columns: df_pivot['Ingreso'] = 0.0
        if 'Gasto' not in df_pivot.columns: df_pivot['Gasto'] = 0.0
        df_pivot = df_pivot.reset_index()
        df_pivot['Balance Neto'] = df_pivot['Ingreso'] - df_pivot['Gasto']
        df_pivot['Balance Acumulado'] = df_pivot['Balance Neto'].cumsum()
        fig_line = go.Figure()
        fig_line.add_trace(go.Scatter(x=df_pivot['Fecha_Dia'], y=df_pivot['Ingreso'], mode='lines+markers', name='Ingreso', line=dict(color='green')))
        fig_line.add_trace(go.Scatter(x=df_pivot['Fecha_Dia'], y=df_pivot['Gasto'], mode='lines+markers', name='Gasto', line=dict(color='red')))
        fig_line.add_trace(go.Scatter(x=df_pivot['Fecha_Dia'], y=df_pivot['Balance Acumulado'], mode='lines+markers', name='Balance Acumulado', line=dict(color='blue', dash='dot')))
        fig_line.update_layout(title='Flujo Diario y Balance Acumulado', xaxis_title='Fecha', yaxis_title='Monto ($)', hovermode="x unified", template='plotly_white')
        st.plotly_chart(fig_line, use_container_width=True)
    else: st.info("ℹ️ No hay transacciones de Ingreso o Gasto en el rango para el análisis de tendencia.")
    col_pie_charts, col_bar_chart = st.columns([1, 1])
    with col_pie_charts:
        st.subheader("🍰 Distribución Gastos", divider="grey")
        df_gastos = df_filtered[df_filtered['Tipo'] == 'Gasto']
        if not df_gastos.empty:
            df_pie_data = df_gastos.groupby('Categoría')['Monto'].sum().reset_index()
            fig_pie = px.pie(df_pie_data, values='Monto', names='Categoría', template='plotly_white', hole=0.3)
            fig_pie.update_traces(textposition='outside', textinfo='percent+label')
            st.plotly_chart(fig_pie, use_container_width=True)
        else: st.info("ℹ️ No hay gastos para mostrar en este rango.")
    with col_bar_chart:
        st.subheader("💰 Distribución Ingresos", divider="grey")
        df_ingresos = df_filtered[df_filtered['Tipo'] == 'Ingreso']
        if not df_ingresos.empty:
            df_pie_data_ingreso = df_ingresos.groupby('Categoría')['Monto'].sum().reset_index()
            fig_pie_ingreso = px.pie(df_pie_data_ingreso, values='Monto', names='Categoría', template='plotly_white', hole=0.3)
            fig_pie_ingreso.update_traces(textposition='outside', textinfo='percent+label')
            st.plotly_chart(fig_pie_ingreso, use_container_width=True)
        else: st.info("ℹ️ No hay ingresos para mostrar en este rango.")


# --- Callbacks para la Pestaña de Configuración ---
# (Adaptados para pasar supabase_client y user_id)
def callback_update_budget(supabase_client: Client, user_id: str):
    start_date = st.session_state.budget_start_date
    end_date = st.session_state.budget_end_date
    budget_amount = st.session_state.budget_amount_input
    if start_date >= end_date:
        st.error("❌ La fecha de inicio debe ser anterior a la fecha de fin.")
    else:
        new_config_dict = {
            'period_start': start_date.isoformat(),
            'period_end': end_date.isoformat(),
            'budget_amount': float(budget_amount)
        }
        db.save_config_key(supabase_client, user_id, db.BUDGET_KEY, new_config_dict)
        st.session_state.budget_config = db.load_budget_config(supabase_client, user_id)
        st.success("✅ Presupuesto global guardado con éxito.")
        st.rerun()

def callback_add_account(supabase_client: Client, user_id: str):
    acc_name = st.session_state.acc_name_input
    acc_type = st.session_state.acc_type_input
    initial_balance = st.session_state.acc_balance_input
    if not acc_name:
        st.error("❌ El nombre de la cuenta no puede estar vacío.")
        return

    new_account = pd.DataFrame([{'Nombre': acc_name, 'Tipo': acc_type, 'Saldo Inicial': float(initial_balance)}])
    st.session_state.accounts_df = pd.concat([st.session_state.accounts_df, new_account], ignore_index=True)
    db.save_data(supabase_client, db.ACCOUNTS_TABLE, st.session_state.accounts_df, user_id)
    st.success(f"✅ Cuenta '{acc_name}' añadida.")
    st.rerun()

def callback_delete_account(supabase_client: Client, user_id: str):
    acc_to_delete = st.session_state.del_acc_select
    # Lógica de comprobación
    can_delete = True
    if not st.session_state.transactions_df.empty:
        if acc_to_delete in st.session_state.transactions_df['Cuenta'].tolist() or \
           acc_to_delete in st.session_state.transactions_df['Destino'].tolist():
            can_delete = False
    if not can_delete:
        st.error("❌ No se puede eliminar: La cuenta tiene transacciones asociadas.")
        return

    st.session_state.accounts_df = st.session_state.accounts_df[st.session_state.accounts_df['Nombre'] != acc_to_delete].reset_index(drop=True)
    db.save_data(supabase_client, db.ACCOUNTS_TABLE, st.session_state.accounts_df, user_id)
    st.success(f"✅ Cuenta '{acc_to_delete}' eliminada.")
    st.rerun()

def callback_add_category(supabase_client: Client, user_id: str):
    cat_type = st.session_state.cat_type_input
    cat_name = st.session_state.cat_name_input
    if not cat_name:
        st.error("❌ El nombre de la categoría no puede estar vacío.")
        return
    if cat_name in st.session_state.categories.get(cat_type, []):
        st.error(f"❌ La categoría '{cat_name}' ya existe en {cat_type}.")
        return

    st.session_state.categories.setdefault(cat_type, []).append(cat_name)
    st.session_state.categories[cat_type].sort()
    db.save_categories(supabase_client, st.session_state.categories, user_id)
    st.success(f"✅ Categoría '{cat_name}' añadida a {cat_type}.")
    st.rerun()

def callback_delete_category(supabase_client: Client, user_id: str, category_type: str):
    if category_type == 'Gasto':
        cat_to_delete = st.session_state.del_cat_gasto
    else: # Ingreso
        cat_to_delete = st.session_state.del_cat_ingreso

    # Lógica de comprobación
    can_delete = True
    if not st.session_state.transactions_df.empty:
        if cat_to_delete in st.session_state.transactions_df['Categoría'].tolist():
            can_delete = False
    if not can_delete:
        st.error(f"❌ No se puede eliminar: La categoría '{cat_to_delete}' tiene transacciones asociadas.")
        return

    try:
        st.session_state.categories[category_type].remove(cat_to_delete)
        if category_type == 'Gasto' and cat_to_delete in st.session_state.category_budgets:
            del st.session_state.category_budgets[cat_to_delete]
            db.save_config_key(supabase_client, user_id, db.CATEGORY_BUDGET_KEY, st.session_state.category_budgets)

        db.save_categories(supabase_client, st.session_state.categories, user_id)
        st.success(f"✅ Categoría '{cat_to_delete}' eliminada.")
        st.rerun()
    except ValueError:
        st.error("❌ Error: Categoría no encontrada.")

def callback_add_member(supabase_client: Client, user_id: str):
    new_member = st.session_state.new_member_name
    if not new_member:
        st.error("❌ El nombre no puede estar vacío.")
        return
    if new_member in st.session_state.members:
        st.error("❌ Miembro ya existe.")
        return

    st.session_state.members.append(new_member)
    st.session_state.members.sort()
    db.save_members(supabase_client, st.session_state.members, user_id)
    st.success(f"✅ Miembro '{new_member}' añadido.")
    st.rerun()

def callback_delete_member(supabase_client: Client, user_id: str):
    member_to_delete = st.session_state.del_member_select
    # Lógica de comprobación
    can_delete = True
    if not st.session_state.transactions_df.empty:
        if member_to_delete in st.session_state.transactions_df['Miembro'].tolist():
             can_delete = False
    if not can_delete:
        st.error("❌ No se puede eliminar: El miembro tiene transacciones asociadas.")
        return

    try:
        st.session_state.members.remove(member_to_delete)
        db.save_members(supabase_client, st.session_state.members, user_id)
        st.success(f"✅ Miembro '{member_to_delete}' eliminado.")
        st.rerun()
    except ValueError:
        st.error("❌ Error: Miembro no encontrado.")

def callback_add_goal(supabase_client: Client, user_id: str):
    goal_name = st.session_state.goal_name_input
    target_amount = st.session_state.goal_amount_input
    target_date = st.session_state.goal_date_input
    if not goal_name:
        st.error("❌ El nombre de la meta no puede estar vacío.")
        return

    new_goal = pd.DataFrame([{'Nombre': goal_name, 'Monto Objetivo': float(target_amount), 'Monto Aportado': 0.0, 'Fecha Objetivo': target_date}])
    st.session_state.goals_df = pd.concat([st.session_state.goals_df, new_goal], ignore_index=True)
    st.session_state.goals_df = db.update_goal_progress(st.session_state.transactions_df, st.session_state.goals_df)
    db.save_data(supabase_client, db.GOALS_TABLE, st.session_state.goals_df, user_id)
    st.success(f"✅ Meta '{goal_name}' añadida.")
    st.rerun()

def callback_delete_goal(supabase_client: Client, user_id: str):
    goal_to_delete = st.session_state.del_goal_select
    # Lógica de comprobación
    can_delete = True
    if not st.session_state.transactions_df.empty:
        if goal_to_delete in st.session_state.transactions_df['Destino'].tolist():
             can_delete = False
    if not can_delete:
        st.error("❌ No se puede eliminar: La meta tiene aportaciones asociadas.")
        return

    st.session_state.goals_df = st.session_state.goals_df[st.session_state.goals_df['Nombre'] != goal_to_delete].reset_index(drop=True)
    db.save_data(supabase_client, db.GOALS_TABLE, st.session_state.goals_df, user_id)
    st.success(f"✅ Meta '{goal_to_delete}' eliminada.")
    st.rerun()


# --- 5.3 Pestaña: Configurar ---
def view_config(supabase_client: Client, user_id: str):
    st.header("⚙️ Configuración del Hogar")

    tab_global, tab_cat, tab_cuentas, tab_cats, tab_miembros, tab_metas = st.tabs([
        "💰 Presupuesto Global", "🏷️ Presupuesto Cat.", "🏦 Cuentas",
        "📑 Categorías", "👥 Miembros", "🎯 Metas Ahorro"
    ])

    with tab_global:
        st.subheader("Definir Periodo y Monto Global", divider="blue")
        config = st.session_state.get('budget_config')
        with st.form("budget_form"):
            col_b1, col_b2, col_b3 = st.columns(3)
            with col_b1: st.date_input("Fecha de Inicio", config.get('period_start', datetime.now().date()), key="budget_start_date")
            with col_b2: st.date_input("Fecha de Fin", config.get('period_end', datetime.now().date() + timedelta(days=15)), key="budget_end_date")
            with col_b3: st.number_input("Monto Total ($)", min_value=0.0, format="%.2f",
                                        value=config.get('budget_amount', 1000.0), key="budget_amount_input")
            st.form_submit_button("💾 Guardar Presupuesto Global", on_click=callback_update_budget, args=(supabase_client, user_id))

    with tab_cat:
        st.subheader("Asignar Presupuesto por Categoría de Gasto", divider="blue")
        st.caption("Define límites específicos para cada categoría dentro del período global.")
        expense_categories = st.session_state.get('categories', {}).get('Gasto', [])
        if not expense_categories:
            st.warning("⚠️ No hay categorías de Gasto configuradas.")
        else:
            current_budgets = st.session_state.get('category_budgets', {})
            data_for_editor = [{'Categoría': cat, 'Presupuesto': current_budgets.get(cat, 0.0)} for cat in expense_categories]
            df_budgets = pd.DataFrame(data_for_editor)
            edited_df = st.data_editor(
                df_budgets,
                column_config={"Categoría": st.column_config.TextColumn(disabled=True), "Presupuesto": st.column_config.NumberColumn(min_value=0.0, format="%.2f")},
                hide_index=True, num_rows="dynamic", key="category_budget_editor", use_container_width=True
            )
            if st.button("💾 Guardar Presupuestos por Categoría", type="primary"):
                new_budgets = {row['Categoría']: float(row['Presupuesto']) for _, row in edited_df.iterrows() if float(row['Presupuesto']) >= 0}
                db.save_config_key(supabase_client, user_id, db.CATEGORY_BUDGET_KEY, new_budgets)
                st.session_state.category_budgets = new_budgets
                st.success("✅ Presupuestos por categoría actualizados con éxito.")
                st.rerun()

    with tab_cuentas:
        st.subheader("Gestionar Cuentas", divider="blue")
        with st.expander("➕ Añadir Nueva Cuenta"):
            with st.form("add_account_form", clear_on_submit=True):
                col_a1, col_a2, col_a3 = st.columns(3)
                with col_a1: st.text_input("Nombre de la Cuenta", key="acc_name_input")
                with col_a2: st.selectbox("Tipo", ['Efectivo', 'Banco', 'Crédito', 'Inversión', 'Otro'], key="acc_type_input")
                with col_a3: st.number_input("Saldo Inicial ($)", value=0.0, format="%.2f", key="acc_balance_input")
                st.form_submit_button("💾 Añadir Cuenta", on_click=callback_add_account, args=(supabase_client, user_id))
        st.subheader("Cuentas Actuales", divider="grey")
        accounts_df_display = st.session_state.get('accounts_df', pd.DataFrame())
        st.dataframe(accounts_df_display, hide_index=True, use_container_width=True)
        if not accounts_df_display.empty:
            st.selectbox("Seleccionar Cuenta para Eliminar:", accounts_df_display['Nombre'].tolist(), key="del_acc_select", label_visibility="collapsed")
            st.button("🗑️ Eliminar Cuenta Seleccionada", key="delete_acc_btn", type="secondary", on_click=callback_delete_account, args=(supabase_client, user_id))

    with tab_cats:
        st.subheader("Gestionar Categorías", divider="blue")
        with st.expander("➕ Añadir Nueva Categoría"):
            with st.form("add_category_form", clear_on_submit=True):
                col_c1, col_c2 = st.columns(2)
                with col_c1: st.radio("Tipo de Categoría", ['Gasto', 'Ingreso'], key="cat_type_input")
                with col_c2: st.text_input("Nombre de la nueva Categoría", key="cat_name_input")
                st.form_submit_button("💾 Añadir Categoría", on_click=callback_add_category, args=(supabase_client, user_id))
        st.subheader("Categorías Actuales", divider="grey")
        col_view_cat, col_del_cat = st.columns(2)
        categories_dict = st.session_state.get('categories', {})
        with col_view_cat:
            st.info("📉 Categorías de Gasto")
            gasto_cats = categories_dict.get('Gasto', [])
            st.write(gasto_cats)
            if gasto_cats:
                st.selectbox("Eliminar Gasto:", gasto_cats, key="del_cat_gasto", label_visibility="collapsed")
                st.button("🗑️ Eliminar Gasto Seleccionado", key="delete_cat_gasto_btn", type="secondary",
                          on_click=callback_delete_category, args=(supabase_client, user_id, 'Gasto'))
        with col_del_cat:
            st.info("📈 Categorías de Ingreso")
            ingreso_cats = categories_dict.get('Ingreso', [])
            st.write(ingreso_cats)
            if ingreso_cats:
                st.selectbox("Eliminar Ingreso:", ingreso_cats, key="del_cat_ingreso", label_visibility="collapsed")
                st.button("🗑️ Eliminar Ingreso Seleccionado", key="delete_cat_ingreso_btn", type="secondary",
                          on_click=callback_delete_category, args=(supabase_client, user_id, 'Ingreso'))

    with tab_miembros:
        st.subheader("Gestionar Miembros del Hogar", divider="blue")
        with st.expander("➕ Añadir Nuevo Miembro"):
            with st.form("add_member_form", clear_on_submit=True):
                st.text_input("Nombre del Nuevo Miembro", key="new_member_name")
                st.form_submit_button("💾 Añadir Miembro", on_click=callback_add_member, args=(supabase_client, user_id))
        st.subheader("Miembros Actuales", divider="grey")
        members_list = st.session_state.get('members', [])
        st.write(members_list)
        if members_list:
            st.selectbox("Seleccionar Miembro para Eliminar:", members_list, key="del_member_select", label_visibility="collapsed")
            st.button("🗑️ Eliminar Miembro Seleccionado", key="delete_member_btn", type="secondary", on_click=callback_delete_member, args=(supabase_client, user_id))

    with tab_metas:
        st.subheader("Gestionar Metas de Ahorro", divider="blue")
        with st.expander("➕ Añadir Nueva Meta de Ahorro"):
            with st.form("add_goal_form", clear_on_submit=True):
                col_g1, col_g2, col_g3 = st.columns(3)
                with col_g1: st.text_input("Nombre de la Meta", key="goal_name_input")
                with col_g2: st.number_input("Monto Objetivo ($)", min_value=1.0, value=1000.0, format="%.2f", key="goal_amount_input")
                with col_g3: st.date_input("Fecha Límite", datetime.now().date() + timedelta(days=365), key="goal_date_input")
                st.form_submit_button("💾 Añadir Meta", on_click=callback_add_goal, args=(supabase_client, user_id))
        st.subheader("📊 Progreso de Metas", divider="grey")
        goals_df_display = st.session_state.get('goals_df', pd.DataFrame())
        if not goals_df_display.empty and 'Monto Objetivo' in goals_df_display.columns:
            df_goals = goals_df_display.copy()
            df_goals['Monto Objetivo'] = pd.to_numeric(df_goals['Monto Objetivo'], errors='coerce').fillna(1.0)
            df_goals['Monto Aportado'] = pd.to_numeric(df_goals['Monto Aportado'], errors='coerce').fillna(0.0)
            df_goals['Fecha Objetivo'] = pd.to_datetime(df_goals['Fecha Objetivo'], errors='coerce').dt.date
            df_goals['Progreso (%)'] = ((df_goals['Monto Aportado'] / df_goals['Monto Objetivo'].replace(0, np.nan)) * 100).fillna(0)
            df_goals['Días Restantes'] = (df_goals['Fecha Objetivo'] - datetime.now().date()).apply(lambda x: max(0, x.days if pd.notna(x) else 0))
            # ... (código de los medidores de plotly) ...
            num_goals = len(df_goals)
            cols_per_row = 3
            num_rows = (num_goals + cols_per_row - 1) // cols_per_row
            goal_idx = 0
            for _ in range(num_rows):
                cols = st.columns(cols_per_row)
                for j in range(cols_per_row):
                    if goal_idx < num_goals:
                        row = df_goals.iloc[goal_idx]
                        progress = min(100, row['Progreso (%)'])
                        target_amount_val = row['Monto Objetivo'] if row['Monto Objetivo'] > 0 else 1
                        fig_gauge = go.Figure(go.Indicator(
                            mode = "gauge+number+delta", value = row['Monto Aportado'],
                            number = {'prefix': "$", 'valueformat': ',.2f'},
                            delta = {'reference': target_amount_val, 'relative': False, 'valueformat': ',.2f', 'suffix': ' Objetivo'},
                            domain = {'x': [0, 1], 'y': [0, 1]},
                            title = {'text': f"<span style='font-size:1.1em'>{row['Nombre']}</span><br><span style='font-size:0.8em'>Días restantes: {row['Días Restantes']}</span>"},
                            gauge = {'axis': {'range': [0, target_amount_val]}, 'bar': {'color': "darkorange"},
                                     'steps': [{'range': [0, target_amount_val * 0.5], 'color': 'lightgray'}, {'range': [target_amount_val * 0.5, target_amount_val], 'color': 'darkgray'}],
                                    'threshold' : {'line': {'color': "green", 'width': 4}, 'thickness': 0.75, 'value': target_amount_val}}
                         ))
                        fig_gauge.update_layout(height=250, margin=dict(l=20, r=20, t=60, b=20))
                        cols[j].plotly_chart(fig_gauge, use_container_width=True, config={'displayModeBar': False})
                        goal_idx += 1
                    else:
                        cols[j].empty()

            with st.expander("✏️ Editar Detalles / Eliminar Metas"):
                st.subheader("Detalle de Metas", divider="grey")
                edited_goals_df = st.data_editor(
                    df_goals.drop(columns=['Progreso (%)', 'Días Restantes']),
                    column_config={
                        "Nombre": st.column_config.TextColumn("Meta", width="large"),
                        "Monto Objetivo": st.column_config.NumberColumn("Objetivo ($)", format="%.2f", min_value=0.01),
                        "Monto Aportado": st.column_config.NumberColumn("Aportado ($) - (Se recalcula)", format="%.2f", disabled=True),
                        "Fecha Objetivo": st.column_config.DateColumn("Fecha Límite")
                    },
                    hide_index=True, use_container_width=True, num_rows="fixed", key="goals_editor"
                )
                if st.button("💾 Guardar Cambios en Metas", key="save_edited_goals"):
                    df_to_save = edited_goals_df[['Nombre', 'Monto Objetivo', 'Fecha Objetivo']].copy()
                    df_to_save = pd.merge(df_to_save, st.session_state.goals_df[['Nombre', 'Monto Aportado']], on='Nombre', how='left').fillna({'Monto Aportado': 0.0})
                    df_to_save['Monto Objetivo'] = pd.to_numeric(df_to_save['Monto Objetivo'], errors='coerce').fillna(0.0)
                    df_to_save['Fecha Objetivo'] = pd.to_datetime(df_to_save['Fecha Objetivo'], errors='coerce').dt.date
                    st.session_state.goals_df = df_to_save
                    db.save_data(supabase_client, db.GOALS_TABLE, st.session_state.goals_df, user_id)
                    st.success("✅ Cambios en metas guardados.")
                    st.rerun()
                st.markdown("---")
                st.selectbox("Seleccionar Meta para Eliminar:", df_goals['Nombre'].tolist(), key="del_goal_select", label_visibility="collapsed")
                st.button("🗑️ Eliminar Meta Seleccionada", key="delete_goal_btn", type="secondary", on_click=callback_delete_goal, args=(supabase_client, user_id))
        else: st.info("ℹ️ Aún no hay metas de ahorro configuradas.")


# --- 5.4 Pestaña: Historial Completo ---
def view_history(supabase_client: Client, user_id: str):
    st.header("📋 Historial Completo y Gestión")
    st.caption("Marca 'Eliminar?' para borrar. Edita directamente en la tabla y guarda los cambios.")

    with st.expander("📥/📤 Importar o Exportar Historial (CSV)"):
        st.subheader("📥 Descargar Historial (CSV)")
        df_to_download = st.session_state.get('transactions_df', pd.DataFrame())
        if not df_to_download.empty:
            df_csv_export = df_to_download.copy()
            if 'Fecha' in df_csv_export.columns:
                 df_csv_export['Fecha'] = pd.to_datetime(df_csv_export['Fecha']).dt.strftime('%Y-%m-%dT%H:%M:%S')
            csv_data = df_csv_export.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="📥 Descargar Historial Actual (CSV)", data=csv_data,
                file_name=f"guardian_domestico_historial_{datetime.now().strftime('%Y%m%d')}.csv",
                mime='text/csv', use_container_width=True
            )
        else:
            st.info("ℹ️ No hay historial para descargar.")

        st.markdown("---")
        st.subheader("📤 Importar desde CSV")
        st.warning("⚠️ **Importante:** El CSV debe tener las columnas: `Fecha`, `Tipo`, `Categoría`, `Cuenta`, `Monto`. \nOpcionales: `Descripción`, `Miembro`, `Destino`, `Recurrente`, `Frecuencia`.", icon="💡")
        uploaded_file = st.file_uploader("Selecciona un archivo CSV", type=['csv'], key="csv_uploader")
        import_mode = st.radio(
            "Modo de Importación:", ('Añadir al historial existente', 'Reemplazar historial completo'),
            key="csv_import_mode", horizontal=True
        )

        if st.button("🚀 Procesar Archivo CSV", key="process_csv_btn", type="primary"):
            if uploaded_file is not None:
                try:
                    df_new = pd.read_csv(uploaded_file)
                    df_processed = df_new.copy()
                    # (Toda la lógica de validación de CSV no cambia...)
                    required_cols_types = {
                        'Fecha': 'datetime64[ns]', 'Tipo': 'object',
                        'Categoría': 'object', 'Cuenta': 'object', 'Monto': 'float64'
                    }
                    optional_cols_defaults = {
                        'Descripción': '', 'Miembro': 'N/A', 'Destino': 'N/A',
                        'Recurrente': False, 'Frecuencia': 'Única/N/A'
                    }
                    df_processed.columns = [col.strip() for col in df_processed.columns]
                    missing_critical = [col for col in required_cols_types.keys() if col not in df_processed.columns]
                    if missing_critical:
                        st.error(f"❌ Error: El CSV no contiene las columnas críticas requeridas: {', '.join(missing_critical)}")
                        return
                    df_processed['Fecha'] = pd.to_datetime(df_processed['Fecha'], errors='coerce')
                    df_processed['Monto'] = pd.to_numeric(df_processed['Monto'], errors='coerce')
                    for col, default_val in optional_cols_defaults.items():
                        if col not in df_processed.columns: df_processed[col] = default_val
                        else:
                            if isinstance(default_val, bool): df_processed[col] = df_processed[col].fillna(default_val).astype(bool)
                            else: df_processed[col] = df_processed[col].fillna(default_val)
                    all_expected_cols = list(db.DEFAULT_TRANSACTIONS.columns)
                    df_processed = df_processed.reindex(columns=all_expected_cols)
                    initial_rows = len(df_processed)
                    df_processed = df_processed.dropna(subset=['Fecha', 'Monto', 'Tipo'])
                    rows_dropped = initial_rows - len(df_processed)
                    if df_processed.empty:
                        st.error("❌ No se encontraron datos válidos (Fecha, Monto, Tipo) en el CSV.")
                        return

                    st.info(f"Archivo leído. {len(df_processed)} filas válidas encontradas. {rows_dropped} filas descartadas.")
                    if import_mode == 'Reemplazar historial completo':
                        df_final = df_processed
                        st.success(f"✅ Historial reemplazado con {len(df_final)} nuevas transacciones.")
                    else:
                        df_current = st.session_state.get('transactions_df', db.DEFAULT_TRANSACTIONS.copy())
                        df_final = pd.concat([df_current, df_processed], ignore_index=True)
                        st.success(f"✅ Se añadieron {len(df_processed)} transacciones. Total: {len(df_final)}.")

                    st.info("Sincronizando categorías, miembros y cuentas del CSV...")
                    changes = db.sync_metadata_from_df(supabase_client, user_id, df_processed) # Adaptado V5.0
                    if not changes:
                        st.toast("¡Todo estaba al día! No se añadieron nuevos metadatos.")

                    st.session_state.transactions_df = df_final.sort_values(by='Fecha', ascending=False).reset_index(drop=True)
                    db.save_data(supabase_client, db.TRANSACTIONS_TABLE, st.session_state.transactions_df, user_id) # Adaptado V5.0
                    st.session_state.goals_df = db.update_goal_progress(
                        st.session_state.transactions_df.copy(),
                        st.session_state.get('goals_df', db.DEFAULT_GOALS.copy()).copy()
                    )
                    db.save_data(supabase_client, db.GOALS_TABLE, st.session_state.goals_df, user_id) # Adaptado V5.0
                    st.success("¡Sincronización completa! Recargando...")
                    st.session_state.force_filter_recalc = True
                    time.sleep(2)
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Ocurrió un error al procesar el archivo CSV: {e}")
            else:
                st.warning("⚠️ No se ha seleccionado ningún archivo.")

    if st.session_state.get('transactions_df', pd.DataFrame()).empty:
        st.info("ℹ️ Aún no hay transacciones en el historial.")
        return

    df_historial = st.session_state.transactions_df.copy().sort_values(by='Fecha', ascending=False)
    df_historial.insert(0, "Seleccionar", False)
    all_categories_list = st.session_state.get('categories', {}).get('Ingreso', []) + st.session_state.get('categories', {}).get('Gasto', [])
    account_options = st.session_state.get('accounts_df', pd.DataFrame(columns=['Nombre']))['Nombre'].tolist()
    member_options = st.session_state.get('members', [])
    goal_options = st.session_state.get('goals_df', pd.DataFrame(columns=['Nombre']))['Nombre'].tolist()
    destination_options = sorted(list(set(account_options + goal_options + ['N/A'])))

    edited_df = st.data_editor(
        df_historial,
        column_config={
            "Seleccionar": st.column_config.CheckboxColumn("Eliminar?", width="small"),
            "Fecha": st.column_config.DatetimeColumn("Fecha", format="YYYY-MM-DD HH:mm", width="small"),
            "Tipo": st.column_config.TextColumn("Tipo", disabled=True, width="small"),
            "Categoría": st.column_config.SelectboxColumn("Categoría", options=all_categories_list, width="medium"),
            "Cuenta": st.column_config.SelectboxColumn("Cuenta", options=account_options, width="medium"),
            "Monto": st.column_config.NumberColumn("Monto ($)", format="%.2f", width="small"),
            "Descripción": st.column_config.TextColumn("Descripción", width="large"),
            "Miembro": st.column_config.SelectboxColumn("Miembro", options=member_options, width="small"),
            "Destino": st.column_config.SelectboxColumn("Destino", options=destination_options, width="medium"),
            "Recurrente": st.column_config.CheckboxColumn("Rec?", width="small"),
            "Frecuencia": st.column_config.SelectboxColumn("Frec.", options=list(db.FREQUENCY_MULTIPLIER.keys()), width="small"),
        },
        key="history_editor", hide_index=True, use_container_width=True, num_rows="dynamic", height=600
    )

    col_save, col_delete = st.columns([1, 4])
    with col_save:
        if st.button("💾 Guardar Cambios", type="primary"):
            try:
                df_to_save = edited_df.drop(columns=['Seleccionar'], errors='ignore')
                df_to_save['Monto'] = pd.to_numeric(df_to_save['Monto'], errors='coerce').fillna(0.0)
                df_to_save['Fecha'] = pd.to_datetime(df_to_save['Fecha'], errors='coerce')
                df_to_save = df_to_save.dropna(subset=['Fecha', 'Monto'])
                st.session_state.transactions_df = df_to_save.sort_values(by='Fecha', ascending=False).reset_index(drop=True)
                db.save_data(supabase_client, db.TRANSACTIONS_TABLE, st.session_state.transactions_df, user_id)
                st.session_state.goals_df = db.update_goal_progress(st.session_state.transactions_df, st.session_state.goals_df)
                db.save_data(supabase_client, db.GOALS_TABLE, st.session_state.goals_df, user_id)
                st.session_state.force_filter_recalc = True
                st.success("✅ Cambios guardados con éxito.")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error al guardar cambios: {e}. Verifica los datos editados.")
    with col_delete:
        if st.button("🗑️ Eliminar Seleccionados", type="secondary"):
            rows_to_keep = edited_df[edited_df['Seleccionar'] == False]
            rows_deleted = edited_df[edited_df['Seleccionar'] == True]
            num_deleted = len(rows_deleted)
            if num_deleted > 0:
                try:
                    df_updated = rows_to_keep.drop(columns=['Seleccionar'], errors='ignore')
                    df_updated['Monto'] = pd.to_numeric(df_updated['Monto'], errors='coerce').fillna(0.0)
                    df_updated['Fecha'] = pd.to_datetime(df_updated['Fecha'], errors='coerce')
                    df_updated = df_updated.dropna(subset=['Fecha', 'Monto'])
                    st.session_state.transactions_df = df_updated.sort_values(by='Fecha', ascending=False).reset_index(drop=True)
                    db.save_data(supabase_client, db.TRANSACTIONS_TABLE, st.session_state.transactions_df, user_id)
                    st.session_state.goals_df = db.update_goal_progress(st.session_state.transactions_df, st.session_state.goals_df)
                    db.save_data(supabase_client, db.GOALS_TABLE, st.session_state.goals_df, user_id)
                    st.session_state.force_filter_recalc = True
                    st.success(f"✅ {num_deleted} transacciones eliminadas con éxito.")
                    st.rerun()
                except Exception as e:
                     st.error(f"❌ Error al eliminar transacciones: {e}.")
            else:
                st.warning("⚠️ No se seleccionaron transacciones para eliminar.")


# --- Asistente de Configuración Inicial (Adaptado V5.0) ---
def run_setup_wizard(supabase_client: Client, user_id: str):
    st.title("👋 ¡Bienvenido a Guardian Doméstico!")
    st.subheader("Configuración Inicial Rápida")
    st.write("Detectamos que es tu primera vez. Vamos a configurar algunos datos básicos para empezar.")

    with st.form("setup_wizard_form"):
        st.markdown("---")
        st.subheader("👥 Miembros del Hogar")
        members_input = st.text_area("Escribe los nombres de los miembros (uno por línea):", height=100, placeholder="Ejemplo:\nJuan Pérez\nMaria García")
        st.markdown("---")
        st.subheader("💰 Ingreso Principal")
        income_amount = st.number_input("Monto del Ingreso Principal:", min_value=0.01, step=100.0, format="%.2f")
        income_freq = st.selectbox("Frecuencia del Ingreso:", db.INCOME_FREQUENCIES, index=0)
        income_member = st.text_input("¿Quién recibe este ingreso? (Escribe un nombre de la lista de miembros)")
        st.markdown("---")
        st.subheader("🏦 Cuenta Bancaria Principal")
        account_name = st.text_input("Nombre de tu Cuenta Principal (Ej: Banco XYZ):", value="Cuenta Principal")
        account_balance = st.number_input("Saldo Inicial Actual ($):", min_value=0.0, step=100.0, format="%.2f", value=1000.0)
        st.markdown("---")
        st.subheader("🎯 Primera Meta de Ahorro")
        goal_name = st.text_input("Nombre de la Meta (Ej: Fondo de Emergencia):", value="Fondo de Emergencia")
        goal_target = st.number_input("Monto Objetivo ($):", min_value=1.0, step=500.0, format="%.2f", value=5000.0)
        goal_days = st.number_input("¿En cuántos días quieres alcanzarla? (Aprox.):", min_value=1, value=365)
        st.markdown("---")
        submitted = st.form_submit_button("🚀 ¡Empezar a Usar Guardian Doméstico!")

        if submitted:
            try:
                # 1. Miembros
                members_list = [name.strip() for name in members_input.split('\n') if name.strip()]
                if not members_list: members_list = ["Titular Principal"]
                db.save_members(supabase_client, sorted(members_list), user_id)
                if income_member not in members_list:
                    income_member_assigned = members_list[0]
                    st.warning(f"El miembro '{income_member}' no estaba en la lista, se asignó el ingreso a '{income_member_assigned}'.")
                else:
                    income_member_assigned = income_member

                # 2. Cuentas
                accounts = db.DEFAULT_ACCOUNTS.copy()
                new_account = pd.DataFrame([{'Nombre': account_name, 'Tipo': 'Banco', 'Saldo Inicial': float(account_balance)}])
                accounts = pd.concat([accounts, new_account], ignore_index=True)
                db.save_data(supabase_client, db.ACCOUNTS_TABLE, accounts, user_id)

                # 3. Ingreso Recurrente (Transacción)
                first_income = pd.DataFrame([{
                    'Fecha': pd.to_datetime(datetime.now()), 'Tipo': 'Ingreso', 'Categoría': 'Salario',
                    'Cuenta': account_name, 'Monto': float(income_amount),
                    'Descripción': 'Ingreso Principal (Configuración Inicial)', 'Miembro': income_member_assigned,
                    'Destino': 'N/A', 'Recurrente': True, 'Frecuencia': income_freq
                }])
                db.save_data(supabase_client, db.TRANSACTIONS_TABLE, first_income, user_id)

                # 4. Meta de Ahorro
                goal_date = datetime.now().date() + timedelta(days=int(goal_days))
                first_goal = pd.DataFrame([{
                    'Nombre': goal_name, 'Monto Objetivo': float(goal_target),
                    'Monto Aportado': 0.0, 'Fecha Objetivo': goal_date
                }])
                db.save_data(supabase_client, db.GOALS_TABLE, first_goal, user_id)

                # 5. Guardar configuraciones default
                db.save_categories(supabase_client, db.DEFAULT_CATEGORIES, user_id)
                db.save_config_key(supabase_client, user_id, db.CATEGORY_BUDGET_KEY, db.DEFAULT_CATEGORY_BUDGETS)
                db.load_budget_config(supabase_client, user_id) # Esto crea el presupuesto default en la DB

                st.success("🎉 ¡Configuración completada! Cargando la aplicación...")
                st.balloons()
                st.session_state.wizard_mode = False # Salir del modo wizard
                st.session_state.wizard_completed = True # Forzar recarga completa
                time.sleep(2)
                st.rerun()
            except Exception as e:
                st.error(f"❌ Ocurrió un error al guardar la configuración: {e}")
                st.error("Por favor, revisa los datos ingresados e intenta de nuevo.")
