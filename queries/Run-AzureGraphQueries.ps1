#Requires -Version 5.1
<#
.SYNOPSIS
    Ejecuta todas las consultas KQL de Azure Resource Graph contra un tenant
    de cliente y guarda los resultados en formato JSON y CSV con timestamp.

.DESCRIPTION
    Script operativo para la Practica Integral de Servicios Azure de C&A Systems.
    Lee todos los archivos .kql del directorio de consultas, los ejecuta usando
    Search-AzGraph contra el tenant del cliente, y guarda los resultados en una
    carpeta estructurada por cliente y fecha.

    Caracteristicas:
    - SOLO LECTURA. No crea ni modifica nada en el tenant del cliente.
    - Autenticacion con Service Principal o interactiva.
    - Doble salida: JSON crudo (para reproceso) y CSV (para Excel/Power BI).
    - Paginacion automatica hasta 10,000 filas por consulta.
    - Resumen de ejecucion con conteo de filas, duracion y errores.
    - Continua aunque alguna consulta individual falle.

.PARAMETER TenantId
    ID del tenant Azure del cliente (obligatorio).

.PARAMETER ClientName
    Nombre corto del cliente para organizar carpetas. Default: 'cliente'.

.PARAMETER SubscriptionIds
    Lista opcional de IDs de suscripcion a consultar. Si se omite, usa todas
    las visibles al usuario o Service Principal autenticado.

.PARAMETER QueriesPath
    Ruta a la carpeta con archivos .kql. Default: ./queries

.PARAMETER OutputPath
    Ruta base donde guardar resultados. Default: ./resultados

.PARAMETER UseServicePrincipal
    Si se especifica, usa autenticacion con Service Principal en lugar de interactiva.

.PARAMETER ApplicationId
    Application (Client) ID del Service Principal. Requerido con -UseServicePrincipal.

.PARAMETER ClientSecret
    Secret del Service Principal como SecureString. Requerido con -UseServicePrincipal.

.PARAMETER SkipAuth
    Salta el paso de autenticacion (util si ya hiciste Connect-AzAccount).

.EXAMPLE
    # Login interactivo, todas las suscripciones del cliente ACME
    .\Run-AzureGraphQueries.ps1 -TenantId "11111111-2222-3333-4444-555555555555" -ClientName "ACME"

.EXAMPLE
    # Con Service Principal
    $sec = ConvertTo-SecureString "secret-del-sp" -AsPlainText -Force
    .\Run-AzureGraphQueries.ps1 `
        -TenantId "11111111-2222-3333-4444-555555555555" `
        -ClientName "ACME" `
        -UseServicePrincipal `
        -ApplicationId "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" `
        -ClientSecret $sec

.EXAMPLE
    # Limitado a suscripciones especificas
    .\Run-AzureGraphQueries.ps1 -TenantId "..." -ClientName "ACME" `
        -SubscriptionIds @("sub-id-1", "sub-id-2")

.NOTES
    Autor:   C&A Systems - Operaciones Tecnologicas
    Modulo:  Requiere Az.Accounts y Az.ResourceGraph
    Install: Install-Module Az.Accounts, Az.ResourceGraph -Scope CurrentUser
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$TenantId,

    [Parameter()]
    [string]$ClientName = "cliente",

    [Parameter()]
    [string[]]$SubscriptionIds,

    [Parameter()]
    [string]$QueriesPath = $PSScriptRoot,

    [Parameter()]
    [string]$OutputPath = (Join-Path $PSScriptRoot "resultados"),

    [Parameter()]
    [switch]$UseServicePrincipal,

    [Parameter()]
    [string]$ApplicationId,

    [Parameter()]
    [SecureString]$ClientSecret,

    [Parameter()]
    [switch]$SkipAuth,

    [Parameter()]
    [int]$BatchSize = 1000
)

$ErrorActionPreference = 'Stop'

# ============================================================================
# Helpers de salida en consola
# ============================================================================
function Write-Info  ($msg) { Write-Host "[INFO]  $msg" -ForegroundColor Cyan }
function Write-Ok    ($msg) { Write-Host "[OK]    $msg" -ForegroundColor Green }
function Write-Warn  ($msg) { Write-Host "[WARN]  $msg" -ForegroundColor Yellow }
function Write-Err   ($msg) { Write-Host "[ERROR] $msg" -ForegroundColor Red }

