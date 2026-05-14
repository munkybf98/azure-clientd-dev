# Dashboard — Instalación y Uso (Mac)

Dashboard web interactivo que lee los resultados del runner ARG y los presenta unificados con KPIs, gráficos y tablas filtradas por categoría.

## Qué incluye

- **Resumen ejecutivo** con 6 KPIs: total recursos, suscripciones, cobertura tags, recursos huérfanos, hallazgos de seguridad, policy compliance.
- **Tab Inventario**: top 15 tipos de recursos, distribución por suscripción y región, inventario completo descargable.
- **Tab Tags**: cobertura por suscripción con meta del 95%, donut de cumplimiento, ranking de tags más ausentes, tabla de recursos no etiquetados.
- **Tab FinOps**: 5 tipos de waste (discos, IPs, NICs, VMs apagadas, snapshots viejos), con totales en GB cuando aplica.
- **Tab Seguridad**: reglas NSG permisivas con criticidad por puerto, VMs con IP pública, Storage Accounts con acceso público.
- **Tab Gobierno**: gauge de cumplimiento Azure Policy con meta del 90%.
- **Tab Datos por Tipo**: detalle de VMs, App Services, Azure SQL, Storage, AKS en sub-tabs.
- **Tab Tendencias**: gráficos de evolución cuando hay múltiples snapshots.

## Instalación (5 minutos, una sola vez)

### 1. Verifica que tienes Python 3

```bash
python3 --version
```

Debe decir 3.9 o superior. Si no lo tienes:
```bash
brew install python3
```

### 2. Crea un entorno virtual (recomendado)

```bash
cd ~/casystem
mkdir -p dashboard
cd dashboard

# Crear venv
python3 -m venv .venv
source .venv/bin/activate
```

Sabrás que está activo cuando tu prompt cambie a algo como `(.venv) usuario@mac dashboard %`.

### 3. Instala las dependencias

Con el venv activo:

```bash
pip install -r requirements.txt
```

Esto instala Streamlit, pandas y plotly. Tarda 1-2 minutos.

## Cómo ejecutarlo

Cada vez que quieras abrir el dashboard:

```bash
cd ~/casystem/dashboard
source .venv/bin/activate
streamlit run dashboard.py
```

El dashboard se abre **automáticamente en tu navegador** en `http://localhost:8501`. Si no, abre esa URL manualmente.

Para **detenerlo**: vuelve a la terminal y presiona `Ctrl + C`.

## Estructura de carpetas esperada

```
~/casystem/
├── queries/
│   ├── Run-AzureGraphQueries.ps1
│   └── resultados/
│       └── ProTG/
│           └── 2026-05-12_2203/
│               ├── _resumen.json
│               ├── csv/
│               └── json/
└── dashboard/
    ├── dashboard.py
    ├── requirements.txt
    └── .venv/
```

El dashboard busca la carpeta `resultados/` automáticamente en:
1. La carpeta actual
2. `../queries/resultados/` (recomendado)
3. `./queries/resultados/`

Si no la encuentra, puedes indicarle la ruta manualmente en el sidebar.

## Uso típico

1. **Cliente** (sidebar): elige el cliente — si ya corriste el runner para varios, todos aparecen.
2. **Snapshot** (sidebar): elige la fecha. Por defecto muestra el más reciente.
3. Navega por los tabs según lo que quieras revisar:
   - **Primera vez con un cliente**: empieza por "Inventario" para ver qué tienen.
   - **Para la junta del lunes**: "Resumen Ejecutivo" (arriba) + "Seguridad" + "FinOps".
   - **Para FinOps detallado**: tab "FinOps" tiene cada tipo de waste expandido.
4. **Recargar datos** (botón sidebar): cuando agregues snapshots nuevos sin reiniciar el dashboard.

## Atajos útiles

### Crear alias para arranque rápido

Agrega a tu `~/.zshrc`:

```bash
echo 'alias casystem-dash="cd ~/casystem/dashboard && source .venv/bin/activate && streamlit run dashboard.py"' >> ~/.zshrc
source ~/.zshrc
```

Después solo escribes `casystem-dash` en Terminal y arranca todo.

### Capturar el dashboard como PDF

Streamlit no exporta PDF nativamente, pero puedes:
1. Abrir el dashboard en el navegador
2. `Cmd + P` → "Save as PDF"
3. Listo para enviar al cliente

### Compartir con compañeros (LAN local)

Si quieres que otro compañero en tu red vea el dashboard:

```bash
streamlit run dashboard.py --server.address 0.0.0.0
```

Y comparte tu IP local. **No expongas esto a Internet**, los datos del cliente son sensibles.

## Troubleshooting

**"streamlit: command not found"**
El venv no está activo. Corre `source .venv/bin/activate` desde `~/casystem/dashboard/`.

**"No existe la carpeta resultados"**
El dashboard no encontró la carpeta automáticamente. En el sidebar, edita la ruta manualmente (puede ser una ruta absoluta tipo `/Users/tuusuario/casystem/queries/resultados`).

**"No hay snapshots para X cliente"**
La subcarpeta del cliente está vacía. Verifica que el runner haya generado al menos una corrida exitosa.

**El dashboard muestra "—" en todos los KPIs**
Los CSVs están vacíos o tienen el header `# Sin resultados`. Verifica que el runner haya devuelto datos con tu corrida más reciente.

**"Sin datos para mostrar" en algún tab**
Normal cuando una consulta devolvió 0 filas (por ejemplo, el cliente no tiene SQL ni AKS). Solo informativo, no es error.

## Flujo de trabajo diario sugerido

1. **Mañana** (5 min): `cd ~/casystem/queries && pwsh -c "Connect-AzAccount -TenantId '...'; ./Run-AzureGraphQueries.ps1 -ClientName ProTG -SkipAuth"`
2. **Mañana** (1 min): `casystem-dash` (con el alias). Revisa el dashboard, anota cambios respecto al día anterior.
3. **Viernes**: tab "Tendencias" para ver la evolución semanal.
4. **Mensual**: exporta a PDF y arma el reporte del servicio según tu estándar.

## Próximos pasos sugeridos

- **Conectar con Cost Management API** para sumar costos reales a cada categoría (necesita una capa adicional, que podemos armar después).
- **Alertas automatizadas**: si la cobertura de tags baja, o aparecen nuevas reglas NSG abiertas, enviar correo automáticamente.
- **Exportación a Excel** con formato (tablas dinámicas pre-armadas) para entrega ejecutiva.

Avísame qué quieres atacar después.
