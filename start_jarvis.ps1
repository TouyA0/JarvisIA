# Lance toute la chaîne Jarvis en un clic :
#   1. Vérifie/démarre Docker Desktop + le conteneur Speaches (STT/TTS)
#   2. Vérifie/démarre Ollama (cerveau conversationnel local)
#   3. Préchauffe le modèle local en arrière-plan (~2 min à froid, sinon Jarvis
#      démarre avec un premier "chat" lent le temps que le modèle charge)
#   4. Lance jarvis.py
#
# Docker Desktop et Ollama démarrent normalement tout seuls avec Windows — ce
# script ne fait rien dans ce cas (juste une vérification rapide), et ne les
# relance que s'ils ont été fermés manuellement.

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

function Write-Step($msg) { Write-Host "-> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "   OK   $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "   !!   $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "   X    $msg" -ForegroundColor Red }

function Get-EnvValue($key, $default) {
    $envFile = Join-Path $ProjectDir ".env"
    if (Test-Path $envFile) {
        $line = Get-Content $envFile -Encoding UTF8 |
            Where-Object { $_ -match "^\s*$key\s*=" } | Select-Object -First 1
        if ($line) { return ($line -split "=", 2)[1].Trim() }
    }
    return $default
}

Write-Host "=== Démarrage de Jarvis ===" -ForegroundColor Magenta
Write-Host ""

# --- 1. Docker Desktop + conteneur Speaches (STT + TTS local) ---
Write-Step "Docker Desktop..."
$dockerReady = $false
try { docker info *> $null; $dockerReady = $true } catch {}

if (-not $dockerReady) {
    Write-Warn "Docker Desktop n'est pas démarré. Lancement..."
    $dockerExe = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerExe) {
        Start-Process $dockerExe
        $elapsed = 0
        while (-not $dockerReady -and $elapsed -lt 90) {
            Start-Sleep -Seconds 3
            $elapsed += 3
            try { docker info *> $null; $dockerReady = $true } catch {}
            Write-Host "." -NoNewline
        }
        Write-Host ""
    } else {
        Write-Err "Docker Desktop introuvable à l'emplacement attendu."
    }
}

if ($dockerReady) {
    Write-Ok "Docker Desktop actif."
    Write-Step "Conteneur Speaches (STT/TTS)..."
    $running = docker ps --filter "name=^speaches$" --format "{{.Names}}" 2>$null
    if ($running -eq "speaches") {
        Write-Ok "Speaches déjà actif."
    } else {
        $exists = docker ps -a --filter "name=^speaches$" --format "{{.Names}}" 2>$null
        if ($exists -eq "speaches") {
            docker start speaches *> $null
            Start-Sleep -Seconds 2
            Write-Ok "Speaches redémarré."
        } else {
            Write-Err "Le conteneur 'speaches' n'existe pas encore. Jarvis n'aura ni voix ni oreilles."
            Write-Err "Recrée-le : docker run -d --name speaches --restart unless-stopped -p 8000:8000 -v speaches-cache:/home/ubuntu/.cache ghcr.io/speaches-ai/speaches:latest-cpu"
        }
    }
} else {
    Write-Err "Docker Desktop n'a pas démarré à temps. Le STT/TTS local ne fonctionnera pas."
}
Write-Host ""

# --- 2. Ollama (conversation locale — pilotage PC reste sur Claude) ---
# On utilise curl.exe plutôt qu'Invoke-RestMethod : sur certaines machines
# (VPN actif, proxy, pilote réseau filtrant), le client HTTP .NET utilisé par
# Invoke-RestMethod expire systématiquement en boucle sur des appels
# localhost alors que curl.exe (implémentation réseau différente) répond
# normalement. Toujours appeler "curl.exe" explicitement : "curl" tout court
# est un alias PowerShell vers Invoke-WebRequest, pas le vrai binaire.
function Test-HttpOk($url) {
    $code = & curl.exe -s -o NUL -w "%{http_code}" --max-time 2 $url 2>$null
    return ($code -eq "200")
}

Write-Step "Ollama..."
$ollamaReady = Test-HttpOk "http://localhost:11434/api/version"

if (-not $ollamaReady) {
    Write-Warn "Ollama n'est pas démarré. Lancement..."
    $ollamaExe = "$env:LOCALAPPDATA\Programs\Ollama\ollama app.exe"
    if (Test-Path $ollamaExe) {
        Start-Process $ollamaExe
        # "ollama app.exe" initialise sa fenêtre/icône avant de lancer le vrai
        # service (ollama.exe serve) — ça peut prendre nettement plus de 20s
        # au démarrage à froid. 60s laisse une vraie marge sans bloquer pour
        # rien si Ollama n'est simplement pas installé/répond jamais.
        $elapsed = 0
        while (-not $ollamaReady -and $elapsed -lt 60) {
            Start-Sleep -Seconds 2
            $elapsed += 2
            $ollamaReady = Test-HttpOk "http://localhost:11434/api/version"
            Write-Host "." -NoNewline
        }
        Write-Host ""
    } else {
        Write-Warn "Ollama introuvable à l'emplacement attendu."
    }
}

if ($ollamaReady) {
    Write-Ok "Ollama actif."
    $ollamaModel = Get-EnvValue "OLLAMA_MODEL" "qwen3:14b"
    Write-Step "Préchauffage de $ollamaModel en arrière-plan (jusqu'à 2 min la première fois)..."
    Start-Job -ScriptBlock {
        param($model)
        # Passer le JSON en argument direct à curl.exe ne marche pas de façon
        # fiable sous PowerShell : le marshaling vers un exécutable natif peut
        # tronquer les guillemets ("{"" disparaît), et Ollama (en Go) rejette
        # le tout avec une 400. On écrit donc le JSON dans un fichier — mais
        # PAS avec [System.Text.Encoding]::UTF8, qui ajoute un BOM que le
        # parseur JSON de Go refuse aussi. UTF8Encoding($false) = sans BOM.
        $json = "{`"model`":`"$model`",`"messages`":[{`"role`":`"user`",`"content`":`"Bonjour`"}],`"stream`":false,`"keep_alive`":`"30m`"}"
        $tmpFile = [System.IO.Path]::GetTempFileName()
        $noBom = New-Object System.Text.UTF8Encoding $false
        [System.IO.File]::WriteAllText($tmpFile, $json, $noBom)
        & curl.exe -s --max-time 180 -X POST "http://localhost:11434/api/chat" -H "Content-Type: application/json" --data-binary "@$tmpFile" *> $null
        Remove-Item $tmpFile -ErrorAction SilentlyContinue
    } -ArgumentList $ollamaModel | Out-Null
} else {
    Write-Warn "Ollama ne répond pas encore après 60s. Jarvis basculera sur Claude en attendant."
    Write-Warn "Pas d'inquiétude : Jarvis retente Ollama à chaque question — dès qu'il répond, le chat repasse en local automatiquement, sans redémarrer Jarvis."
}
Write-Host ""

# --- 3. Jarvis ---
Write-Step "Lancement de Jarvis..."
Write-Host ""
python jarvis.py
