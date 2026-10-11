"""
Inventario de Aulas - Versión Web con login, roles y Supabase
"""
from datetime import datetime

import pandas as pd
import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
from supabase import create_client, Client

# ---------- CONFIGURACIÓN ----------
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


# ---------- SUPABASE ----------
@st.cache_resource
def get_supabase() -> Client:
    """Crea el cliente de Supabase (cacheado)."""
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


# ---------- LOGIN ----------
def cargar_config_auth():
    """Carga la config desde secrets (nube) o desde auth.yaml (local)."""
    try:
        if "auth" in st.secrets:
            return st.secrets["auth"].to_dict()
    except Exception:
        pass
    try:
        with open("auth.yaml", encoding="utf-8") as f:
            return yaml.load(f, Loader=SafeLoader)
    except FileNotFoundError:
        st.error(
            "❌ No se ha encontrado la configuración de usuarios.\n\n"
            "**En local**: crea `auth.yaml` en la carpeta del proyecto.\n\n"
            "**En Streamlit Cloud**: ve a *Settings → Secrets* y pega "
            "la configuración en formato TOML."
        )
        st.stop()


def inicializar_autenticador():
    config = cargar_config_auth()
    authenticator = stauth.Authenticate(
        config["credentials"],
        config["cookie"]["name"],
        config["cookie"]["key"],
        config["cookie"]["expiry_days"],
    )
    return authenticator


def es_admin():
    roles = st.session_state.get("roles") or []
    return "admin" in roles


# ---------- ACCESO A DATOS ----------
@st.cache_data(ttl=30)
def listar_aulas():
    """Devuelve todas las aulas ordenadas por ubicación y nombre."""
    sb = get_supabase()
    resp = sb.table("aulas").select("id, nombre, ubicacion").order(
        "ubicacion").order("nombre").execute()
    return pd.DataFrame(resp.data)


@st.cache_data(ttl=30)
def listar_equipos(aula_id):
    """Devuelve los equipos de un aula."""
    sb = get_supabase()
    resp = (sb.table("equipos")
              .select("id, tipo, marca, modelo, num_serie, estado, "
                      "fecha_instalacion, notas")
              .eq("aula_id", aula_id)
              .order("tipo")
              .execute())
    return pd.DataFrame(resp.data)


@st.cache_data(ttl=30)
def estadisticas_globales():
    """Estadísticas globales del inventario."""
    sb = get_supabase()
    aulas = sb.table("aulas").select("id", count="exact").execute()
    equipos = sb.table("equipos").select("id, estado, tipo").execute()

    total_aulas = aulas.count or 0
    df_equipos = pd.DataFrame(equipos.data)
    total_equipos = len(df_equipos)

    if df_equipos.empty:
        por_estado = pd.DataFrame(columns=["estado", "n"])
        por_tipo = pd.DataFrame(columns=["tipo", "n"])
    else:
        por_estado = (df_equipos.groupby("estado").size()
                      .reset_index(name="n"))
        por_tipo = (df_equipos.groupby("tipo").size()
                    .reset_index(name="n")
                    .sort_values("n", ascending=False))

    return total_aulas, total_equipos, por_estado, por_tipo


def insertar_equipo(aula_id, datos):
    sb = get_supabase()
    sb.table("equipos").insert({
        "aula_id": aula_id,
        "tipo": datos[0],
        "marca": datos[1],
        "modelo": datos[2],
        "num_serie": datos[3],
        "estado": datos[4],
        "fecha_instalacion": datos[5],
        "notas": datos[6],
    }).execute()
    st.cache_data.clear()


def actualizar_equipo(equipo_id, datos):
    sb = get_supabase()
    sb.table("equipos").update({
        "tipo": datos[0],
        "marca": datos[1],
        "modelo": datos[2],
        "num_serie": datos[3],
        "estado": datos[4],
        "fecha_instalacion": datos[5],
        "notas": datos[6],
    }).eq("id", equipo_id).execute()
    st.cache_data.clear()


def eliminar_equipo(equipo_id):
    sb = get_supabase()
    sb.table("equipos").delete().eq("id", equipo_id).execute()
    st.cache_data.clear()