Write-Host ""
Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host " C&A Systems - Azure Resource Graph Runner" -ForegroundColor DarkCyan
Write-Host " Cliente: $ClientName" -ForegroundColor DarkCyan
Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host ""

# ============================================================================
# 1. Validacion de modulos requeridos
# ============================================================================
Write-Info "Validando modulos requeridos..."
$requiredModules = @('Az.Accounts', 'Az.ResourceGraph')
foreach ($mod in $requiredModules) {
    if (-not (Get-Module -ListAvailable -Name $mod)) {
        Write-Err "Modulo '$mod' no instalado."
        Write-Host "  Ejecuta: Install-Module $mod -Scope CurrentUser" -ForegroundColor Yellow
        exit 1
    }
}
Import-Module Az.Accounts -ErrorAction Stop
Import-Module Az.ResourceGraph -ErrorAction Stop
Write-Ok "Modulos cargados."

# ============================================================================
# 2. Autenticacion
# ============================================================================
if (-not $SkipAuth) {
    Write-Info "Autenticando en tenant $TenantId..."

    if ($UseServicePrincipal) {
        if (-not $ApplicationId -or -not $ClientSecret) {
            Write-Err "Para -UseServicePrincipal se requieren -ApplicationId y -ClientSecret."
            exit 1
        }
        $cred = New-Object System.Management.Automation.PSCredential($ApplicationId, $ClientSecret)
        Connect-AzAccount -ServicePrincipal -TenantId $TenantId -Credential $cred -WarningAction SilentlyContinue | Out-Null
        Write-Ok "Autenticado como Service Principal $ApplicationId"
    }
    else {
        Connect-AzAccount -TenantId $TenantId -WarningAction SilentlyContinue | Out-Null
        $ctx = Get-AzContext
        Write-Ok "Autenticado como $($ctx.Account.Id)"
    }
}
else {
    Write-Warn "Saltando autenticacion (-SkipAuth). Asumo sesion activa."
}

# ============================================================================
# 3. Listar suscripciones objetivo
# ============================================================================
$visibleSubs = Get-AzSubscription -TenantId $TenantId -ErrorAction Stop
if (-not $visibleSubs) {
    Write-Err "No se encontraron suscripciones en el tenant. Verifica permisos del SP/usuario (rol Reader)."
    exit 1
}

Write-Host ""
Write-Info "Suscripciones visibles en el tenant ($($visibleSubs.Count)):"
$visibleSubs | ForEach-Object { Write-Host "  - $($_.Name)  ($($_.Id))" -ForegroundColor Gray }

if ($SubscriptionIds) {
    $targetSubs = $SubscriptionIds
    Write-Info "Filtrando a $($targetSubs.Count) suscripcion(es) especificada(s)."
}
else {
    $targetSubs = $visibleSubs.Id
    Write-Info "Usando TODAS las suscripciones visibles."
}

# ============================================================================
# 4. Preparar estructura de carpetas de salida
# ============================================================================
$timestamp   = Get-Date -Format "yyyy-MM-dd_HHmm"
$dateOnly    = Get-Date -Format "yyyy-MM-dd"
$runFolder   = Join-Path $OutputPath (Join-Path $ClientName $timestamp)
$jsonFolder  = Join-Path $runFolder "json"
$csvFolder   = Join-Path $runFolder "csv"
$logFile     = Join-Path $runFolder "ejecucion.log"

New-Item -ItemType Directory -Path $jsonFolder -Force | Out-Null
New-Item -ItemType Directory -Path $csvFolder  -Force | Out-Null

Write-Host ""
Write-Info "Carpeta de salida: $runFolder"

# Iniciar log
"=== Ejecucion ARG Runner - $timestamp ===" | Out-File $logFile -Encoding UTF8
"Cliente: $ClientName" | Out-File $logFile -Append -Encoding UTF8
"Tenant:  $TenantId"   | Out-File $logFile -Append -Encoding UTF8
"Subs:    $($targetSubs -join ', ')" | Out-File $logFile -Append -Encoding UTF8
"" | Out-File $logFile -Append -Encoding UTF8

