"""
C&A Systems - Azure Inventory Dashboard
========================================
Dashboard interactivo que lee los resultados del runner ARG y los visualiza
en una sola interfaz unificada.

Uso:
    cd ~/casystem/dashboard
    streamlit run dashboard.py

Se abre automaticamente en el navegador en http://localhost:8501
"""

from __future__ import annotations  # Compatibilidad con Python 3.9

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from auth import login, check_auth, logout
# ============================================================================
# Configuracion de pagina
# ============================================================================
st.set_page_config(
    page_title="C&A Systems — Azure Inventory",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================================
# Autenticación
# ============================================================================
if not check_auth():
    login()
    st.stop()

# Paleta corporativa refinada
COLOR_PRIMARY = "#0F4C81"    # Azul corporativo profundo
COLOR_OK = "#0E7C66"          # Verde sobrio
COLOR_WARN = "#D97706"        # Ambar (en lugar de amarillo brillante)
COLOR_DANGER = "#B91C1C"      # Rojo profundo
COLOR_NEUTRAL = "#475569"     # Slate gray
COLOR_LIGHT_BG = "#F8FAFC"    # Fondo sutil

# CSS corporativo
st.markdown(
    """
    <style>
        /* Tipografia */
        html, body, [class*="css"] {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                         "Helvetica Neue", Arial, sans-serif;
        }

        /* Header */
        h1 {
            color: #0F4C81;
            font-weight: 600;
            letter-spacing: -0.02em;
        }
        h2, h3 {
            color: #1F2937;
            font-weight: 600;
        }

        /* Metrics */
        div[data-testid="metric-container"] {
            background-color: white;
            border: 1px solid #E5E7EB;
            padding: 16px 20px;
            border-radius: 6px;
            box-shadow: none;
        }
        div[data-testid="metric-container"] > label {
            color: #6B7280;
            font-size: 0.8rem;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        div[data-testid="metric-container"] > div[data-testid="stMetricValue"] {
            font-size: 1.85rem;
            font-weight: 600;
            color: #1F2937;
        }

        /* Tabs - estilo corporativo limpio */
        .stTabs [data-baseweb="tab-list"] {
            gap: 0;
            border-bottom: 1px solid #E5E7EB;
        }
        .stTabs [data-baseweb="tab"] {
            padding: 12px 24px;
            background-color: transparent;
            border-radius: 0;
            border-bottom: 2px solid transparent;
            color: #6B7280;
            font-weight: 500;
            font-size: 0.9rem;
        }
        .stTabs [data-baseweb="tab"]:hover {
            background-color: #F8FAFC;
            color: #1F2937;
        }
        .stTabs [aria-selected="true"] {
            background-color: transparent;
            color: #0F4C81;
            border-bottom: 2px solid #0F4C81;
            font-weight: 600;
        }

        .block-container { padding-top: 2rem; padding-bottom: 2rem; }

        /* Reducir el espaciado excesivo */
        div[data-testid="stVerticalBlock"] > div { gap: 0.5rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================================
# Helpers
# ============================================================================
def find_resultados_dir() -> Path | None:
    """Busca la carpeta 'resultados' en ubicaciones comunes."""
    candidates = [
        Path.cwd() / "resultados",
        Path.cwd().parent / "queries" / "resultados",
        Path.cwd() / "queries" / "resultados",
        Path.cwd().parent / "resultados",
    ]
    for c in candidates:
        if c.exists() and c.is_dir():
            return c
    return None


@st.cache_data(show_spinner=False)
def load_csv(csv_dir: Path, filename: str) -> pd.DataFrame | None:
    """Carga un CSV de forma segura. Devuelve DataFrame vacio si el archivo
    dice '# Sin resultados', None si no existe."""
    path = csv_dir / filename
    if not path.exists():
        return None
    try:
        first_line = path.read_text(encoding="utf-8").splitlines()[0] if path.stat().st_size > 0 else ""
        if first_line.startswith("# Sin resultados"):
            return pd.DataFrame()
        return pd.read_csv(path)
    except Exception as e:
        st.warning(f"Error leyendo {filename}: {e}")
        return None


def empty_state(message: str = "Sin datos para mostrar"):
    """Muestra un mensaje amigable cuando no hay datos."""
    st.info(f"ℹ️ {message}")


def safe_len(df) -> int:
    return len(df) if df is not None and not df.empty else 0


def to_bool_series(s) -> pd.Series:
    """Convierte una columna a booleana real.
    PowerShell Export-Csv escribe 'True'/'False' como strings que pandas
    interpreta como enteros 0/1 o como strings; este helper normaliza."""
    if s.dtype == bool:
        return s
    return s.astype(str).str.strip().str.lower().isin(["true", "1"])


# ============================================================================
# Componentes visuales corporativos
# ============================================================================
SEVERITY_STYLES = {
    "CRÍTICO":   {"fg": "#B91C1C", "bg": "#FEF2F2", "border": "#FCA5A5"},
    "ALTO":      {"fg": "#C2410C", "bg": "#FFF7ED", "border": "#FDBA74"},
    "MEDIO":     {"fg": "#D97706", "bg": "#FFFBEB", "border": "#FCD34D"},
    "BAJO":      {"fg": "#0891B2", "bg": "#ECFEFF", "border": "#67E8F9"},
}


def severity_badge(level: str) -> str:
    """Badge HTML de severidad con estilo corporativo."""
    style = SEVERITY_STYLES.get(level, {"fg": "#475569", "bg": "#F1F5F9", "border": "#CBD5E1"})
    return (
        f'<span style="display: inline-block; '
        f'background-color: {style["bg"]}; '
        f'color: {style["fg"]}; '
        f'padding: 3px 10px; '
        f'border-radius: 3px; '
        f'border: 1px solid {style["border"]}; '
        f'font-size: 0.72rem; '
        f'font-weight: 700; '
        f'letter-spacing: 0.06em; '
        f'text-transform: uppercase; '
        f'font-family: -apple-system, sans-serif;">'
        f'{level}</span>'
    )


def status_pill(text: str, color: str) -> str:
    """Pill de estado con punto de color, formato corporativo."""
    return (
        f'<span style="display: inline-flex; align-items: center; gap: 8px; '
        f'padding: 5px 14px; '
        f'background-color: {color}10; '
        f'border: 1px solid {color}40; '
        f'border-radius: 4px; '
        f'color: {color}; '
        f'font-size: 0.78rem; '
        f'font-weight: 700; '
        f'text-transform: uppercase; '
        f'letter-spacing: 0.08em;">'
        f'<span style="display: inline-block; width: 8px; height: 8px; '
        f'background-color: {color}; border-radius: 50%;"></span>'
        f'{text}</span>'
    )


def callout(message: str, kind: str = "info"):
    """Caja informativa con estilo corporativo sobrio."""
    styles = {
        "info":    {"fg": "#0F4C81", "bg": "#F0F6FB", "border": "#0F4C81"},
        "success": {"fg": "#0E7C66", "bg": "#F0FBF7", "border": "#0E7C66"},
        "warning": {"fg": "#D97706", "bg": "#FFFBEB", "border": "#D97706"},
        "danger":  {"fg": "#B91C1C", "bg": "#FEF2F2", "border": "#B91C1C"},
        "neutral": {"fg": "#475569", "bg": "#F8FAFC", "border": "#94A3B8"},
    }
    s = styles.get(kind, styles["info"])
    st.markdown(
        f'<div style="background-color: {s["bg"]}; '
        f'border-left: 3px solid {s["border"]}; '
        f'padding: 12px 16px; '
        f'border-radius: 4px; '
        f'margin: 8px 0 16px 0; '
        f'color: #1F2937; '
        f'font-size: 0.93rem; '
        f'line-height: 1.5;">'
        f'{message}</div>',
        unsafe_allow_html=True,
    )


def section_header(text: str, subtitle: str | None = None):
    """Header de seccion con estilo corporativo."""
    st.markdown(
        f'<div style="margin: 1.5rem 0 0.75rem 0;">'
        f'<div style="font-size: 1.15rem; font-weight: 600; color: #1F2937;">{text}</div>'
        + (f'<div style="font-size: 0.85rem; color: #6B7280; margin-top: 2px;">{subtitle}</div>' if subtitle else '')
        + '</div>',
        unsafe_allow_html=True,
    )


# ============================================================================
# Health Score y Acciones Recomendadas
# ============================================================================
def calculate_health_score(data: dict) -> tuple[int, list[dict]]:
    """Calcula un score 0-100 con desglose por componente."""
    components = []

    # 1) Cobertura de tags (25 puntos)
    tc = data.get("tags_cob")
    if tc is not None and not tc.empty and "CoberturaPct" in tc.columns:
        cov = tc["CoberturaPct"].mean()
        s = (cov / 100) * 25
        det = f"{cov:.0f}% de cobertura promedio (meta 95%)"
    else:
        s, det = 12, "Sin datos de cobertura — score neutral"
    components.append({"nombre": "Etiquetado", "score": round(s, 1),
                       "max": 25, "detalle": det})

    # 2) Seguridad (30 puntos, escalonado por #hallazgos)
    nsg_n = safe_len(data.get("nsgs"))
    pub_n = safe_len(data.get("vms_pub"))
    total_sec = nsg_n + pub_n
    if total_sec == 0:
        s, det = 30, "Sin hallazgos críticos de exposición"
    elif total_sec <= 2:
        s, det = 22, f"{total_sec} hallazgo(s) menores"
    elif total_sec <= 5:
        s, det = 12, f"{total_sec} hallazgos — requiere remediación"
    else:
        s, det = 0, f"{total_sec} hallazgos — situación crítica"
    components.append({"nombre": "Seguridad", "score": s,
                       "max": 30, "detalle": det})

    # 3) Policy Compliance (20 puntos)
    pol = data.get("policy")
    if pol is not None and not pol.empty and "CumplimientoPct" in pol.columns:
        comp = pol["CumplimientoPct"].mean()
        s = (comp / 100) * 20
        det = f"{comp:.0f}% de cumplimiento promedio (meta 90%)"
    else:
        s, det = 10, "Sin políticas asignadas — score neutral"
    components.append({"nombre": "Gobierno (Policy)", "score": round(s, 1),
                       "max": 20, "detalle": det})

    # 4) FinOps / Waste (15 puntos)
    waste = (safe_len(data.get("discos_orf"))
             + safe_len(data.get("ips_huerf"))
             + safe_len(data.get("nics_orf"))
             + safe_len(data.get("snaps_old")))
    if waste == 0:
        s, det = 15, "Sin recursos ociosos detectados"
    elif waste <= 3:
        s, det = 11, f"{waste} recursos ociosos menores"
    elif waste <= 10:
        s, det = 6, f"{waste} recursos ociosos — limpieza recomendada"
    else:
        s, det = 0, f"{waste} recursos ociosos — fuga importante de costo"
    components.append({"nombre": "FinOps (waste)", "score": s,
                       "max": 15, "detalle": det})

    # 5) Estándares tecnicos (10 puntos): HTTPS/TLS
    s = 10
    issues = []
    st_df = data.get("storages")
    if st_df is not None and not st_df.empty:
        if "publicBlobAccess" in st_df.columns:
            pub = to_bool_series(st_df["publicBlobAccess"]).sum()
            if pub > 0:
                s -= 5
                issues.append(f"{pub} storage con blobs públicos")
        if "httpsOnly" in st_df.columns:
            no_https = (~to_bool_series(st_df["httpsOnly"])).sum()
            if no_https > 0:
                s -= 3
                issues.append(f"{no_https} storage sin HTTPS forzado")
    ap_df = data.get("apps")
    if ap_df is not None and not ap_df.empty and "httpsOnly" in ap_df.columns:
        no_https = (~to_bool_series(ap_df["httpsOnly"])).sum()
        if no_https > 0:
            s -= 2
            issues.append(f"{no_https} App Service sin HTTPS forzado")
    s = max(0, s)
    det = "Todos los recursos siguen estándares de cifrado" if not issues else "; ".join(issues)
    components.append({"nombre": "Estándares técnicos", "score": s,
                       "max": 10, "detalle": det})

    total = int(sum(c["score"] for c in components))
    return total, components


def get_score_status(score: int) -> tuple[str, str, str]:
    """Devuelve (color_hex, status_texto, mensaje)."""
    if score >= 80:
        return ("#0E7C66", "BUENO", "El entorno está en buen estado general. Mantenimiento de rutina recomendado.")
    elif score >= 60:
        return ("#D97706", "NECESITA ATENCIÓN", "Hay áreas importantes que requieren mejora a corto plazo.")
    elif score >= 40:
        return ("#C2410C", "REQUIERE ACCIÓN", "Existen riesgos significativos que deben atenderse pronto.")
    else:
        return ("#B91C1C", "CRÍTICO", "Se detectaron riesgos críticos. Acción inmediata requerida.")


def generate_top_actions(data: dict) -> list[dict]:
    """Genera lista de acciones priorizadas en lenguaje sencillo."""
    actions = []

    # NSG permisivas - prioridad maxima
    nsgs = data.get("nsgs")
    if nsgs is not None and not nsgs.empty:
        n = len(nsgs)
        # Detectar puertos criticos especificos
        critical_ports = []
        if "destinationPortRange" in nsgs.columns:
            ports = nsgs["destinationPortRange"].astype(str).tolist()
            port_names = {"22": "SSH", "3389": "RDP", "1433": "SQL",
                          "3306": "MySQL", "5432": "PostgreSQL",
                          "6379": "Redis", "27017": "MongoDB", "*": "TODOS"}
            for p in ports:
                if p in port_names:
                    critical_ports.append(f"{port_names[p]} ({p})")
        ports_text = ", ".join(set(critical_ports)) if critical_ports else "puertos sensibles"
        actions.append({
            "prioridad": 100,
            "severidad": "CRÍTICO",
            "titulo": f"Cerrar {n} regla(s) de firewall abierta(s) a Internet",
            "descripcion": (f"Hay {n} reglas NSG que permiten tráfico desde Internet (cualquier IP) hacia "
                            f"{ports_text}. Estos puertos son el blanco principal de ataques de fuerza bruta y "
                            f"escaneos automatizados."),
            "impacto": "Alto",
            "esfuerzo": "Bajo",
            "como": ("1) Restringir el origen a IPs corporativas o VPN. "
                     "2) Para acceso administrativo (SSH/RDP), usar Azure Bastion en lugar de exponer el puerto. "
                     "3) Documentar excepciones aprobadas según el estándar."),
        })

    # VMs con IP publica directa
    vms_pub = data.get("vms_pub")
    if vms_pub is not None and not vms_pub.empty:
        n = len(vms_pub)
        actions.append({
            "prioridad": 85,
            "severidad": "ALTO",
            "titulo": f"Quitar IP pública directa de {n} máquina(s) virtual(es)",
            "descripcion": (f"{n} VM(s) tienen una dirección IP pública asociada directamente, lo que las "
                            f"expone a Internet sin ningún balanceador, firewall o Bastion en medio. "
                            f"Cualquiera en el mundo puede intentar conectarse."),
            "impacto": "Alto",
            "esfuerzo": "Medio",
            "como": ("1) Para acceso administrativo: implementar Azure Bastion (acceso vía portal sin IP pública). "
                     "2) Para tráfico web: poner Application Gateway o Front Door delante. "
                     "3) Eliminar la Public IP del NIC de la VM."),
        })

    # Cobertura de tags
    tc = data.get("tags_cob")
    if tc is not None and not tc.empty and "CoberturaPct" in tc.columns:
        cov = tc["CoberturaPct"].mean()
        if cov < 95:
            sub_bajo = tc[tc["CoberturaPct"] < 95]
            n_subs = len(sub_bajo)
            sev = "ALTO" if cov < 80 else "MEDIO"
            pri = 75 if cov < 80 else 50
            actions.append({
                "prioridad": pri,
                "severidad": sev,
                "titulo": f"Completar etiquetas en recursos sin tags ({cov:.0f}% actual, meta 95%)",
                "descripcion": (f"La cobertura promedio de tags obligatorios es {cov:.0f}%, debajo del 95% "
                                f"que marca el estándar. {n_subs} suscripción(es) están debajo de la meta. "
                                f"Sin tags no se puede atribuir costo, asignar responsables ni gestionar "
                                f"el ciclo de vida de los recursos."),
                "impacto": "Medio",
                "esfuerzo": "Medio",
                "como": ("1) Identificar dueño técnico y de negocio de cada recurso sin tags. "
                         "2) Aplicar los 6 tags obligatorios (Environment, Application, Owner, "
                         "CostCenter, BusinessUnit, Client). "
                         "3) Configurar Azure Policy 'Require Tag' para evitar nuevos recursos sin tags."),
            })

    # Storage con acceso publico
    st_df = data.get("storages")
    if st_df is not None and not st_df.empty and "publicBlobAccess" in st_df.columns:
        pub_count = int(to_bool_series(st_df["publicBlobAccess"]).sum())
        if pub_count > 0:
            actions.append({
                "prioridad": 80,
                "severidad": "ALTO",
                "titulo": f"Desactivar acceso público en {pub_count} Storage Account(s)",
                "descripcion": (f"{pub_count} cuenta(s) de almacenamiento permiten lectura pública de blobs. "
                                f"Esto podría exponer datos sensibles si alguien sube por error archivos "
                                f"a contenedores públicos."),
                "impacto": "Alto",
                "esfuerzo": "Bajo",
                "como": ("1) Validar con el dueño que no haya casos legítimos de blobs públicos. "
                         "2) En el portal: Storage Account → Configuration → Allow Blob public access = Disabled. "
                         "3) Crear Azure Policy 'Storage accounts should disable public network access'."),
            })

    # Policy compliance baja
    pol = data.get("policy")
    if pol is not None and not pol.empty and "CumplimientoPct" in pol.columns:
        comp = pol["CumplimientoPct"].mean()
        if comp < 90:
            sev = "ALTO" if comp < 75 else "MEDIO"
            pri = 65 if comp < 75 else 40
            actions.append({
                "prioridad": pri,
                "severidad": sev,
                "titulo": f"Mejorar cumplimiento de Azure Policy ({comp:.0f}%, meta 90%)",
                "descripcion": (f"El cumplimiento de las políticas asignadas es {comp:.0f}%, debajo del 90% "
                                f"que marca el estándar. Hay recursos que están violando reglas de gobierno "
                                f"definidas por el cliente o por C&A Systems."),
                "impacto": "Medio",
                "esfuerzo": "Medio",
                "como": ("1) Revisar recursos NonCompliant en Azure Policy. "
                         "2) Remediar (manual o con remediation task). "
                         "3) Para casos legítimos, documentar excepción según el estándar."),
            })

    # Waste / recursos huerfanos
    waste = (safe_len(data.get("discos_orf"))
             + safe_len(data.get("ips_huerf"))
             + safe_len(data.get("nics_orf"))
             + safe_len(data.get("snaps_old")))
    if waste > 0:
        # Calcular tamaño total si hay discos/snapshots
        total_gb = 0
        d = data.get("discos_orf")
        if d is not None and "sizeGB" in d.columns:
            total_gb += d["sizeGB"].sum()
        s_old = data.get("snaps_old")
        if s_old is not None and "sizeGB" in s_old.columns:
            total_gb += s_old["sizeGB"].sum()
        gb_text = f" (~{int(total_gb)} GB de almacenamiento)" if total_gb > 0 else ""
        actions.append({
            "prioridad": 30,
            "severidad": "MEDIO",
            "titulo": f"Limpiar {waste} recurso(s) ocioso(s){gb_text}",
            "descripcion": (f"Se detectaron recursos sin uso que siguen generando costo: discos no asociados "
                            f"a ninguna VM, IPs públicas sueltas, NICs huérfanas y/o snapshots antiguos."),
            "impacto": "Bajo a Medio",
            "esfuerzo": "Bajo",
            "como": ("1) Validar con cada owner que el recurso realmente no está en uso. "
                     "2) Esperar 7 días por si se necesita restaurar. "
                     "3) Eliminar o archivar (snapshots se pueden enviar a storage frío)."),
        })

    actions.sort(key=lambda x: -x["prioridad"])
    return actions[:5]


def generate_positives_and_improvements(data: dict, score_components: list[dict]) -> tuple[list[str], list[str]]:
    """Genera listas de fortalezas y áreas de mejora en lenguaje sencillo."""
    positives = []
    improvements = []

    # Por cada componente del score, determinar si es fortaleza o oportunidad
    for c in score_components:
        pct = c["score"] / c["max"] if c["max"] > 0 else 0
        if pct >= 0.8:
            positives.append(f"**{c['nombre']}**: {c['detalle']}")
        elif pct < 0.5:
            improvements.append(f"**{c['nombre']}**: {c['detalle']}")

    # Específicos sin tag faltante
    tags_val = data.get("tags_val")
    if tags_val is not None and tags_val.empty:
        positives.append("**Formato de tags**: No se detectaron tags con formato inválido (CC-####, emails, catálogos)")

    # AKS con private cluster
    aks = data.get("aks")
    if aks is not None and not aks.empty and "privateCluster" in aks.columns:
        priv = to_bool_series(aks["privateCluster"]).sum()
        if priv == len(aks) and len(aks) > 0:
            positives.append(f"**AKS seguro**: Los {len(aks)} cluster(s) son privados (sin API server público)")

    return positives, improvements


# Glosario de terminos (para el tab de Resumen)
GLOSARIO = [
    ("Tag (Etiqueta)", "Metadato tipo clave-valor (ej: Environment=Prod) que se asigna a cada recurso para identificar dueño, ambiente, centro de costo, etc. Sin tags no se puede gestionar costo ni responsabilidades."),
    ("NSG (Network Security Group)", "Firewall a nivel de subred o NIC. Define reglas de qué tráfico se permite entrar y salir. Una regla 'abierta a Internet' significa que cualquier IP del mundo puede intentar conectarse."),
    ("IP pública", "Dirección IP visible desde Internet. Si una VM la tiene, cualquiera puede intentar conectarse directamente, lo que aumenta el riesgo de ataque."),
    ("Azure Policy", "Reglas automáticas que evalúan si los recursos cumplen con estándares definidos (ej: 'todo recurso debe tener tag CostCenter'). Cumplimiento = % de recursos que sí cumplen."),
    ("Recurso huérfano", "Recurso que ya no está siendo usado pero sigue desplegado y generando costo. Ejemplo: un disco que pertenecía a una VM eliminada hace meses."),
    ("FinOps", "Disciplina de optimización financiera en la nube. Identifica desperdicio, atribuye costos a equipos y mejora el retorno de inversión en cloud."),
    ("Bastion", "Servicio de Azure que permite conectarse a VMs vía RDP/SSH desde el portal, sin necesidad de exponer puertos a Internet. Mejora seguridad de acceso administrativo."),
    ("Suscripción", "Contenedor de facturación y administración en Azure. Un cliente puede tener varias (típicamente una por ambiente: Prod, QA, Dev)."),
]


# ============================================================================
# Sidebar: selector de cliente y snapshot
# ============================================================================
st.sidebar.title("Configuración")

# Buscar carpeta resultados
default_resultados = find_resultados_dir()
resultados_input = st.sidebar.text_input(
    "Ruta a carpeta resultados/",
    value=str(default_resultados) if default_resultados else "",
    help="Ruta absoluta o relativa a la carpeta resultados/ del runner",
)

if not resultados_input:
    st.warning("Indica la ruta a la carpeta `resultados/` en el sidebar.")
    st.stop()

resultados_dir = Path(resultados_input)
if not resultados_dir.exists():
    st.error(f"La carpeta `{resultados_dir}` no existe.")
    st.stop()

# Listar clientes
clients = sorted([d.name for d in resultados_dir.iterdir() if d.is_dir()])
if not clients:
    st.error(f"No hay subcarpetas de cliente en `{resultados_dir}`.")
    st.stop()

client = st.sidebar.selectbox("Cliente", clients)
client_path = resultados_dir / client

# Listar snapshots (ordenados, mas reciente primero)
snapshots = sorted(
    [d.name for d in client_path.iterdir() if d.is_dir()],
    reverse=True,
)
if not snapshots:
    st.error(f"No hay snapshots para el cliente `{client}`.")
    st.stop()

snapshot = st.sidebar.selectbox("Snapshot", snapshots, index=0)
snapshot_path = client_path / snapshot
csv_path = snapshot_path / "csv"

if not csv_path.exists():
    st.error(f"No existe la subcarpeta `csv/` en `{snapshot_path}`.")
    st.stop()

# Metadata del run
resumen_file = snapshot_path / "_resumen.json"
metadata = {}
if resumen_file.exists():
    try:
        metadata = json.loads(resumen_file.read_text(encoding="utf-8"))
    except Exception:
        pass

st.sidebar.divider()
st.sidebar.markdown("**Metadata del Snapshot**")
if metadata:
    st.sidebar.markdown(f"**Fecha**: `{metadata.get('fecha_ejecucion', 'N/A')}`")
    st.sidebar.markdown(f"**Suscripciones**: {len(metadata.get('suscripciones', []))}")
    n_ok = metadata.get("consultas_ok", 0)
    n_total = metadata.get("total_consultas", 0)
    estado = "OK" if n_ok == n_total else "Parcial"
    st.sidebar.markdown(f"**Consultas**: {estado} — {n_ok} / {n_total}")
    st.sidebar.markdown(f"**Filas totales**: {metadata.get('total_filas', 0):,}")
    st.sidebar.markdown(f"**Duración**: {metadata.get('duracion_total_seg', 0):.1f}s")

st.sidebar.divider()
if st.sidebar.button("Recargar datos", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# ============================================================================
# Cargar todos los datasets
# ============================================================================
inventario = load_csv(csv_path, "01-inventario-maestro.csv")
resumen_tipo = load_csv(csv_path, "02-resumen-por-tipo.csv")
resumen_sub = load_csv(csv_path, "03-resumen-por-suscripcion.csv")
resumen_loc = load_csv(csv_path, "04-resumen-por-ubicacion.csv")

tags_cump = load_csv(csv_path, "01-cumplimiento-tags-obligatorios.csv")
tags_cob = load_csv(csv_path, "02-cobertura-por-suscripcion.csv")
tags_val = load_csv(csv_path, "03-validacion-formato-tags.csv")

discos_orf = load_csv(csv_path, "01-discos-no-asociados.csv")
ips_huerf = load_csv(csv_path, "02-public-ips-huerfanas.csv")
nics_orf = load_csv(csv_path, "03-nics-sin-vm.csv")
vms_off = load_csv(csv_path, "04-vms-apagadas.csv")
snaps_old = load_csv(csv_path, "05-snapshots-antiguos.csv")

vms = load_csv(csv_path, "01-vms-detalle.csv")
apps = load_csv(csv_path, "02-app-services-detalle.csv")
sqls = load_csv(csv_path, "03-sql-databases-detalle.csv")
storages = load_csv(csv_path, "04-storage-accounts-detalle.csv")
aks = load_csv(csv_path, "05-aks-clusters-detalle.csv")

nsgs = load_csv(csv_path, "01-nsgs-reglas-permisivas.csv")
vms_pub = load_csv(csv_path, "02-vms-con-ip-publica.csv")

policy = load_csv(csv_path, "01-azure-policy-compliance.csv")

# Cost Management / FinOps histórico generado desde Microsoft Cost Management API
# IMPORTANTE: Para filtros dinámicos se exige este archivo.
# No hacemos fallback al CSV anterior porque ese no trae ResourceGroup/Suscripción.
COST_DYNAMIC_FILENAME = "01-costos-dinamicos.csv"
cost_history = load_csv(csv_path, COST_DYNAMIC_FILENAME)

# ============================================================================
# HEADER
# ============================================================================
st.title("Azure Inventory Dashboard")
st.markdown(
    f'<div style="color: #6B7280; font-size: 0.95rem; margin-bottom: 1.5rem;">'
    f'Cliente: <strong style="color: #1F2937;">{client}</strong>'
    f' &nbsp;&middot;&nbsp; Snapshot: <code>{snapshot}</code>'
    f'</div>',
    unsafe_allow_html=True,
)

# ============================================================================
# KPI ROW
# ============================================================================
section_header("Resumen Ejecutivo")
c1, c2, c3, c4, c5, c6 = st.columns(6)

with c1:
    total_recursos = safe_len(inventario)
    st.metric("Recursos", f"{total_recursos:,}")

with c2:
    n_subs = safe_len(resumen_sub)
    st.metric("Suscripciones", n_subs)

with c3:
    if tags_cob is not None and not tags_cob.empty and "CoberturaPct" in tags_cob.columns:
        cob = tags_cob["CoberturaPct"].mean()
        st.metric("Cobertura Tags", f"{cob:.1f}%",
                  delta="Meta 95%", delta_color="off")
    else:
        st.metric("Cobertura Tags", "—")

with c4:
    waste = safe_len(discos_orf) + safe_len(ips_huerf) + safe_len(nics_orf) + safe_len(snaps_old)
    st.metric(
        "Recursos Huérfanos",
        waste,
        delta=("Sin waste" if waste == 0 else f"{waste} a remediar"),
        delta_color=("normal" if waste == 0 else "inverse"),
    )

with c5:
    sec_findings = safe_len(nsgs) + safe_len(vms_pub)
    st.metric(
        "Hallazgos Seguridad",
        sec_findings,
        delta=("OK" if sec_findings == 0 else "Revisar"),
        delta_color=("normal" if sec_findings == 0 else "inverse"),
    )

with c6:
    if policy is not None and not policy.empty and "CumplimientoPct" in policy.columns:
        comp = policy["CumplimientoPct"].mean()
        st.metric("Policy Compliance", f"{comp:.1f}%",
                  delta="Meta 90%", delta_color="off")
    else:
        st.metric("Policy Compliance", "—")

st.divider()

# ============================================================================
# TABS
# ============================================================================
tab_summary, tab_inv, tab_tags, tab_fin, tab_sec, tab_gov, tab_costs, tab_data, tab_trend = st.tabs([
    "Resumen Cliente",
    "Inventario",
    "Etiquetado",
    "FinOps",
    "Seguridad",
    "Gobierno",
    "Costos",
    "Detalle Técnico",
    "Tendencias",
])

# ----------------------------------------------------------------------------
# TAB: RESUMEN CLIENTE (vista ejecutiva en lenguaje sencillo)
# ----------------------------------------------------------------------------
with tab_summary:
    # Empaquetar datos para los helpers
    _data = {
        "inventario": inventario, "resumen_sub": resumen_sub,
        "tags_cob": tags_cob, "tags_cump": tags_cump, "tags_val": tags_val,
        "discos_orf": discos_orf, "ips_huerf": ips_huerf, "nics_orf": nics_orf,
        "vms_off": vms_off, "snaps_old": snaps_old,
        "vms": vms, "apps": apps, "sqls": sqls, "storages": storages, "aks": aks,
        "nsgs": nsgs, "vms_pub": vms_pub, "policy": policy,
    }

    score, components = calculate_health_score(_data)
    color, status_txt, mensaje = get_score_status(score)
    actions = generate_top_actions(_data)
    positives, improvements = generate_positives_and_improvements(_data, components)

    # ===== HEALTH SCORE =====
    cA, cB = st.columns([2, 3])

    with cA:
        st.markdown(
            f"""
            <div style="background-color: white;
                        border: 1px solid #E5E7EB;
                        border-top: 4px solid {color};
                        padding: 28px 24px;
                        border-radius: 6px;
                        text-align: center;">
                <div style="font-size: 0.75rem; color: #6B7280;
                            text-transform: uppercase; letter-spacing: 0.1em;
                            font-weight: 600;">
                    Salud del Entorno
                </div>
                <div style="font-size: 4.5rem; font-weight: 600; color: #1F2937;
                            line-height: 1; margin: 16px 0 8px 0;
                            font-variant-numeric: tabular-nums;">
                    {score}<span style="font-size: 1.5rem; color: #9CA3AF; font-weight: 400;">/100</span>
                </div>
                <div style="margin: 16px 0 12px 0;">
                    {status_pill(status_txt, color)}
                </div>
                <div style="font-size: 0.9rem; color: #4B5563; line-height: 1.5;
                            margin-top: 12px;">
                    {mensaje}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with cB:
        section_header("Componentes del puntaje",
                       "Cada categoría aporta un máximo definido; las barras muestran el avance.")
        for c in components:
            pct = (c["score"] / c["max"] * 100) if c["max"] > 0 else 0
            if pct >= 80:
                indicator_color = COLOR_OK
            elif pct >= 50:
                indicator_color = COLOR_WARN
            else:
                indicator_color = COLOR_DANGER
            st.markdown(
                f'<div style="display: flex; justify-content: space-between; '
                f'align-items: center; margin-top: 12px; margin-bottom: 4px;">'
                f'<div style="display: flex; align-items: center; gap: 8px;">'
                f'<span style="display: inline-block; width: 6px; height: 6px; '
                f'background-color: {indicator_color}; border-radius: 50%;"></span>'
                f'<span style="font-weight: 600; color: #1F2937; font-size: 0.92rem;">{c["nombre"]}</span>'
                f'</div>'
                f'<span style="font-family: monospace; color: #6B7280; font-size: 0.85rem;">'
                f'{c["score"]} / {c["max"]} pts</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
            st.progress(pct / 100)
            st.markdown(
                f'<div style="font-size: 0.83rem; color: #6B7280; margin-bottom: 8px;">{c["detalle"]}</div>',
                unsafe_allow_html=True,
            )

    st.divider()

    # ===== LO QUE ESTÁ BIEN / LO QUE MEJORAR =====
    cA, cB = st.columns(2)

    with cA:
        section_header("Fortalezas")
        if positives:
            for p in positives:
                callout(p, kind="success")
        else:
            callout("No se detectaron fortalezas claras en este snapshot.", kind="neutral")

    with cB:
        section_header("Áreas a mejorar")
        if improvements:
            for imp in improvements:
                callout(imp, kind="warning")
        else:
            callout("No hay áreas críticas de mejora. Mantenimiento de rutina recomendado.", kind="success")

    st.divider()

    # ===== TOP 5 ACCIONES =====
    section_header("Acciones recomendadas",
                   "Ordenadas por prioridad. Iniciar por la primera.")

    if not actions:
        callout("No se detectaron acciones críticas pendientes en este snapshot.", kind="success")
    else:
        for i, a in enumerate(actions, 1):
            badge_html = severity_badge(a["severidad"])
            st.markdown(
                f'<div style="border: 1px solid #E5E7EB; border-radius: 6px; '
                f'padding: 18px 20px; margin-bottom: 12px; background-color: white;">'
                f'<div style="display: flex; align-items: center; gap: 12px; margin-bottom: 10px;">'
                f'<span style="font-size: 0.85rem; color: #9CA3AF; font-weight: 700; '
                f'font-family: monospace;">#{i}</span>'
                f'{badge_html}'
                f'<span style="font-size: 1.05rem; font-weight: 600; color: #1F2937;">{a["titulo"]}</span>'
                f'</div>'
                f'<div style="color: #4B5563; font-size: 0.93rem; line-height: 1.55; margin-bottom: 12px;">'
                f'{a["descripcion"]}'
                f'</div>'
                f'<div style="display: flex; gap: 24px; font-size: 0.85rem; color: #6B7280;">'
                f'<div><strong style="color: #1F2937;">Impacto:</strong> {a["impacto"]}</div>'
                f'<div><strong style="color: #1F2937;">Esfuerzo:</strong> {a["esfuerzo"]}</div>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            with st.expander("Procedimiento sugerido"):
                st.write(a["como"])

    # ===== GLOSARIO =====
    st.divider()
    with st.expander("Glosario de términos técnicos"):
        st.caption("Útil al presentar este dashboard a audiencias no técnicas.")
        for termino, definicion in GLOSARIO:
            st.markdown(f"**{termino}** — {definicion}")

# ----------------------------------------------------------------------------
# TAB: INVENTARIO
# ----------------------------------------------------------------------------
with tab_inv:
    callout("Inventario completo del entorno. Todos los recursos desplegados en Azure agrupados por tipo, suscripción y región. Base de los demás análisis.", kind="info")
    section_header("Distribución de Recursos")

    cA, cB = st.columns([3, 2])

    with cA:
        st.markdown("**Top 15 tipos de recursos**")
        if resumen_tipo is not None and not resumen_tipo.empty:
            top15 = resumen_tipo.nlargest(15, "Cantidad")
            top15["type_short"] = top15["type"].str.replace("microsoft.", "", regex=False)
            fig = px.bar(
                top15.sort_values("Cantidad"),
                x="Cantidad",
                y="type_short",
                orientation="h",
                color="Cantidad",
                color_continuous_scale=[[0, "#deecf9"], [1, COLOR_PRIMARY]],
            )
            fig.update_layout(
                height=520,
                yaxis_title=None,
                xaxis_title="Cantidad de recursos",
                showlegend=False,
                coloraxis_showscale=False,
                margin=dict(l=10, r=10, t=10, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            empty_state("No hay datos de resumen por tipo")

    with cB:
        st.markdown("**Por Suscripción**")
        if resumen_sub is not None and not resumen_sub.empty:
            fig = px.pie(
                resumen_sub,
                values="Total",
                names="subscriptionName",
                hole=0.55,
                color_discrete_sequence=px.colors.sequential.Blues_r,
            )
            fig.update_traces(textposition="outside", textinfo="label+value")
            fig.update_layout(
                height=260,
                showlegend=False,
                margin=dict(l=10, r=10, t=10, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            empty_state("Sin datos por suscripción")

        st.markdown("**Por Región**")
        if resumen_loc is not None and not resumen_loc.empty:
            fig = px.bar(
                resumen_loc.sort_values("Cantidad", ascending=True),
                x="Cantidad",
                y="location",
                orientation="h",
                color_discrete_sequence=[COLOR_PRIMARY],
            )
            fig.update_layout(
                height=240,
                yaxis_title=None,
                xaxis_title=None,
                margin=dict(l=10, r=10, t=10, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            empty_state("Sin datos por región")

    st.divider()
    st.markdown("**Inventario Completo** (búsqueda y filtro arriba de la tabla)")
    if inventario is not None and not inventario.empty:
        cols_show = [c for c in ["subscriptionName", "resourceGroup", "name", "type",
                                  "location", "sku", "skuTier"] if c in inventario.columns]
        st.dataframe(
            inventario[cols_show],
            use_container_width=True,
            height=400,
            hide_index=True,
        )
        st.download_button(
            "⬇️ Descargar inventario completo (CSV)",
            inventario.to_csv(index=False).encode("utf-8"),
            f"{client}_{snapshot}_inventario.csv",
            "text/csv",
        )
    else:
        empty_state("Inventario vacío o no disponible")

# ----------------------------------------------------------------------------
# TAB: TAGS
# ----------------------------------------------------------------------------
with tab_tags:
    callout("Sin etiquetas no se puede saber a qué aplicación, dueño o centro de costo pertenece cada recurso. La meta del estándar es 95% de cobertura en los 6 tags obligatorios: Environment, Application, Owner, CostCenter, BusinessUnit, Client.", kind="info")
    section_header("Cobertura de Tags Obligatorios")
    st.caption("Tags evaluados: Environment, Application, Owner, CostCenter, BusinessUnit, Client")

    cA, cB = st.columns(2)

    with cA:
        st.markdown("**Cobertura por Suscripción**")
        if tags_cob is not None and not tags_cob.empty:
            fig = px.bar(
                tags_cob.sort_values("CoberturaPct"),
                x="CoberturaPct",
                y="subscriptionName",
                orientation="h",
                color="CoberturaPct",
                color_continuous_scale=[
                    [0, COLOR_DANGER], [0.8, COLOR_WARN], [0.95, COLOR_OK], [1, COLOR_OK]
                ],
                range_color=[0, 100],
                text="CoberturaPct",
            )
            fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            fig.add_vline(x=95, line_dash="dash", line_color=COLOR_OK,
                          annotation_text="Meta 95%", annotation_position="top right")
            fig.update_layout(
                height=300,
                xaxis_title="Cobertura (%)",
                yaxis_title=None,
                xaxis_range=[0, 110],
                coloraxis_showscale=False,
                margin=dict(l=10, r=10, t=30, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)

            st.dataframe(tags_cob, use_container_width=True, hide_index=True)
        else:
            empty_state("Sin datos de cobertura")

    with cB:
        st.markdown("**Cumplimiento Global**")
        if tags_cump is not None and not tags_cump.empty:
            tags_completos_bool = to_bool_series(tags_cump["tagsCompletos"]) if "tagsCompletos" in tags_cump.columns else pd.Series([False] * len(tags_cump))
            cumple = int(tags_completos_bool.sum())
            total = len(tags_cump)
            no_cumple = total - cumple

            fig = go.Figure(data=[go.Pie(
                labels=["Con todos los tags", "Con tags faltantes"],
                values=[cumple, no_cumple],
                hole=0.65,
                marker=dict(colors=[COLOR_OK, COLOR_DANGER]),
            )])
            fig.update_traces(textposition="outside", textinfo="label+percent+value")
            fig.update_layout(
                height=300,
                showlegend=False,
                annotations=[dict(
                    text=f"{cumple/total*100:.0f}%" if total else "—",
                    x=0.5, y=0.5, font_size=28, showarrow=False
                )],
                margin=dict(l=10, r=10, t=30, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)

            # Tags más faltantes (recuento por tag)
            if "tagsFaltantes" in tags_cump.columns:
                st.markdown("**Tags más ausentes**")
                tag_names = ["Environment", "Application", "Owner",
                             "CostCenter", "BusinessUnit", "Client"]
                counts = {
                    t: tags_cump["tagsFaltantes"].fillna("").str.contains(t, regex=False).sum()
                    for t in tag_names
                }
                tag_df = pd.DataFrame(
                    {"Tag": list(counts.keys()), "Faltante en N recursos": list(counts.values())}
                ).sort_values("Faltante en N recursos", ascending=True)
                fig = px.bar(
                    tag_df,
                    x="Faltante en N recursos",
                    y="Tag",
                    orientation="h",
                    color_discrete_sequence=[COLOR_WARN],
                )
                fig.update_layout(
                    height=240,
                    margin=dict(l=10, r=10, t=10, b=10),
                    yaxis_title=None,
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            empty_state("Sin datos de cumplimiento")

    st.divider()

    st.markdown("**Recursos con Tags Incompletos**")
    if tags_cump is not None and not tags_cump.empty:
        if "tagsCompletos" in tags_cump.columns:
            mask_completos = to_bool_series(tags_cump["tagsCompletos"])
            faltantes_df = tags_cump[~mask_completos]
            if not faltantes_df.empty:
                cols_show = [c for c in ["resourceGroup", "name", "type", "location",
                                          "tagsFaltantes", "environment", "owner"]
                             if c in faltantes_df.columns]
                st.dataframe(faltantes_df[cols_show], use_container_width=True,
                             height=350, hide_index=True)
            else:
                callout("Todos los recursos tienen los tags obligatorios completos.", kind="success")
    else:
        empty_state("Sin datos")

    if tags_val is not None and not tags_val.empty:
        section_header("Tags con formato inválido")
        st.caption("Tags presentes pero que no cumplen el patrón del estándar (CC-####, regex de email, catálogos cerrados)")
        st.dataframe(tags_val, use_container_width=True, hide_index=True)

# ----------------------------------------------------------------------------
# TAB: FINOPS
# ----------------------------------------------------------------------------
with tab_fin:
    callout("Recursos ociosos generan factura mensual sin aportar valor. Esta sección detecta discos huérfanos, IPs sueltas, NICs sin VM, VMs apagadas (que aún cobran disco) y snapshots viejos.", kind="info")
    section_header("Recursos Ociosos (Waste)")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Discos no asociados", safe_len(discos_orf))
    c2.metric("Public IPs huérfanas", safe_len(ips_huerf))
    c3.metric("NICs sin VM", safe_len(nics_orf))
    c4.metric("VMs apagadas", safe_len(vms_off))
    c5.metric("Snapshots antiguos", safe_len(snaps_old))

    total_waste = (safe_len(discos_orf) + safe_len(ips_huerf) + safe_len(nics_orf)
                   + safe_len(vms_off) + safe_len(snaps_old))
    if total_waste == 0:
        callout("No se detectaron recursos ociosos en este snapshot.", kind="success")
    else:
        # Total GB en discos / snapshots
        total_gb = 0
        if discos_orf is not None and "sizeGB" in discos_orf.columns:
            total_gb += discos_orf["sizeGB"].sum()
        if snaps_old is not None and "sizeGB" in snaps_old.columns:
            total_gb += snaps_old["sizeGB"].sum()
        if total_gb > 0:
            callout(f"Total de almacenamiento ocioso (discos + snapshots): <strong>{int(total_gb):,} GB</strong>", kind="info")

    st.divider()

    def show_waste_section(title: str, df, key_cols: list):
        if df is None or df.empty:
            return
        section_header(f"{title} ({len(df)})")
        cols_show = [c for c in key_cols if c in df.columns]
        st.dataframe(df[cols_show], use_container_width=True, hide_index=True)

    show_waste_section(
        "Discos no asociados",
        discos_orf,
        ["resourceGroup", "name", "sizeGB", "skuName", "antiguedadDias",
         "environment", "owner", "costCenter"],
    )

    show_waste_section(
        "Public IPs huérfanas",
        ips_huerf,
        ["resourceGroup", "name", "skuName", "metodo", "ip", "environment", "owner"],
    )

    show_waste_section(
        "NICs sin VM asociada",
        nics_orf,
        ["resourceGroup", "name", "location", "privateIp", "environment", "owner"],
    )

    show_waste_section(
        "VMs apagadas (siguen cobrando recursos)",
        vms_off,
        ["resourceGroup", "name", "vmSize", "powerState", "environment",
         "criticality", "owner"],
    )

    show_waste_section(
        "Snapshots con más de 90 días",
        snaps_old,
        ["resourceGroup", "name", "sizeGB", "antiguedadDias", "environment", "owner"],
    )

# ----------------------------------------------------------------------------
# TAB: SEGURIDAD
# ----------------------------------------------------------------------------
with tab_sec:
    callout("La exposición directa a Internet es el principal vector de ataque. Esta sección identifica reglas de firewall demasiado permisivas y máquinas expuestas sin protección intermedia. Generalmente son los hallazgos más urgentes.", kind="info")
    section_header("Hallazgos de Seguridad")

    cA, cB = st.columns(2)
    cA.metric("Reglas NSG permisivas (Inbound desde Internet)", safe_len(nsgs))
    cB.metric("VMs con IP pública directa", safe_len(vms_pub))

    st.divider()

    section_header("Reglas NSG permisivas")
    st.caption("Reglas que permiten tráfico Inbound desde *, 0.0.0.0/0, Internet o Any a puertos sensibles (SSH, RDP, SQL, MySQL, PG, Redis, Mongo, WinRM, *).")
    if nsgs is not None and not nsgs.empty:
        # Codificar criticidad por puerto
        def criticidad(port):
            critical_ports = {"22": "CRÍTICO - SSH",
                              "3389": "CRÍTICO - RDP",
                              "1433": "CRÍTICO - SQL Server",
                              "3306": "CRÍTICO - MySQL",
                              "5432": "CRÍTICO - PostgreSQL",
                              "6379": "CRÍTICO - Redis",
                              "27017": "CRÍTICO - MongoDB",
                              "5985": "ALTO - WinRM",
                              "5986": "ALTO - WinRM HTTPS",
                              "*": "CRÍTICO - Todos los puertos"}
            return critical_ports.get(str(port), "MEDIO")

        nsgs_display = nsgs.copy()
        if "destinationPortRange" in nsgs_display.columns:
            nsgs_display["criticidad"] = nsgs_display["destinationPortRange"].apply(criticidad)

        cols_show = [c for c in ["criticidad", "resourceGroup", "nsgName", "ruleName",
                                  "priority", "protocol", "sourceAddressPrefix",
                                  "destinationPortRange", "environment", "owner"]
                     if c in nsgs_display.columns]
        st.dataframe(nsgs_display[cols_show], use_container_width=True, hide_index=True)
    else:
        callout("No se detectaron reglas NSG permisivas.", kind="success")

    section_header("VMs con IP pública directa")
    st.caption("Recomendación: las VMs deben estar detrás de Load Balancer, Bastion o ExpressRoute.")
    if vms_pub is not None and not vms_pub.empty:
        cols_show = [c for c in ["resourceGroup", "vmName", "location",
                                  "environment", "criticality", "owner", "costCenter"]
                     if c in vms_pub.columns]
        st.dataframe(vms_pub[cols_show], use_container_width=True, hide_index=True)
    else:
        callout("Ninguna VM tiene IP pública directa.", kind="success")

    # Storage accounts con acceso público
    if storages is not None and not storages.empty:
        st.divider()
        section_header("Storage Accounts con acceso público")
        if "publicBlobAccess" in storages.columns:
            public_storages = storages[to_bool_series(storages["publicBlobAccess"])]
            if not public_storages.empty:
                cols_show = [c for c in ["resourceGroup", "name", "location",
                                          "publicBlobAccess", "publicNetworkAccess",
                                          "httpsOnly", "minTlsVersion",
                                          "environment", "owner"]
                             if c in public_storages.columns]
                st.dataframe(public_storages[cols_show], use_container_width=True, hide_index=True)
            else:
                callout("Ningún Storage Account permite acceso público a blobs.", kind="success")

# ----------------------------------------------------------------------------
# TAB: GOBIERNO
# ----------------------------------------------------------------------------
with tab_gov:
    callout("Azure Policy define reglas automáticas de gobierno (ubicaciones permitidas, SKUs autorizados, tags obligatorios, etc.). La meta del estándar es 90% de cumplimiento.", kind="info")
    section_header("Cumplimiento de Azure Policy")
    if policy is not None and not policy.empty:
        cA, cB = st.columns([2, 3])

        with cA:
            avg = policy["CumplimientoPct"].mean()
            fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=avg,
                number={"suffix": "%"},
                gauge={
                    "axis": {"range": [0, 100]},
                    "bar": {"color": COLOR_PRIMARY},
                    "steps": [
                        {"range": [0, 75], "color": "#fde7e9"},
                        {"range": [75, 90], "color": "#fff4ce"},
                        {"range": [90, 100], "color": "#dff6dd"},
                    ],
                    "threshold": {
                        "line": {"color": COLOR_OK, "width": 4},
                        "thickness": 0.75,
                        "value": 90,
                    },
                },
                title={"text": "Cumplimiento promedio"},
            ))
            fig.update_layout(height=300, margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(fig, use_container_width=True)

        with cB:
            fig = px.bar(
                policy.sort_values("CumplimientoPct"),
                x="CumplimientoPct",
                y="subscriptionName",
                orientation="h",
                color="CumplimientoPct",
                color_continuous_scale=[
                    [0, COLOR_DANGER], [0.75, COLOR_WARN], [0.90, COLOR_OK], [1, COLOR_OK]
                ],
                range_color=[0, 100],
                text="CumplimientoPct",
            )
            fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            fig.add_vline(x=90, line_dash="dash", line_color=COLOR_OK)
            fig.update_layout(
                height=300,
                xaxis_title="Cumplimiento (%)",
                yaxis_title=None,
                xaxis_range=[0, 110],
                coloraxis_showscale=False,
                margin=dict(l=10, r=10, t=30, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)

        st.dataframe(policy, use_container_width=True, hide_index=True)
    else:
        empty_state("Sin datos de Policy Compliance. ¿El cliente tiene asignaciones de Azure Policy?")


# ----------------------------------------------------------------------------
# TAB: COSTOS (historial cliente / importes MXN con filtros dinámicos)
# ----------------------------------------------------------------------------
with tab_costs:
    BILLING_CUT_DESCRIPTION = "Corte PROTG: del 24 al 23 de cada mes"

    section_header("Costos", "Historial, comparativa y filtros dinámicos de importes en MXN")

    if cost_history is None:
        empty_state(
            f"No se encontró el archivo {COST_DYNAMIC_FILENAME} en la carpeta csv/ del snapshot seleccionado. "
            "Este archivo es obligatorio para usar filtros por suscripción, Resource Group, servicio y periodo."
        )
        st.code(str(csv_path / COST_DYNAMIC_FILENAME), language="text")
    elif cost_history.empty:
        empty_state("El archivo de costos existe, pero no contiene registros.")
    else:
        costs = cost_history.copy()

        # ================================================================
        # Normalización para portal cliente
        # ================================================================
        # El portal cliente solo debe mostrar importes finales en MXN.
        # Si el CSV todavía trae costo base, se usa únicamente para calcular
        # internamente y después se oculta.
        if "ImporteMXN" in costs.columns:
            costs["ImporteMXN"] = pd.to_numeric(costs["ImporteMXN"], errors="coerce").fillna(0)
        elif "CostMXN" in costs.columns:
            costs["ImporteMXN"] = pd.to_numeric(costs["CostMXN"], errors="coerce").fillna(0)
        elif "Cost" in costs.columns:
            INTERNAL_EXCHANGE_RATE = 22
            INTERNAL_CUSTOMER_FACTOR = 1.15
            costs["ImporteMXN"] = (
                pd.to_numeric(costs["Cost"], errors="coerce").fillna(0)
                * INTERNAL_EXCHANGE_RATE
                * INTERNAL_CUSTOMER_FACTOR
            )
        else:
            st.error(
                "El archivo de costos no contiene una columna válida de importe. "
                "Debe traer ImporteMXN, CostMXN o Cost."
            )
            st.stop()

        # Normalizar nombres de columnas para soportar distintos CSVs
        rename_candidates = {
            "ServiceName": "Servicio",
            "serviceName": "Servicio",
            "service_name": "Servicio",
            "ResourceGroupName": "ResourceGroup",
            "resourceGroupName": "ResourceGroup",
            "resourceGroup": "ResourceGroup",
            "resource_group": "ResourceGroup",
            "SubscriptionName": "Suscripcion",
            "subscriptionName": "Suscripcion",
            "subscription_name": "Suscripcion",
            "SubscriptionId": "SubscriptionId",
            "subscriptionId": "SubscriptionId",
            "subscription_id": "SubscriptionId",
        }
        costs = costs.rename(columns={k: v for k, v in rename_candidates.items() if k in costs.columns})

        if "Servicio" not in costs.columns:
            st.error("El CSV de costos no contiene columna de servicio: ServiceName / Servicio.")
            st.dataframe(costs.head(20), use_container_width=True, hide_index=True)
            st.stop()

        costs["Servicio"] = costs["Servicio"].fillna("Sin servicio").astype(str)

        if "ResourceGroup" not in costs.columns:
            costs["ResourceGroup"] = "Sin dato"
        else:
            costs["ResourceGroup"] = costs["ResourceGroup"].fillna("Sin dato").replace("", "Sin dato").astype(str)

        if "Suscripcion" not in costs.columns:
            if "SubscriptionId" in costs.columns:
                costs["Suscripcion"] = costs["SubscriptionId"].fillna("Sin dato").astype(str)
            else:
                costs["Suscripcion"] = "Cliente completo"
        else:
            costs["Suscripcion"] = costs["Suscripcion"].fillna("Sin dato").replace("", "Sin dato").astype(str)

        if "PeriodStart" in costs.columns:
            costs["PeriodStart"] = pd.to_datetime(costs["PeriodStart"], errors="coerce")
        elif "UsageDate" in costs.columns:
            costs["PeriodStart"] = pd.to_datetime(costs["UsageDate"], errors="coerce")
        else:
            st.error("El CSV de costos no contiene fecha de periodo/corte: UsageDate o PeriodStart.")
            st.dataframe(costs.head(20), use_container_width=True, hide_index=True)
            st.stop()

        if "PeriodEnd" in costs.columns:
            costs["PeriodEnd"] = pd.to_datetime(costs["PeriodEnd"], errors="coerce")
        else:
            costs["PeriodEnd"] = costs["PeriodStart"] + pd.offsets.MonthEnd(0)

        costs = costs.dropna(subset=["PeriodStart"])
        if costs.empty:
            empty_state("No hay periodos válidos para mostrar en la sección de costos.")
            st.stop()

        if "CorteLabel" not in costs.columns:
            costs["CorteLabel"] = costs["PeriodStart"].dt.strftime("%b %Y")
        else:
            costs["CorteLabel"] = costs["CorteLabel"].astype(str)

        if "CorteStatus" not in costs.columns:
            costs["CorteStatus"] = ""
        else:
            costs["CorteStatus"] = costs["CorteStatus"].fillna("").astype(str)

        costs["PeriodOrder"] = costs["PeriodStart"]

        # Nunca mostrar columnas base/comerciales en el portal cliente
        hidden_columns = [
            "Cost", "Currency", "CostMXN", "ExchangeRate", "Factor", "TipoCambio",
            "PrecioBase", "BaseCost", "UnitPrice", "PretaxCost", "PreTaxCost",
        ]
        costs = costs.drop(columns=[c for c in hidden_columns if c in costs.columns], errors="ignore")

        # ================================================================
        # Filtros dinámicos
        # ================================================================
        callout(
            "Usa los filtros para analizar el consumo por suscripción, resource group, servicio o periodo. "
            "Los importes mostrados corresponden a valores finales en MXN.",
            kind="info",
        )
        st.caption(f"Fuente de costos cargada: {COST_DYNAMIC_FILENAME}")

        st.markdown("### Filtros")
        f1, f2, f3, f4 = st.columns(4)

        with f1:
            suscripciones = ["Todas"] + sorted(costs["Suscripcion"].dropna().unique().tolist())
            selected_sub = st.selectbox("Suscripción", suscripciones, key="cost_filter_subscription")

        sub_filtered_for_rg = costs.copy()
        if selected_sub != "Todas":
            sub_filtered_for_rg = sub_filtered_for_rg[sub_filtered_for_rg["Suscripcion"] == selected_sub]

        with f2:
            rgs = ["Todos"] + sorted(sub_filtered_for_rg["ResourceGroup"].dropna().unique().tolist())
            selected_rg = st.selectbox("Resource Group", rgs, key="cost_filter_rg")

        rg_filtered_for_service = sub_filtered_for_rg.copy()
        if selected_rg != "Todos":
            rg_filtered_for_service = rg_filtered_for_service[rg_filtered_for_service["ResourceGroup"] == selected_rg]

        with f3:
            servicios = ["Todos"] + sorted(rg_filtered_for_service["Servicio"].dropna().unique().tolist())
            selected_service = st.selectbox("Servicio", servicios, key="cost_filter_service")

        with f4:
            periodos_df = costs[["PeriodOrder", "CorteLabel"]].drop_duplicates().sort_values("PeriodOrder", ascending=False)
            periodos = ["Todos"] + periodos_df["CorteLabel"].tolist()
            selected_period = st.selectbox("Periodo", periodos, key="cost_filter_period")

        filtered_costs = costs.copy()
        if selected_sub != "Todas":
            filtered_costs = filtered_costs[filtered_costs["Suscripcion"] == selected_sub]
        if selected_rg != "Todos":
            filtered_costs = filtered_costs[filtered_costs["ResourceGroup"] == selected_rg]
        if selected_service != "Todos":
            filtered_costs = filtered_costs[filtered_costs["Servicio"] == selected_service]
        if selected_period != "Todos":
            filtered_costs = filtered_costs[filtered_costs["CorteLabel"] == selected_period]

        if filtered_costs.empty:
            empty_state("No hay datos de costos para los filtros seleccionados.")
            st.stop()

        # ================================================================
        # KPIs
        # ================================================================
        monthly = (
            filtered_costs.groupby(["PeriodOrder", "CorteLabel", "CorteStatus"], as_index=False)
            .agg(ImporteMXN=("ImporteMXN", "sum"))
            .sort_values("PeriodOrder")
        )
        monthly["VariacionMXN"] = monthly["ImporteMXN"].diff()
        monthly["VariacionPct"] = monthly["ImporteMXN"].pct_change() * 100

        total_mxn = monthly["ImporteMXN"].sum()
        latest = monthly.iloc[-1]
        previous = monthly.iloc[-2] if len(monthly) >= 2 else None

        delta_value = None
        if previous is not None:
            delta_abs = latest["ImporteMXN"] - previous["ImporteMXN"]
            delta_pct = (delta_abs / previous["ImporteMXN"] * 100) if previous["ImporteMXN"] else 0
            delta_value = f"${delta_abs:+,.2f} MXN ({delta_pct:+.1f}%)"

        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.metric("Importe acumulado", f"${total_mxn:,.2f} MXN")
        with k2:
            st.metric(
                "Último periodo",
                f"${latest['ImporteMXN']:,.2f} MXN",
                delta=delta_value,
                delta_color="inverse",
            )
        with k3:
            st.metric("Servicios", filtered_costs["Servicio"].nunique())
        with k4:
            st.metric("Resource Groups", filtered_costs["ResourceGroup"].nunique())

        st.caption(f"{BILLING_CUT_DESCRIPTION}. Importes expresados únicamente en MXN.")
        st.divider()

        # ================================================================
        # Gráficas principales
        # ================================================================
        cA, cB = st.columns([2, 1])

        with cA:
            st.markdown("### Evolución del gasto")
            fig = px.line(
                monthly,
                x="CorteLabel",
                y="ImporteMXN",
                markers=True,
                text=monthly["ImporteMXN"].map(lambda x: f"${x:,.0f}"),
                color_discrete_sequence=[COLOR_PRIMARY],
            )
            fig.update_traces(textposition="top center")
            fig.update_layout(
                height=380,
                xaxis_title="Periodo",
                yaxis_title="Importe (MXN)",
                margin=dict(l=10, r=10, t=30, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)

        with cB:
            st.markdown("### Comparativa")
            monthly_display = monthly.copy()
            monthly_display["Importe"] = monthly_display["ImporteMXN"].map(lambda x: f"${x:,.2f} MXN")
            monthly_display["Variación"] = monthly_display["VariacionMXN"].map(
                lambda x: "—" if pd.isna(x) else f"${x:+,.2f} MXN"
            )
            monthly_display["Variación %"] = monthly_display["VariacionPct"].map(
                lambda x: "—" if pd.isna(x) else f"{x:+.1f}%"
            )
            monthly_display = monthly_display.rename(columns={"CorteLabel": "Periodo", "CorteStatus": "Estado"})
            display_cols = ["Periodo", "Importe", "Variación", "Variación %"]
            if monthly_display["Estado"].astype(str).str.strip().any():
                display_cols.insert(1, "Estado")
            st.dataframe(monthly_display[display_cols], use_container_width=True, hide_index=True)

        st.divider()

        c1, c2 = st.columns(2)

        with c1:
            st.markdown("### Distribución por servicio")
            service_period = (
                filtered_costs.groupby(["PeriodOrder", "CorteLabel", "Servicio"], as_index=False)["ImporteMXN"]
                .sum()
                .sort_values(["PeriodOrder", "ImporteMXN"], ascending=[True, False])
            )
            fig = px.bar(
                service_period,
                x="CorteLabel",
                y="ImporteMXN",
                color="Servicio",
                barmode="stack",
            )
            fig.update_layout(
                height=460,
                xaxis_title="Periodo",
                yaxis_title="Importe (MXN)",
                legend_title="Servicio",
                margin=dict(l=10, r=10, t=30, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)

        with c2:
            st.markdown("### Top servicios por costo acumulado")
            top_services = (
                filtered_costs.groupby("Servicio", as_index=False)
                .agg(ImporteMXN=("ImporteMXN", "sum"))
                .sort_values("ImporteMXN", ascending=False)
            )
            fig = px.bar(
                top_services.head(10).sort_values("ImporteMXN"),
                x="ImporteMXN",
                y="Servicio",
                orientation="h",
                text="ImporteMXN",
                color_discrete_sequence=[COLOR_PRIMARY],
            )
            fig.update_traces(texttemplate="$%{text:,.0f}", textposition="outside")
            fig.update_layout(
                height=460,
                xaxis_title="Importe acumulado (MXN)",
                yaxis_title=None,
                margin=dict(l=10, r=30, t=30, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)

        st.divider()

        c3, c4 = st.columns(2)

        with c3:
            st.markdown("### Top Resource Groups")
            rg_totals = (
                filtered_costs.groupby("ResourceGroup", as_index=False)
                .agg(ImporteMXN=("ImporteMXN", "sum"))
                .sort_values("ImporteMXN", ascending=False)
            )
            fig = px.bar(
                rg_totals.head(10).sort_values("ImporteMXN"),
                x="ImporteMXN",
                y="ResourceGroup",
                orientation="h",
                text="ImporteMXN",
                color_discrete_sequence=[COLOR_PRIMARY],
            )
            fig.update_traces(texttemplate="$%{text:,.0f}", textposition="outside")
            fig.update_layout(
                height=430,
                xaxis_title="Importe acumulado (MXN)",
                yaxis_title=None,
                margin=dict(l=10, r=30, t=30, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)

        with c4:
            st.markdown("### Distribución por suscripción")
            sub_totals = (
                filtered_costs.groupby("Suscripcion", as_index=False)
                .agg(ImporteMXN=("ImporteMXN", "sum"))
                .sort_values("ImporteMXN", ascending=False)
            )
            fig = px.pie(
                sub_totals,
                values="ImporteMXN",
                names="Suscripcion",
                hole=0.55,
            )
            fig.update_traces(textposition="outside", textinfo="label+percent")
            fig.update_layout(height=430, showlegend=False, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig, use_container_width=True)

        st.divider()

        section_header("Servicios que más cambiaron", "Comparación entre el último periodo y el anterior con los filtros aplicados")
        if len(monthly) >= 2:
            last_period = monthly["PeriodOrder"].max()
            prev_period = monthly["PeriodOrder"].sort_values().iloc[-2]
            last_label = monthly.loc[monthly["PeriodOrder"] == last_period, "CorteLabel"].iloc[0]
            prev_label = monthly.loc[monthly["PeriodOrder"] == prev_period, "CorteLabel"].iloc[0]

            pivot = (
                filtered_costs[filtered_costs["PeriodOrder"].isin([prev_period, last_period])]
                .groupby(["Servicio", "PeriodOrder"], as_index=False)["ImporteMXN"]
                .sum()
                .pivot(index="Servicio", columns="PeriodOrder", values="ImporteMXN")
                .fillna(0)
                .reset_index()
            )
            pivot["CambioMXN"] = pivot[last_period] - pivot[prev_period]
            pivot["CambioPct"] = pivot.apply(
                lambda r: (r["CambioMXN"] / r[prev_period] * 100) if r[prev_period] else 0,
                axis=1,
            )
            pivot_display = pivot.sort_values("CambioMXN", ascending=False).copy()
            pivot_display = pivot_display.rename(columns={prev_period: prev_label, last_period: last_label})
            pivot_display[prev_label] = pivot_display[prev_label].map(lambda x: f"${x:,.2f} MXN")
            pivot_display[last_label] = pivot_display[last_label].map(lambda x: f"${x:,.2f} MXN")
            pivot_display["Cambio"] = pivot_display["CambioMXN"].map(lambda x: f"${x:+,.2f} MXN")
            pivot_display["Cambio %"] = pivot_display["CambioPct"].map(lambda x: f"{x:+.1f}%")
            st.dataframe(
                pivot_display[["Servicio", prev_label, last_label, "Cambio", "Cambio %"]],
                use_container_width=True,
                hide_index=True,
            )
        else:
            empty_state("Se necesita al menos dos periodos para calcular variaciones por servicio.")

        st.divider()

        section_header("Detalle histórico filtrado")
        detail_cols = [
            "CorteLabel", "CorteStatus", "PeriodStart", "PeriodEnd", "Suscripcion",
            "ResourceGroup", "Servicio", "ImporteMXN",
        ]
        detail_cols = [c for c in detail_cols if c in filtered_costs.columns]
        detail = filtered_costs[detail_cols].copy().sort_values(
            ["PeriodStart", "ImporteMXN"], ascending=[False, False]
        )
        detail = detail.rename(columns={
            "CorteLabel": "Periodo",
            "CorteStatus": "Estado",
            "PeriodStart": "Inicio",
            "PeriodEnd": "Fin",
            "Suscripcion": "Suscripción",
            "ResourceGroup": "Resource Group",
            "ImporteMXN": "Importe MXN",
        })
        detail["Importe MXN"] = detail["Importe MXN"].map(lambda x: f"${x:,.2f} MXN")
        st.dataframe(detail, use_container_width=True, hide_index=True)

# ----------------------------------------------------------------------------
# TAB: DATOS POR TIPO (VMs, Apps, SQL, Storage, AKS)
# ----------------------------------------------------------------------------
with tab_data:
    callout("Vista de deep-dive operativo: tamaños de VM, versiones de Kubernetes, configuración de Storage, etc. Útil cuando ya se identificó un problema y se requiere el detalle técnico.", kind="info")
    section_header("Detalle por Tipo de Recurso")

    sub_tabs = st.tabs(["VMs", "App Services", "Azure SQL", "Storage Accounts", "AKS"])

    with sub_tabs[0]:
        if vms is not None and not vms.empty:
            st.markdown(f"**{len(vms)} máquinas virtuales**")
            st.dataframe(vms, use_container_width=True, hide_index=True)
            if "vmSize" in vms.columns:
                st.markdown("**Distribución por tamaño**")
                size_count = vms["vmSize"].value_counts().reset_index()
                size_count.columns = ["vmSize", "Cantidad"]
                fig = px.bar(size_count, x="vmSize", y="Cantidad",
                             color_discrete_sequence=[COLOR_PRIMARY])
                fig.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig, use_container_width=True)
        else:
            empty_state("No hay VMs")

    with sub_tabs[1]:
        if apps is not None and not apps.empty:
            st.markdown(f"**{len(apps)} App Services**")
            st.dataframe(apps, use_container_width=True, hide_index=True)
            # Mostrar los que no tienen HTTPS only
            if "httpsOnly" in apps.columns:
                sin_https = apps[~to_bool_series(apps["httpsOnly"])]
                if not sin_https.empty:
                    callout(f"{len(sin_https)} App Service(s) sin HTTPS Only forzado.", kind="warning")
        else:
            empty_state("No hay App Services")

    with sub_tabs[2]:
        if sqls is not None and not sqls.empty:
            st.markdown(f"**{len(sqls)} bases Azure SQL**")
            st.dataframe(sqls, use_container_width=True, hide_index=True)
        else:
            empty_state("No hay bases Azure SQL")

    with sub_tabs[3]:
        if storages is not None and not storages.empty:
            st.markdown(f"**{len(storages)} Storage Accounts**")
            st.dataframe(storages, use_container_width=True, hide_index=True)
        else:
            empty_state("No hay Storage Accounts")

    with sub_tabs[4]:
        if aks is not None and not aks.empty:
            st.markdown(f"**{len(aks)} clusters AKS**")
            st.dataframe(aks, use_container_width=True, hide_index=True)
        else:
            empty_state("No hay clusters AKS")

# ----------------------------------------------------------------------------
# TAB: TENDENCIAS (multi-snapshot)
# ----------------------------------------------------------------------------
with tab_trend:
    callout("Evolución del entorno snapshot a snapshot: crecimiento, mejoras en cobertura de tags, hallazgos remediados o nuevos. Requiere al menos 2 corridas del runner.", kind="info")
    section_header("Tendencias entre Snapshots")
    st.caption("Compara la evolución del entorno acumulando varias ejecuciones del runner.")

    if len(snapshots) < 2:
        st.info("ℹ️ Necesitas al menos 2 snapshots para ver tendencias. "
                f"Actualmente tienes 1 snapshot para `{client}`.")
    else:
        # Agregar metricas de cada snapshot
        trend_data = []
        for snap in sorted(snapshots):
            snap_csv = client_path / snap / "csv"
            if not snap_csv.exists():
                continue
            inv = load_csv(snap_csv, "01-inventario-maestro.csv")
            cob = load_csv(snap_csv, "02-cobertura-por-suscripcion.csv")
            d_orf = load_csv(snap_csv, "01-discos-no-asociados.csv")
            i_huer = load_csv(snap_csv, "02-public-ips-huerfanas.csv")
            n_orf = load_csv(snap_csv, "03-nics-sin-vm.csv")
            v_off = load_csv(snap_csv, "04-vms-apagadas.csv")
            s_old = load_csv(snap_csv, "05-snapshots-antiguos.csv")
            nsg_data = load_csv(snap_csv, "01-nsgs-reglas-permisivas.csv")
            pub_vms = load_csv(snap_csv, "02-vms-con-ip-publica.csv")

            trend_data.append({
                "snapshot": snap,
                "recursos": safe_len(inv),
                "cobertura_tags": (cob["CoberturaPct"].mean()
                                   if cob is not None and not cob.empty
                                   and "CoberturaPct" in cob.columns else 0),
                "waste": (safe_len(d_orf) + safe_len(i_huer) + safe_len(n_orf)
                          + safe_len(v_off) + safe_len(s_old)),
                "seguridad": safe_len(nsg_data) + safe_len(pub_vms),
            })

        if trend_data:
            trend_df = pd.DataFrame(trend_data)

            c1, c2 = st.columns(2)
            with c1:
                fig = px.line(trend_df, x="snapshot", y="recursos",
                              markers=True, title="Total de recursos",
                              color_discrete_sequence=[COLOR_PRIMARY])
                fig.update_layout(height=300, margin=dict(l=10, r=10, t=40, b=10))
                st.plotly_chart(fig, use_container_width=True)

                fig = px.line(trend_df, x="snapshot", y="cobertura_tags",
                              markers=True, title="Cobertura de tags (%)",
                              color_discrete_sequence=[COLOR_OK])
                fig.update_layout(height=300, margin=dict(l=10, r=10, t=40, b=10),
                                  yaxis_range=[0, 105])
                fig.add_hline(y=95, line_dash="dash", line_color=COLOR_NEUTRAL)
                st.plotly_chart(fig, use_container_width=True)

            with c2:
                fig = px.line(trend_df, x="snapshot", y="waste",
                              markers=True, title="Recursos huérfanos (waste)",
                              color_discrete_sequence=[COLOR_WARN])
                fig.update_layout(height=300, margin=dict(l=10, r=10, t=40, b=10))
                st.plotly_chart(fig, use_container_width=True)

                fig = px.line(trend_df, x="snapshot", y="seguridad",
                              markers=True, title="Hallazgos de seguridad",
                              color_discrete_sequence=[COLOR_DANGER])
                fig.update_layout(height=300, margin=dict(l=10, r=10, t=40, b=10))
                st.plotly_chart(fig, use_container_width=True)

            st.dataframe(trend_df, use_container_width=True, hide_index=True)

# ============================================================================
# FOOTER
# ============================================================================
st.divider()
st.markdown(
    f'<div style="text-align: center; color: #9CA3AF; font-size: 0.8rem; padding: 8px 0;">'
    f'C&A Systems &middot; Azure Inventory Dashboard &middot; '
    f'Cliente: <strong>{client}</strong> &middot; Snapshot: <code>{snapshot}</code>'
    f'</div>',
    unsafe_allow_html=True,
)