# ---------- INTERFAZ ----------
def main():
    # --- LOGIN ---
    authenticator = inicializar_autenticador()
    authenticator.login(location="main")

    auth_status = st.session_state.get("authentication_status")

    if auth_status is False:
        st.error("❌ Usuario o contraseña incorrectos.")
        st.stop()

    if auth_status is None:
        st.warning("🔒 Introduce tus credenciales para acceder.")
        st.info("Si no tienes cuenta, contacta con el administrador TIC del centro.")
        st.stop()

    # --- USUARIO AUTENTICADO ---
    usuario_nombre = st.session_state.get("name") or st.session_state.get("username")
    usuario_rol = "admin" if es_admin() else "viewer"

    col_info, col_logout = st.columns([4, 1])
    with col_info:
        st.markdown("### 🏫 Inventario de Equipos por Aula")
        emoji = "👑" if usuario_rol == "admin" else "👤"
        st.caption(f"{emoji} Conectado como **{usuario_nombre}** · Rol: `{usuario_rol}`")
    with col_logout:
        authenticator.logout("Cerrar sesión", location="main")

    st.divider()

    # --- Barra lateral ---
    with st.sidebar:
        st.header("📚 Aulas")
        aulas = listar_aulas()
        if aulas.empty:
            st.warning("No hay aulas en la base de datos.")
            st.stop()

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
        if st.button("🔄 Refrescar datos", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # --- Pestañas según el rol ---
    if usuario_rol == "admin":
        tab_inv, tab_add, tab_stats = st.tabs(
            ["📋 Inventario del aula", "➕ Añadir equipo", "📊 Estadísticas"]
        )
    else:
        tab_inv, tab_stats = st.tabs(
            ["📋 Inventario del aula", "📊 Estadísticas"]
        )
        tab_add = None

    # ============ TAB 1: INVENTARIO ============
    with tab_inv:
        st.subheader(f"Equipos en {aula_nombre}")
        equipos = listar_equipos(aula_id)

        if equipos.empty:
            st.info("Esta aula no tiene equipos registrados todavía.")
        else:
            filtro = st.text_input(
                "🔍 Buscar (tipo, marca, modelo, nº serie...)", "").strip().lower()

            df_filtrado = equipos.copy()
            if filtro:
                mascara = df_filtrado.apply(
                    lambda row: filtro in " ".join(
                        str(x) for x in row.values).lower(), axis=1)
                df_filtrado = df_filtrado[mascara]

            st.caption(f"Mostrando {len(df_filtrado)} de {len(equipos)} equipos")

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
            )

            csv = df_filtrado.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Exportar CSV",
                csv,
                file_name=f"{aula_nombre.replace(' ', '_')}.csv",
                mime="text/csv",
            )

            if usuario_rol == "admin":
                st.divider()
                st.subheader("✏️ Editar o eliminar equipo")
                opciones_eq = {
                    f"#{r['id']} — {r['tipo']} {r['marca'] or ''} {r['modelo'] or ''}".strip():
                    r for _, r in equipos.iterrows()
                }
                sel_eq = st.selectbox("Selecciona un equipo:",
                                       list(opciones_eq.keys()))
                equipo = opciones_eq[sel_eq]

                with st.form("form_editar"):
                    col1, col2 = st.columns(2)
                    with col1:
                        tipo = st.selectbox("Tipo", TIPOS,
                            index=TIPOS.index(equipo["tipo"])
                            if equipo["tipo"] in TIPOS else 0)
                        marca = st.text_input("Marca", equipo["marca"] or "")
                        modelo = st.text_input("Modelo", equipo["modelo"] or "")
                        num_serie = st.text_input("Nº de serie",
                                                  equipo["num_serie"] or "")
                    with col2:
                        estado = st.selectbox("Estado", ESTADOS,
                            index=ESTADOS.index(equipo["estado"])
                            if equipo["estado"] in ESTADOS else 0)
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
            else:
                st.info("👤 Modo solo lectura. Contacta con el administrador TIC "
                        "para modificar equipos.")

    # ============ TAB 2: AÑADIR EQUIPO (solo admin) ============
    if tab_add is not None:
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
            if not por_estado.empty:
                st.bar_chart(por_estado.set_index("estado")["n"])
        with col_b:
            st.write("**Equipos por tipo**")
            st.dataframe(por_tipo, use_container_width=True, hide_index=True)
            if not por_tipo.empty:
                st.bar_chart(por_tipo.set_index("tipo")["n"])


if __name__ == "__main__":
    main()