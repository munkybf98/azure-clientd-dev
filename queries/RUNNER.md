# Runner — Ejecución de las consultas

Script PowerShell que ejecuta las 20 consultas KQL y deja los resultados en JSON y CSV con timestamp, organizados por cliente.

## Setup inicial (una sola vez por máquina)

```powershell
# Instalar módulos requeridos
Install-Module Az.Accounts -Scope CurrentUser -Force
Install-Module Az.ResourceGraph -Scope CurrentUser -Force
```

## Setup por cliente (una sola vez por tenant)

Crear un **Service Principal** en el tenant del cliente con rol **Reader** a nivel Management Group raíz:

```bash
# Esto lo hace el cliente o se hace en conjunto. NO crea recursos, solo
# una App Registration en Entra ID.
az ad sp create-for-rbac \
  --name "CASystem-ReadOnly-Inventory" \
  --role "Reader" \
  --scopes "/providers/Microsoft.Management/managementGroups/<MG-RAIZ-DEL-CLIENTE>"
```

Guarda con cuidado: `appId`, `password`, `tenant`. **El secret solo se muestra una vez.**

## Cómo correrlo

### Opción 1 — Login interactivo (más simple para empezar)

```powershell
.\Run-AzureGraphQueries.ps1 `
    -TenantId "11111111-2222-3333-4444-555555555555" `
    -ClientName "ACME"
```

Te abre el navegador para hacer login con MFA.

### Opción 2 — Con Service Principal (para automatizar)

```powershell
# Convertir el secret a SecureString (mejor: leer desde Key Vault o variable de entorno)
$sec = ConvertTo-SecureString $env:CLIENT_SP_SECRET -AsPlainText -Force

.\Run-AzureGraphQueries.ps1 `
    -TenantId "11111111-2222-3333-4444-555555555555" `
    -ClientName "ACME" `
    -UseServicePrincipal `
    -ApplicationId "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" `
    -ClientSecret $sec
```

### Opción 3 — Limitando a suscripciones específicas

```powershell
.\Run-AzureGraphQueries.ps1 `
    -TenantId "..." `
    -ClientName "ACME" `
    -SubscriptionIds @("sub-prod-id", "sub-qa-id")
```

### Opción 4 — Si ya hiciste `Connect-AzAccount` antes

```powershell
.\Run-AzureGraphQueries.ps1 -TenantId "..." -ClientName "ACME" -SkipAuth
```

## Estructura de salida

```
resultados/
└── ACME/
    └── 2026-05-12_1430/
        ├── _resumen.json           Estadísticas totales (filas, errores, duración)
        ├── _resumen.csv            Misma info en CSV (una fila por consulta)
        ├── ejecucion.log           Log secuencial de cada consulta
        ├── json/
        │   ├── 01-inventario-maestro.json
        │   ├── 02-resumen-por-tipo.json
        │   └── ...                 (20 archivos JSON)
        └── csv/
            ├── 01-inventario-maestro.csv
            ├── 02-resumen-por-tipo.csv
            └── ...                 (20 archivos CSV)
```

**Para histórico**: cada ejecución crea su propia carpeta con timestamp. Acumula varias y luego comparas con Power BI o un notebook.

## Qué hace el script en detalle

1. Valida módulos `Az.Accounts` y `Az.ResourceGraph` instalados.
2. Autentica en el tenant del cliente (SP o interactivo).
3. Lista las suscripciones visibles y muestra cuáles va a usar.
4. Crea la carpeta `resultados/<Cliente>/<Fecha_Hora>/`.
5. Recorre todos los `.kql` recursivamente en `queries/`.
6. Por cada consulta:
   - Lee el archivo.
   - Ejecuta con paginación (hasta 10,000 filas).
   - Usa `-AllowPartialScope` para que `powerState` de VMs se popule.
   - Guarda JSON crudo (con estructuras anidadas intactas).
   - Guarda CSV plano (campos anidados se serializan a JSON dentro de la celda).
   - Loguea fila count y duración.
7. Si una consulta falla, **continúa con las demás** y registra el error.
8. Genera `_resumen.json` y `_resumen.csv` al final.
9. Muestra tabla de resumen en consola.
10. Exit code: `0` éxito total, `2` si hubo errores parciales.

## Códigos de salida

| Exit code | Significado |
|---|---|
| 0 | Todas las consultas OK |
| 1 | Error fatal (módulos, autenticación, carpeta) |
| 2 | Ejecución completa pero con consultas individuales fallidas |

Útil para integrar en pipelines o tareas programadas.

## Automatización (correr diario)

### Tarea programada de Windows

```powershell
# Crear tarea que corre cada día a las 6 AM
$action = New-ScheduledTaskAction -Execute "pwsh.exe" `
    -Argument "-NoProfile -File C:\CASystem\Run-AzureGraphQueries.ps1 -TenantId '...' -ClientName 'ACME' -UseServicePrincipal -ApplicationId '...' -ClientSecret (ConvertTo-SecureString (Get-Content C:\secrets\acme.txt) -AsPlainText -Force)"

$trigger = New-ScheduledTaskTrigger -Daily -At 6am

Register-ScheduledTask -TaskName "ARG-Inventory-ACME" `
    -Action $action -Trigger $trigger `
    -RunLevel Highest
```

### Linux / cron (con PowerShell Core)

```bash
# /etc/cron.d/arg-inventory-acme
0 6 * * * casystem pwsh -NoProfile -File /opt/casystem/Run-AzureGraphQueries.ps1 -TenantId '...' -ClientName 'ACME' -UseServicePrincipal -ApplicationId '...' -ClientSecret (cat /opt/casystem/secrets/acme.txt | ConvertTo-SecureString -AsPlainText -Force)
```

**Importante**: para automatizar, los secrets deben ir en **Azure Key Vault** o en un store seguro, no en archivos planos. Lo de arriba es solo ilustrativo.

## Troubleshooting

**"No se encontraron suscripciones en el tenant"**
El SP o usuario no tiene rol Reader visible al menos en una suscripción. Verificar con `az role assignment list --assignee <appId>`.

**"powerState" sale vacío en VMs**
El script ya pasa `-AllowPartialScope`. Si aun así sale vacío, el rol Reader no tiene permiso sobre `instanceView`. Asignar adicionalmente `Microsoft.Compute/virtualMachines/read` (ya viene en Reader, pero algunos clientes usan roles custom).

**"Operation returned an invalid status code 'Forbidden'"**
La consulta `06-gobierno/01-azure-policy-compliance` necesita acceso a `PolicyResources`. Reader lo cubre, pero verificar que no haya bloqueo a nivel Management Group.

**"Cannot bind parameter 'Subscription'"**
Versión vieja del módulo. Actualizar: `Update-Module Az.ResourceGraph`.

**Tiempo de ejecución muy largo**
Si el tenant tiene >10k recursos por consulta, considerar filtrar por `-SubscriptionIds` y correr por suscripción. ARG tiene throttling de ~15 queries/5seg por usuario.

## Próximo paso sugerido

Una vez que tengas 3–4 ejecuciones acumuladas en `resultados/<Cliente>/`, podemos armar un **notebook de Python** o **plantilla de Power BI** que lea toda la carpeta y genere las tendencias semanales/mensuales del Reporte FinOps.
