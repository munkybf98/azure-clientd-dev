# Consultas Azure Resource Graph — Práctica Integral Azure (C&A Systems)

Set inicial de **20 consultas KQL** diseñadas para correr contra el tenant del cliente con permisos **solo lectura** (rol Reader). Ninguna consulta crea, modifica ni elimina recursos en el entorno del cliente.

## Estructura

```
queries/
├── 01-inventario/          Visibilidad y control (Nivel 1)
├── 02-etiquetado/          Estándar de Tags (los 6 obligatorios)
├── 03-finops-waste/        Recursos ociosos / FinOps (Nivel 3)
├── 04-monitoreo-recursos/  Matriz de monitoreo por tipo (VM, App, SQL, Storage, AKS)
├── 05-seguridad/           Gobierno y seguridad (Nivel 4)
└── 06-gobierno/            Azure Policy compliance
```

## Mapeo al documento estándar

| Sección del estándar | Consulta(s) | KPI cubierto |
|---|---|---|
| Reporte de Inventario (onboarding) | `01-inventario/*` | Visibilidad completa |
| Estándar de Etiquetado (6 tags) | `02-etiquetado/01-cumplimiento-tags-obligatorios` | Cobertura tags ≥ 95% |
| Formato CC-#### y catálogos cerrados | `02-etiquetado/03-validacion-formato-tags` | Calidad de tags |
| Reporte Mensual FinOps — waste | `03-finops-waste/*` | Recursos ociosos ≥ 80% resueltos en 60d |
| Matriz de Monitoreo NOC | `04-monitoreo-recursos/*` | Disponibilidad Tier1 ≥ 99.5% |
| Seguridad / hallazgos críticos | `05-seguridad/*` | Secure Score ≥ 70% |
| Reporte de Gobernanza y Cumplimiento | `06-gobierno/01-azure-policy-compliance` | Cumplimiento Policy ≥ 90% |

## Cómo ejecutar

### Opción 0 — Runner automatizado (ejecuta TODO de un jalón)

Si solo quieres correr las 20 consultas y obtener JSON + CSV organizados:

```powershell
.\Run-AzureGraphQueries.ps1 -TenantId "<tenant-del-cliente>" -ClientName "ACME"
```

Genera la carpeta `resultados/ACME/YYYY-MM-DD_HHMM/` con subcarpetas `json/` y `csv/`, además de un `_resumen.json` con métricas de la ejecución. Ver **`RUNNER.md`** para todos los detalles, troubleshooting y cómo automatizarlo con tarea programada.

### Opción A — Azure CLI (recomendado para pruebas rápidas)

```bash
# Login al tenant del cliente con tu cuenta o Service Principal
az login --tenant <tenant-id-del-cliente>

# Ejecutar una consulta
az graph query -q "$(cat queries/01-inventario/01-inventario-maestro.kql)" \
  --first 1000 \
  --output json > resultados/$(date +%Y-%m-%d)-inventario-maestro.json
```

### Opción B — PowerShell (recomendado para automatizar)

```powershell
# Instalar una vez
Install-Module Az.ResourceGraph -Scope CurrentUser

# Login con Service Principal
Connect-AzAccount -ServicePrincipal -TenantId <tenant-id> -Credential $cred

# Ejecutar
$query = Get-Content -Raw queries/01-inventario/01-inventario-maestro.kql
$result = Search-AzGraph -Query $query -First 1000 -UseTenantScope
$result | Export-Csv -NoTypeInformation "resultados/$(Get-Date -f yyyy-MM-dd)-inventario-maestro.csv"
```

### Opción C — Portal (solo manual, sin crear nada)

Abrir Resource Graph Explorer → pegar el contenido del .kql → Run → Download as CSV.

## Suscripciones múltiples

Por defecto las consultas corren sobre **todas las suscripciones visibles al usuario o SP**. Para limitar:

- CLI: agregar `--subscriptions <id1> <id2>`
- PowerShell: agregar `-Subscription <id1>, <id2>`

Para tenant root scope (recomendado en multicliente), el SP necesita rol **Reader en el Management Group raíz** del cliente.

## Notas importantes

1. **`properties.extended.instanceView` (powerState de VMs)** — para que se popule, ejecutar con `-AllowPartialScope` en PowerShell o `--allow-partial-scopes true` en CLI. Si no, las consultas de VMs apagadas devolverán filas con `powerState` vacío.
2. **Paginación** — `--first 1000` y `--first 5000` son los máximos. Si el cliente tiene más recursos, paginar con `--skip-token`.
3. **Tag Client** — la consulta `02-etiquetado/01` lo evalúa porque es multicliente según el estándar. Si la suscripción es de un solo cliente, comentar la línea correspondiente.
4. **Costos** — ARG **no incluye datos de costo**. Para eso se necesita la **Cost Management API** (`az consumption usage list` o el endpoint REST). Es una capa adicional que se complementa con estas consultas.
5. **PolicyResources** — la consulta `06-gobierno/01` requiere que el cliente tenga al menos una asignación de Azure Policy. Si no tienen ninguna, devuelve vacío (es información valiosa por sí misma).

## Histórico

Estas consultas devuelven el estado **actual**. Para construir tendencias:

1. Crear carpeta `resultados/YYYY-MM-DD/` por cada ejecución.
2. Guardar el JSON crudo de cada consulta dentro.
3. Tras 3–4 ejecuciones, comparar con un notebook o Power BI Desktop:
   - VMs creadas/eliminadas en la semana
   - Evolución de cobertura de tags
   - Crecimiento de recursos huérfanos (waste)
   - Recursos que aparecieron sin pasar por IaC

## Orden sugerido para el primer día

1. `01-inventario/01-inventario-maestro` → fotografía base
2. `02-etiquetado/02-cobertura-por-suscripcion` → KPI inmediato
3. `03-finops-waste/01-discos-no-asociados` → quick win visible
4. `05-seguridad/01-nsgs-reglas-permisivas` → impacto en seguridad
5. `06-gobierno/01-azure-policy-compliance` → estado de gobierno

Con estas 5 ya tienes material para una primera conversación seria con el cliente.
