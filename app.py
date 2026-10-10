"""
Inventario de Aulas - Versión Web (Streamlit)
Reutiliza la base de datos SQLite del programa de escritorio.
"""
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# ---------- CONFIGURACIÓN ----------
DB_NAME = "inventario_aulas.db"

st.set_page_config(
    page_title="Inventario de Aulas",
    page_icon="🏫",
    layout="wide",
    initial_sidebar_state="expanded",
)

TIPOS = ["Ordenador", "Portátil", "Proyector", "Pizarra digital",
         "Pantalla", "Altavoces", "Impresora", "Router", "Switch",
         "Cámara", "Teclado", "Ratón", "CPU", "Protector de tensión", "Otro"]

ESTADOS = ["Operativo", "Averiado", "En reparación", "Obsoleto", "Baja"]


# ---------- BASE DE DATOS ----------
def get_con():
    con = sqlite3.connect(DB_NAME)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db():
    con = get_con()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS aulas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            ubicacion TEXT
        )""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS equipos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aula_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            marca TEXT, modelo TEXT, num_serie TEXT,
            estado TEXT, fecha_instalacion TEXT, notas TEXT,
            FOREIGN KEY (aula_id) REFERENCES aulas(id) ON DELETE CASCADE
        )""")
    con.commit()
    con.close()


@st.cache_data(ttl=5)
def listar_aulas():
    con = get_con()
    df = pd.read_sql_query(
        "SELECT id, nombre, ubicacion FROM aulas ORDER BY ubicacion, nombre",
        con)
    con.close()
    return df


@st.cache_data(ttl=5)
def listar_equipos(aula_id):
    con = get_con()
    df = pd.read_sql_query("""
        SELECT id, tipo, marca, modelo, num_serie, estado,
               fecha_instalacion, notas
        FROM equipos WHERE aula_id=? ORDER BY tipo
    """, con, params=(aula_id,))
    con.close()
    return df


@st.cache_data(ttl=5)
def estadisticas_globales():
    con = get_con()
    total_aulas = con.execute("SELECT COUNT(*) FROM aulas").fetchone()[0]
    total_equipos = con.execute("SELECT COUNT(*) FROM equipos").fetchone()[0]
    por_estado = pd.read_sql_query(
        "SELECT estado, COUNT(*) as n FROM equipos GROUP BY estado", con)
    por_tipo = pd.read_sql_query(
        "SELECT tipo, COUNT(*) as n FROM equipos GROUP BY tipo ORDER BY n DESC", con)
    con.close()
    return total_aulas, total_equipos, por_estado, por_tipo


def insertar_equipo(aula_id, datos):
    con = get_con()
    con.execute("""
        INSERT INTO equipos (aula_id, tipo, marca, modelo, num_serie,
                             estado, fecha_instalacion, notas)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (aula_id, *datos))
    con.commit()
    con.close()
    st.cache_data.clear()


def actualizar_equipo(equipo_id, datos):
    con = get_con()
    con.execute("""
        UPDATE equipos SET tipo=?, marca=?, modelo=?, num_serie=?,
               estado=?, fecha_instalacion=?, notas=?
        WHERE id=?
    """, (*datos, equipo_id))
    con.commit()
    con.close()
    st.cache_data.clear()


def eliminar_equipo(equipo_id):
    con = get_con()
    con.execute("DELETE FROM equipos WHERE id=?", (equipo_id,))
    con.commit()
    con.close()
    st.cache_data.clear()


