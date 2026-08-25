# Espía v2: captura el COMMAND-LINE del Driver (reintenta si viene vacío). Poll 50ms.
$seen = @{}
$log  = "C:\Users\j-b-j\Documents\Hekatan Calc 1.0.0\hekatan-etabs-bridge\etabs\tracer\spy_out.txt"
"=== spy v2 start $(Get-Date -Format HH:mm:ss) ===" | Out-File $log
$end = (Get-Date).AddSeconds(160)
while ((Get-Date) -lt $end) {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match 'SAPFire|Driver|ETABS|Analysis|Scheduler' } |
        ForEach-Object {
            $k = [string]$_.ProcessId
            if (-not $seen.ContainsKey($k)) {
                $cl = $_.CommandLine
                # reintentar leer cmdline si vino vacio (proceso recien creado)
                $tries = 0
                while ([string]::IsNullOrEmpty($cl) -and $tries -lt 5) {
                    Start-Sleep -Milliseconds 40
                    $p = Get-CimInstance Win32_Process -Filter "ProcessId=$($_.ProcessId)" -ErrorAction SilentlyContinue
                    if ($p) { $cl = $p.CommandLine }
                    $tries++
                }
                $seen[$k] = 1
                $line = "[{0}] PID={1} PPID={2} {3}`n        CMD= {4}" -f (Get-Date -Format HH:mm:ss), $_.ProcessId, $_.ParentProcessId, $_.Name, $cl
                $line | Tee-Object -FilePath $log -Append
            }
        }
    Start-Sleep -Milliseconds 50
}
"=== spy end $(Get-Date -Format HH:mm:ss) ===" | Out-File $log -Append