# ============================================================================
# 5. Localizar archivos de consulta
# ============================================================================
if (-not (Test-Path $QueriesPath)) {
    Write-Err "No existe la carpeta de consultas: $QueriesPath"
    exit 1
}

$queryFiles = Get-ChildItem -Path $QueriesPath -Recurse -Filter "*.kql" | Sort-Object FullName
if (-not $queryFiles) {
    Write-Err "No se encontraron archivos .kql en $QueriesPath"
    exit 1
}

Write-Info "Encontradas $($queryFiles.Count) consultas para ejecutar."
Write-Host ""

# ============================================================================
# 6. Funcion: ejecutar consulta con paginacion
# ============================================================================
function Invoke-ArgQueryPaginated {
    param(
        [Parameter(Mandatory)] [string]   $Query,
        [Parameter()]          [string[]] $Subscriptions,
        [Parameter()]          [int]      $PageSize = 1000
    )

    $allRows = [System.Collections.ArrayList]::new()
    $skip = 0
    $maxSkip = 10000   # limite duro de Azure Resource Graph

    do {
        $params = @{
            Query       = $Query
            First       = $PageSize
            ErrorAction = 'Stop'
        }
        if ($Subscriptions) { $params['Subscription'] = $Subscriptions }
        if ($skip -gt 0)    { $params['Skip']         = $skip }   # -Skip exige minimo 1

        $batch = Search-AzGraph @params

        if ($batch) {
            [void]$allRows.AddRange(@($batch))
        }
        $batchCount = if ($batch) { @($batch).Count } else { 0 }
        $skip += $batchCount

        # Si el batch fue menor al PageSize, no hay mas paginas
        if ($batchCount -lt $PageSize) { break }
    } while ($skip -lt $maxSkip)

    if ($skip -ge $maxSkip) {
        Write-Warn "Se alcanzo el limite de 10,000 filas (ARG -Skip max). Considera filtrar la consulta."
    }

    return ,$allRows
}

# ============================================================================
# 7. Funcion: flatten de objetos para CSV
# ============================================================================
function ConvertTo-FlatRow {
    param([Parameter(Mandatory)][object]$Row)

    $flat = [ordered]@{}
    foreach ($prop in $Row.PSObject.Properties) {
        $val = $prop.Value
        if ($null -eq $val) {
            $flat[$prop.Name] = ''
        }
        elseif ($val -is [string] -or $val -is [bool] -or $val -is [int] -or
                $val -is [long]   -or $val -is [double] -or $val -is [datetime]) {
            $flat[$prop.Name] = $val
        }
        else {
            # Hashtables, arrays, PSCustomObjects anidados -> JSON compacto
            try {
                $flat[$prop.Name] = ($val | ConvertTo-Json -Compress -Depth 10)
            }
            catch {
                $flat[$prop.Name] = [string]$val
            }
        }
    }
    return [PSCustomObject]$flat
}

# ============================================================================
# 8. Ejecutar cada consulta
# ============================================================================
$summary    = [System.Collections.ArrayList]::new()
$totalStart = Get-Date
$i = 0

