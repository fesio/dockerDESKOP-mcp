param(
    [Parameter(Mandatory = $true)][string]$Action,
    [Parameter(Mandatory = $true)][string]$Target,
    [ValidateRange(30, 900)][int]$TtlSeconds = 300
)

$secureSecret = Read-Host "PROGRAMMER_APPROVAL_SECRET" -AsSecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureSecret)
try {
    $plainSecret = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    $plainSecret | uv run python -m app.approval_cli --action $Action --target $Target --ttl $TtlSeconds
}
finally {
    if ($null -ne $plainSecret) { $plainSecret = $null }
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
}
