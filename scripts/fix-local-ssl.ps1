# ponytail: correctif machine-locale, jamais totalement portable - chaque
# machine peut avoir un antivirus/proxy different (ou aucun). Generalise
# depuis la version Avast-only (dette technique #1, docs/DETTE-TECHNIQUE.md).
# A relancer a chaque fois qu'un conteneur qui fait des appels HTTPS sortants
# (ollama, futur n8n pour la veille) est recree par `docker compose up`.
#
# Usage :
#   ./fix-local-ssl.ps1                          # auto (marche si Avast, comme sur cette machine)
#   ./fix-local-ssl.ps1 -List                     # liste les root CA "suspects" a installer sur cette machine
#   ./fix-local-ssl.ps1 -CertPattern "Kaspersky"  # cible un autre logiciel

param(
    [string]$CertPattern = "Avast Web/Mail Shield",
    [string[]]$Containers = @("bv-ollama"),
    [switch]$List
)

# Organisations de root CA publiques connues - tout le reste est un
# candidat "logiciel qui intercepte le HTTPS localement".
$EditeursConnus = @(
    "Microsoft", "DigiCert", "GlobalSign", "Sectigo", "IdenTrust", "ISRG",
    "Amazon", "GoDaddy", "Starfield", "Certum", "HARICA", "Thawte",
    "VeriSign", "SwissSign", "Comodo", "USERTrust", "SSL.com", "Certigna",
    "Symantec", "Hellenic Academic"
)

if ($List) {
    Write-Output "Root CA installees hors editeurs publics connus (candidats interception locale) :"
    Get-ChildItem Cert:\LocalMachine\Root | Where-Object {
        $subject = $_.Subject
        -not ($EditeursConnus | Where-Object { $subject -like "*$_*" })
    } | Select-Object Subject | Format-Table -AutoSize -Wrap
    Write-Output "Relancer avec -CertPattern '<mot-clé du Subject ci-dessus>' pour installer le bon certificat."
    exit 0
}

$cert = Get-ChildItem Cert:\LocalMachine\Root | Where-Object { $_.Subject -like "*$CertPattern*" }
if (-not $cert) {
    Write-Output "Pas de certificat correspondant a '$CertPattern' - rien a faire, ou relancer avec -List pour identifier le bon."
    exit 0
}

$crtPath = "$env:TEMP\local-intercept-root.crt"
$pemPath = "$env:TEMP\local-intercept-root.pem"
[System.IO.File]::WriteAllBytes($crtPath, $cert.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Cert))
certutil -encode $crtPath $pemPath | Out-Null

foreach ($c in $Containers) {
    docker cp $pemPath "${c}:/usr/local/share/ca-certificates/local-intercept-root.crt"
    # -u root : certains conteneurs (n8n) tournent par defaut sous un user
    # non-root qui ne peut pas ecrire /etc/ssl/certs (trouve en cablant
    # n8n sur des APIs externes au Sprint 5).
    docker exec -u root $c update-ca-certificates
    Write-Output "CA installee dans $c - penser a `docker restart $c` pour qu'il recharge son pool de certificats."
}