foreach ($qf in $queryFiles) {
    $i++
    $queryName    = $qf.BaseName
    $category     = Split-Path -Leaf $qf.Directory
    $relativeName = "$category/$queryName"

    Write-Progress -Activity "Ejecutando consultas ARG" `
                   -Status "$i de $($queryFiles.Count): $relativeName" `
                   -PercentComplete (($i / $queryFiles.Count) * 100)

    Write-Info "[$i/$($queryFiles.Count)] $relativeName"

    $queryStart = Get-Date
    $status   = "OK"
    $rowCount = 0
    $errorMsg = ""

    try {
        $kql = Get-Content -Raw -Path $qf.FullName -Encoding UTF8
        $results = Invoke-ArgQueryPaginated -Query $kql -Subscriptions $targetSubs -PageSize $BatchSize
        $rowCount = if ($results) { @($results).Count } else { 0 }

        # ---- Guardar JSON crudo ----
        $jsonPath = Join-Path $jsonFolder "$queryName.json"
        if ($rowCount -gt 0) {
            $results | ConvertTo-Json -Depth 20 | Out-File -FilePath $jsonPath -Encoding UTF8
        }
        else {
            "[]" | Out-File -FilePath $jsonPath -Encoding UTF8
        }

        # ---- Guardar CSV plano ----
        $csvPath = Join-Path $csvFolder "$queryName.csv"
        if ($rowCount -gt 0) {
            $flatRows = $results | ForEach-Object { ConvertTo-FlatRow -Row $_ }
            $flatRows | Export-Csv -Path $csvPath -NoTypeInformation -Encoding UTF8
        }
        else {
            "# Sin resultados" | Out-File -FilePath $csvPath -Encoding UTF8
        }

        Write-Ok "  -> $rowCount filas"
    }
    catch {
        $status   = "ERROR"
        $errorMsg = $_.Exception.Message
        Write-Err "  -> $errorMsg"
    }

    $duration = ((Get-Date) - $queryStart).TotalSeconds

    [void]$summary.Add([PSCustomObject]@{
        Categoria       = $category
        Consulta        = $queryName
        Estado          = $status
        Filas           = $rowCount
        Duracion_seg    = [math]::Round($duration, 2)
        Error           = $errorMsg
    })

    "[$status] $relativeName - $rowCount filas en $([math]::Round($duration,2))s $(if($errorMsg){"- $errorMsg"})" |
        Out-File $logFile -Append -Encoding UTF8
}

Write-Progress -Activity "Ejecutando consultas ARG" -Completed

$totalDuration = ((Get-Date) - $totalStart).TotalSeconds

# ============================================================================
# 9. Resumen final - guardar y mostrar
# ============================================================================
$okCount   = ($summary | Where-Object Estado -eq 'OK').Count
$errCount  = ($summary | Where-Object Estado -eq 'ERROR').Count
$totalRows = ($summary | Measure-Object -Property Filas -Sum).Sum

$summaryData = [PSCustomObject]@{
    cliente              = $ClientName
    tenantId             = $TenantId
    fecha_ejecucion      = $timestamp
    fecha_iso            = (Get-Date).ToString("o")
    suscripciones        = $targetSubs
    total_consultas      = $summary.Count
    consultas_ok         = $okCount
    consultas_error      = $errCount
    total_filas          = $totalRows
    duracion_total_seg   = [math]::Round($totalDuration, 2)
    carpeta_salida       = $runFolder
    detalle              = $summary
}

$summaryJson = Join-Path $runFolder "_resumen.json"
$summaryCsv  = Join-Path $runFolder "_resumen.csv"
$summaryData | ConvertTo-Json -Depth 20 | Out-File $summaryJson -Encoding UTF8
$summary | Export-Csv -Path $summaryCsv -NoTypeInformation -Encoding UTF8

Write-Host ""
Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host " RESUMEN DE EJECUCION" -ForegroundColor DarkCyan
Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host (" Cliente:          {0}" -f $ClientName)
Write-Host (" Tenant:           {0}" -f $TenantId)
Write-Host (" Fecha:            {0}" -f $timestamp)
Write-Host (" Suscripciones:    {0}" -f $targetSubs.Count)
Write-Host (" Consultas OK:     {0} / {1}" -f $okCount, $summary.Count) -ForegroundColor $(if ($errCount -eq 0) { 'Green' } else { 'Yellow' })
if ($errCount -gt 0) {
    Write-Host (" Consultas ERROR:  {0}" -f $errCount) -ForegroundColor Red
}
Write-Host (" Total filas:      {0}" -f $totalRows)
Write-Host (" Duracion total:   {0} seg" -f [math]::Round($totalDuration, 2))
Write-Host (" Salida:           {0}" -f $runFolder)
Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host ""

$summary | Format-Table Categoria, Consulta, Estado, Filas, Duracion_seg -AutoSize

if ($errCount -gt 0) {
    Write-Host ""
    Write-Warn "Algunas consultas fallaron. Revisa $logFile para detalles."
    exit 2
}

Write-Host ""
Write-Ok "Ejecucion completada sin errores."
exit 0