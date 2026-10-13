# atualizar.ps1 - baixa a versao mais recente do Sistema de Fiado do GitHub
# e atualiza a pasta onde este arquivo esta. Chamado pelo atualizar.bat.
#
# O que ele faz:
#  - pergunta ao GitHub qual e a ultima versao publicada (Releases);
#  - compara com a instalada (arquivo versao.txt desta pasta);
#  - se houver mais nova: baixa o .zip, confere se chegou inteiro e troca os
#    programas (os .exe, a pasta _internal e os .bat);
#  - NAO mexe no ".env" nem na pasta "app" (configuracoes, backups e logs).
#
# Se algo der errado no meio da troca, a versao anterior e colocada de volta.
#
# Sem acentos de proposito: o PowerShell do Windows le este arquivo como ANSI.

param(
    # Pasta instalada a atualizar (padrao: a pasta deste arquivo).
    [string]$Pasta = $PSScriptRoot,
    # Endereco que informa a ultima versao (so muda nos testes).
    [string]$Origem = 'https://api.github.com/repos/fabioduartep4/sistema-fiado/releases/latest',
    # Atualiza sem pedir confirmacao.
    [switch]$Sim
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# Nunca sao trocados pela atualizacao: pertencem a este computador.
$PRESERVADOS = @('.env', 'app')

function Sair([int]$codigo, [string]$mensagem) {
    if ($mensagem) { Write-Host ''; Write-Host $mensagem }
    exit $codigo
}

# Troca de nome dentro do mesmo disco: ou move tudo, ou nao move nada. (O
# Move-Item, numa pasta com arquivo em uso, deixaria metade em cada lugar.)
function Mover([string]$de, [string]$para) {
    if (Test-Path -LiteralPath $de -PathType Container) { [IO.Directory]::Move($de, $para) }
    else { [IO.File]::Move($de, $para) }
}

# Apaga uma pasta inteira. O prefixo \\?\ faz o Windows aceitar caminhos com
# mais de 260 letras, que o Remove-Item nao consegue apagar.
function Apagar-Pasta([string]$caminho) {
    if (-not (Test-Path -LiteralPath $caminho)) { return }
    try { [IO.Directory]::Delete('\\?\' + $caminho, $true) }
    catch { Remove-Item -LiteralPath $caminho -Recurse -Force -ErrorAction SilentlyContinue }
}

function Ler-Versao([string]$texto) {
    $limpo = ($texto -replace '^[vV]', '').Trim()
    try { return [version]$limpo } catch { return $null }
}

Write-Host '============================================'
Write-Host ' Sistema de Fiado - Atualizar pelo GitHub'
Write-Host '============================================'
Write-Host ''

$Pasta = (Resolve-Path $Pasta).Path.TrimEnd('\')
if (-not (Test-Path (Join-Path $Pasta 'SistemaFiado.exe'))) {
    Sair 1 "Nao encontrei o SistemaFiado.exe em:`n  $Pasta`nColoque o atualizar.bat e o atualizar.ps1 dentro da pasta do sistema."
}

$arquivoVersao = Join-Path $Pasta 'versao.txt'
$instalada = $null
if (Test-Path $arquivoVersao) { $instalada = Ler-Versao (Get-Content $arquivoVersao -Raw) }
if ($instalada) { Write-Host "Versao instalada:  $instalada" } else { Write-Host 'Versao instalada:  desconhecida (anterior ao atualizador)' }

# ---------------------------------------------------------------- consulta
try {
    $release = Invoke-RestMethod -Uri $Origem -Headers @{ 'User-Agent' = 'SistemaFiado-Atualizador' } -TimeoutSec 30
} catch {
    $resposta = $_.Exception.Response
    if ($resposta -and [int]$resposta.StatusCode -eq 404) {
        Sair 0 'Ainda nao ha nenhuma versao publicada no GitHub. Nada a fazer.'
    }
    Sair 1 "Nao consegui consultar o GitHub. Confira a internet e tente de novo.`nDetalhe: $($_.Exception.Message)"
}

$disponivel = Ler-Versao $release.tag_name
if (-not $disponivel) { Sair 1 "A versao publicada no GitHub tem um nome que nao entendi: '$($release.tag_name)'." }
Write-Host "Versao no GitHub:  $disponivel"

if ($instalada -and $instalada -ge $disponivel) {
    Sair 0 'Este computador ja esta na versao mais recente. Nada a fazer.'
}

$pacote = $release.assets | Where-Object { $_.name -like '*.zip' } | Select-Object -First 1
if (-not $pacote) { Sair 1 "A versao $disponivel foi publicada sem o arquivo .zip do programa." }

$tamanhoMb = [math]::Round($pacote.size / 1MB)
Write-Host ''
Write-Host "Ha uma versao nova ($disponivel, $tamanhoMb MB)."
if ($release.body) { Write-Host ''; Write-Host 'O que mudou:'; Write-Host $release.body }
if (-not $Sim) {
    Write-Host ''
    $resposta = Read-Host 'Atualizar agora? (S/N)'
    if ($resposta -notmatch '^[sS]') { Sair 0 'Atualizacao cancelada. Nada foi alterado.' }
}

# O sistema nao pode estar aberto: o Windows nao deixa trocar arquivo em uso.
$abertos = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith("$Pasta\", [StringComparison]::OrdinalIgnoreCase) }
if ($abertos) {
    $nomes = ($abertos | ForEach-Object { $_.ProcessName } | Sort-Object -Unique) -join ', '
    Sair 1 "Feche o sistema neste computador antes de atualizar (aberto: $nomes) e rode de novo."
}

# ---------------------------------------------------------------- download
$temporaria = Join-Path ([IO.Path]::GetTempPath()) ("SistemaFiado_atualizacao_" + [guid]::NewGuid().ToString('N'))
$anterior = Join-Path $Pasta '_versao_anterior'
New-Item -ItemType Directory -Path $temporaria | Out-Null
try {
    $zip = Join-Path $temporaria 'pacote.zip'
    Write-Host ''
    Write-Host '[1/3] Baixando...'
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($curl) {
        # curl.exe mostra o andamento do download; o PowerShell sozinho, nao.
        & $curl.Source -L --fail --progress-bar -o $zip $pacote.browser_download_url
        if ($LASTEXITCODE -ne 0) { throw 'O download falhou.' }
    } else {
        Invoke-WebRequest -Uri $pacote.browser_download_url -OutFile $zip -UseBasicParsing
    }

    if ((Get-Item $zip).Length -ne $pacote.size) { throw 'O arquivo baixado veio incompleto.' }
    if ($pacote.digest -like 'sha256:*') {
        $esperado = $pacote.digest.Substring(7)
        $obtido = (Get-FileHash $zip -Algorithm SHA256).Hash
        if ($obtido -ne $esperado) { throw 'O arquivo baixado nao confere com o publicado (soma SHA-256 diferente).' }
    }

    Write-Host '[2/3] Abrindo o pacote...'
    $extraido = Join-Path $temporaria 'conteudo'
    Expand-Archive -Path $zip -DestinationPath $extraido
    $exe = Get-ChildItem -Path $extraido -Filter 'SistemaFiado.exe' -Recurse | Select-Object -First 1
    if (-not $exe) { throw 'O pacote baixado nao tem o SistemaFiado.exe.' }
    $nova = $exe.Directory.FullName
    if (-not (Test-Path (Join-Path $nova '_internal'))) { throw 'O pacote baixado nao tem a pasta _internal.' }

    # ------------------------------------------------------------- troca
    Write-Host '[3/3] Trocando os programas...'
    $itens = Get-ChildItem -LiteralPath $nova -Force | Where-Object { $PRESERVADOS -notcontains $_.Name }
    Apagar-Pasta $anterior
    if (Test-Path $anterior) { throw 'Nao consegui apagar a pasta _versao_anterior, que sobrou de uma atualizacao passada. Apague-a a mao.' }
    New-Item -ItemType Directory -Path $anterior | Out-Null
    $movidos = @()
    try {
        # A pasta _internal sai inteira: misturar arquivos de duas versoes faz
        # o programa parar de abrir ("Failed to load Python DLL").
        foreach ($item in $itens) {
            $atual = Join-Path $Pasta $item.Name
            if (Test-Path -LiteralPath $atual) {
                Mover $atual (Join-Path $anterior $item.Name)
                $movidos += $item.Name
            }
        }
        foreach ($item in $itens) {
            Copy-Item -LiteralPath $item.FullName -Destination (Join-Path $Pasta $item.Name) -Recurse -Force
        }
        Set-Content -LiteralPath $arquivoVersao -Value "$disponivel" -Encoding ascii
    } catch {
        Write-Host 'A troca falhou. Colocando a versao anterior de volta...'
        foreach ($nome in $movidos) {
            $atual = Join-Path $Pasta $nome
            if (Test-Path -LiteralPath $atual) { Remove-Item -LiteralPath $atual -Recurse -Force -ErrorAction SilentlyContinue }
            try { Mover (Join-Path $anterior $nome) $atual } catch { Write-Host "  Nao consegui devolver: $nome (esta em _versao_anterior)" }
        }
        # So apaga a pasta de reserva se tudo voltou para o lugar (ficou vazia).
        if (-not (Get-ChildItem -LiteralPath $anterior -Force)) { Remove-Item -LiteralPath $anterior -Force }
        throw
    }
    Apagar-Pasta $anterior
} catch {
    Sair 1 "A atualizacao NAO foi concluida: $($_.Exception.Message)`nO sistema continua na versao anterior. Se o motivo for arquivo em uso ou acesso negado, feche o sistema e rode de novo."
} finally {
    Apagar-Pasta $temporaria
}

Write-Host ''
Write-Host '============================================'
Write-Host " Pronto! Sistema atualizado para a versao $disponivel."
Write-Host '============================================'
Write-Host 'O ".env" e a pasta "app" (configuracoes, backups e logs) foram mantidos.'
Write-Host 'Abra o SistemaFiado.exe e confira o numero da versao na tela de login.'
if (Test-Path $anterior) { Write-Host 'Sobrou a pasta "_versao_anterior" (a versao antiga). Pode apagar a mao.' }
exit 0