# ---------- INTERFAZ ----------
def main():
    init_db()

    st.title("🏫 Inventario de Equipos por Aula")

    # --- Barra lateral: selección de aula
    with st.sidebar:
        st.header("📚 Aulas")
        aulas = listar_aulas()
        if aulas.empty:
            st.warning("No hay aulas en la base de datos.\n\n"
                       "Importa el CSV con `python importar_csv.py`.")
            st.stop()

        # Agrupar por ubicación
        opciones = []
        for _, row in aulas.iterrows():
            etiqueta = f"{row['nombre']}  ({row['ubicacion'] or 'sin planta'})"
            opciones.append((etiqueta, row["id"]))

        seleccion = st.radio(
            "Selecciona un aula:",
            options=[o[0] for o in opciones],
            label_visibility="collapsed",
        )
        aula_id = dict(opciones)[seleccion]
        aula_nombre = seleccion.split("  (")[0]

        st.divider()
        st.caption(f"Base de datos: `{DB_NAME}`")
        if st.button("🔄 Refrescar datos", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # --- Tabs principales
    tab_inv, tab_add, tab_stats = st.tabs(
        ["📋 Inventario del aula", "➕ Añadir equipo", "📊 Estadísticas"]
    )

    # ============ TAB 1: INVENTARIO ============
    with tab_inv:
        st.subheader(f"Equipos en {aula_nombre}")

        equipos = listar_equipos(aula_id)

        if equipos.empty:
            st.info("Esta aula no tiene equipos registrados todavía.")
        else:
            # Búsqueda
            filtro = st.text_input("🔍 Buscar (tipo, marca, modelo, nº serie...)",
                                    "").strip().lower()

            df_filtrado = equipos.copy()
            if filtro:
                mascara = df_filtrado.apply(
                    lambda row: filtro in " ".join(
                        str(x) for x in row.values).lower(), axis=1)
                df_filtrado = df_filtrado[mascara]

            st.caption(f"Mostrando {len(df_filtrado)} de {len(equipos)} equipos")

            # Colores de estado
            def color_estado(val):
                colores = {
                    "Operativo": "background-color: #d4edda",
                    "Averiado": "background-color: #f8d7da",
                    "En reparación": "background-color: #fff3cd",
                    "Obsoleto": "background-color: #e2e3e5",
                    "Baja": "background-color: #d6d8db",
                }
                return colores.get(val, "")

            st.dataframe(
                df_filtrado.style.map(color_estado, subset=["estado"]),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "id": st.column_config.NumberColumn("ID", width="small"),
                    "tipo": st.column_config.TextColumn("Tipo", width="medium"),
                    "marca": st.column_config.TextColumn("Marca", width="small"),
                    "modelo": st.column_config.TextColumn("Modelo", width="medium"),
                    "num_serie": st.column_config.TextColumn("Nº Serie", width="small"),
                    "estado": st.column_config.TextColumn("Estado", width="small"),
                    "fecha_instalacion": st.column_config.TextColumn("Instalación", width="small"),
                    "notas": st.column_config.TextColumn("Notas", width="large"),
                },
            )

            # Exportar CSV
            csv = df_filtrado.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Exportar CSV",
                csv,
                file_name=f"{aula_nombre.replace(' ', '_')}.csv",
                mime="text/csv",
            )

            # Editar / eliminar
            st.divider()
            st.subheader("✏️ Editar o eliminar equipo")
            opciones_eq = {
                f"#{r['id']} — {r['tipo']} {r['marca'] or ''} {r['modelo'] or ''}".strip():
                r for _, r in equipos.iterrows()
            }
            sel_eq = st.selectbox("Selecciona un equipo:", list(opciones_eq.keys()))
            equipo = opciones_eq[sel_eq]

            with st.form("form_editar"):
                col1, col2 = st.columns(2)
                with col1:
                    tipo = st.selectbox("Tipo", TIPOS,
                        index=TIPOS.index(equipo["tipo"]) if equipo["tipo"] in TIPOS else 0)
                    marca = st.text_input("Marca", equipo["marca"] or "")
                    modelo = st.text_input("Modelo", equipo["modelo"] or "")
                    num_serie = st.text_input("Nº de serie", equipo["num_serie"] or "")
                with col2:
                    estado = st.selectbox("Estado", ESTADOS,
                        index=ESTADOS.index(equipo["estado"]) if equipo["estado"] in ESTADOS else 0)
                    fecha = st.text_input("Fecha instalación (AAAA-MM-DD)",
                                          equipo["fecha_instalacion"] or "")
                    notas = st.text_area("Notas", equipo["notas"] or "")

                col_b1, col_b2 = st.columns([1, 1])
                with col_b1:
                    guardar = st.form_submit_button("💾 Guardar cambios",
                                                     use_container_width=True)
                with col_b2:
                    borrar = st.form_submit_button("🗑️ Eliminar equipo",
                                                    use_container_width=True)

                if guardar:
                    actualizar_equipo(equipo["id"],
                        (tipo, marca, modelo, num_serie, estado, fecha, notas))
                    st.success("Equipo actualizado")
                    st.rerun()

                if borrar:
                    eliminar_equipo(equipo["id"])
                    st.success("Equipo eliminado")
                    st.rerun()

    # ============ TAB 2: AÑADIR EQUIPO ============
    with tab_add:
        st.subheader(f"Añadir equipo a {aula_nombre}")
        with st.form("form_nuevo", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                tipo_n = st.selectbox("Tipo *", TIPOS)
                marca_n = st.text_input("Marca")
                modelo_n = st.text_input("Modelo")
                num_serie_n = st.text_input("Nº de serie")
            with col2:
                estado_n = st.selectbox("Estado", ESTADOS, index=0)
                fecha_n = st.text_input("Fecha instalación (AAAA-MM-DD)",
                                        datetime.now().strftime("%Y-%m-%d"))
                notas_n = st.text_area("Notas")

            enviado = st.form_submit_button("➕ Añadir equipo",
                                             use_container_width=True)
            if enviado:
                if not tipo_n:
                    st.error("El tipo es obligatorio.")
                else:
                    insertar_equipo(aula_id,
                        (tipo_n, marca_n, modelo_n, num_serie_n,
                         estado_n, fecha_n, notas_n))
                    st.success(f"Equipo '{tipo_n}' añadido a {aula_nombre}")
                    st.rerun()

    # ============ TAB 3: ESTADÍSTICAS ============
    with tab_stats:
        st.subheader("📊 Estadísticas globales")
        total_aulas, total_equipos, por_estado, por_tipo = estadisticas_globales()

        col1, col2, col3 = st.columns(3)
        col1.metric("Aulas registradas", total_aulas)
        col2.metric("Equipos totales", total_equipos)
        operativos = 0
        if not por_estado.empty:
            operativos = por_estado.loc[
                por_estado["estado"] == "Operativo", "n"].sum()
        col3.metric("Equipos operativos", int(operativos))

        col_a, col_b = st.columns(2)
        with col_a:
            st.write("**Equipos por estado**")
            st.dataframe(por_estado, use_container_width=True, hide_index=True)
            st.bar_chart(por_estado.set_index("estado")["n"])
        with col_b:
            st.write("**Equipos por tipo**")
            st.dataframe(por_tipo, use_container_width=True, hide_index=True)
            st.bar_chart(por_tipo.set_index("tipo")["n"])


if __name__ == "__main__":
    main()