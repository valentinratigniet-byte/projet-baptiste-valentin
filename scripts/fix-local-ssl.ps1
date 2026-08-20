# ponytail: correctif machine-locale, pas portable (Baptiste n'a probablement pas Avast).
# A relancer a chaque fois qu'un conteneur qui fait des appels HTTPS sortants
# (ollama, futur n8n pour la veille) est recree par `docker compose up`.
# Cause : Avast Web/Mail Shield intercepte le HTTPS avec son propre certificat racine,
# approuve par Windows mais pas par les conteneurs Linux. Voir docs/ARCHITECTURE.md.

param(
    [string[]]$Containers = @("bv-ollama")
)

$cert = Get-ChildItem Cert:\LocalMachine\Root | Where-Object { $_.Subject -like "*Avast Web/Mail Shield*" }
if (-not $cert) {
    Write-Output "Pas de certificat Avast trouve - rien a faire sur cette machine."
    exit 0
}

$crtPath = "$env:TEMP\avast-root.crt"
$pemPath = "$env:TEMP\avast-root.pem"
[System.IO.File]::WriteAllBytes($crtPath, $cert.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Cert))
certutil -encode $crtPath $pemPath | Out-Null

foreach ($c in $Containers) {
    docker cp $pemPath "${c}:/usr/local/share/ca-certificates/avast-root.crt"
    docker exec $c update-ca-certificates
    Write-Output "CA Avast installee dans $c"
}
