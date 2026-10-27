param(
    [string]$RequestPath,
    [string]$ResponsePath,
    [switch]$HeadOnly
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$taskTransportConfig = [Console]::In.ReadToEnd() | ConvertFrom-Json
$taskEndpoint = [Uri]($taskTransportConfig.base_url.TrimEnd('/') + '/chat/completions')
$taskStatus = $null
$taskContent = $null
$taskError = $null
$taskClient = $null
$taskMessage = $null
$taskResponse = $null
try {
    $taskHandler = [System.Net.Http.HttpClientHandler]::new()
    $taskHandler.AllowAutoRedirect = $false
    $taskClient = [System.Net.Http.HttpClient]::new($taskHandler)
    $taskClient.Timeout = [TimeSpan]::FromSeconds($(if ($HeadOnly) { 20 } else { 360 }))
    if ($HeadOnly) {
        $taskOrigin = $taskEndpoint.GetLeftPart([UriPartial]::Authority) + '/'
        $taskMessage = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Head, $taskOrigin)
    } else {
        $taskMessage = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Post, $taskEndpoint.AbsoluteUri)
        $taskMessage.Headers.Authorization = [System.Net.Http.Headers.AuthenticationHeaderValue]::new('Bearer', [string]$taskTransportConfig.api_key)
        $taskMessage.Content = [System.Net.Http.ByteArrayContent]::new([IO.File]::ReadAllBytes($RequestPath))
        $taskMessage.Content.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::new('application/json')
        $taskMessage.Content.Headers.ContentType.CharSet = 'utf-8'
    }
    $taskResponse = $taskClient.SendAsync($taskMessage).GetAwaiter().GetResult()
    $taskStatus = [int]$taskResponse.StatusCode
    if (-not $HeadOnly) { $taskContent = $taskResponse.Content.ReadAsStringAsync().GetAwaiter().GetResult() }
} catch {
    $taskError = $_.Exception.GetBaseException().Message
    if ($taskTransportConfig.api_key) { $taskError = $taskError.Replace([string]$taskTransportConfig.api_key, '[REDACTED]') }
} finally {
    if ($null -ne $taskResponse) { $taskResponse.Dispose() }
    if ($null -ne $taskMessage) { $taskMessage.Dispose() }
    if ($null -ne $taskClient) { $taskClient.Dispose() }
}
if (-not $HeadOnly -and $null -ne $taskContent) {
    [IO.File]::WriteAllText($ResponsePath, $taskContent, [Text.UTF8Encoding]::new($false))
}
@{
    http_status = $taskStatus
    transport_error = $taskError
    transport = 'System.Net.Http.HttpClient with platform default certificate and hostname verification'
    certificate_validation_disabled = $false
    redirects_followed = $false
} | ConvertTo-Json -Compress
if ($null -eq $taskStatus) { exit 1 }
