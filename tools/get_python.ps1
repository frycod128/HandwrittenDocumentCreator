#Requires -Version 5.1
<#
.SYNOPSIS
    在项目内准备一个便携版 Python，供 tools/bootstrap.py 使用。

.DESCRIPTION
    只在整台机器找不到 Python 时才会运行。下载的运行时解压到项目的 .python
    目录，不安装到系统、不写注册表、不修改 PATH，也不影响其他用户。
    下载后按固定 SHA-256 校验，校验失败即中止。
#>
[CmdletBinding()]
param(
    [string]$Destination = '',
    [string]$Url = 'https://github.com/astral-sh/python-build-standalone/releases/download/20261124/cpython-3.13.18%2B20261124-x86_64-pc-windows-msvc-install_only.tar.gz',
    [string]$Sha256 = '9c22438c8f107dc88505394a87a61aab3504d33d1ce4e22eb177381e5e9b244f',
    [string]$ExpectedVersion = '3.13'
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
}
catch {
    Write-Verbose "无法设置 TLS 1.2，继续使用系统默认值。"
}

function Write-Step([string]$Message) {
    Write-Host "[下载] $Message"
}

if (-not $Destination) {
    $Destination = Join-Path (Split-Path -Parent $PSScriptRoot) '.python'
}
$Destination = [IO.Path]::GetFullPath($Destination)
$pythonExe = Join-Path $Destination 'python.exe'

function Test-PortablePython([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    try {
        $version = & $Path -c "import sys; print('%d.%d' % tuple(sys.version_info[:2]))" 2>$null
        return ($LASTEXITCODE -eq 0 -and $version -eq $ExpectedVersion)
    }
    catch {
        return $false
    }
}

if (Test-PortablePython $pythonExe) {
    Write-Host "项目内已有 Python $ExpectedVersion：$pythonExe"
    Write-Host "PYTHON_EXE=$pythonExe"
    exit 0
}

if (-not (Get-Command tar.exe -ErrorAction SilentlyContinue)) {
    Write-Host "[下载] 缺少 tar.exe（Windows 10 1803 及以上自带），无法解压便携版 Python。" -ForegroundColor Red
    exit 1
}

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ('hdc-python-' + [guid]::NewGuid().ToString('N'))
$archive = Join-Path $tempRoot 'python.tar.gz'
$extractRoot = Join-Path $tempRoot 'extract'

try {
    New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
    Write-Step "下载 Python $ExpectedVersion 便携版（约 47 MB，仅本次运行使用）…"
    Invoke-WebRequest -Uri $Url -OutFile $archive -UseBasicParsing

    Write-Step '校验下载文件的 SHA-256 …'
    $actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $Sha256.ToLowerInvariant()) {
        throw "校验失败：期望 $Sha256，实际 $actual"
    }

    Write-Step '解压到项目内 .python 目录 …'
    New-Item -ItemType Directory -Force -Path $extractRoot | Out-Null
    & tar.exe -xzf $archive -C $extractRoot
    if ($LASTEXITCODE -ne 0) {
        throw "解压失败（tar 退出码 $LASTEXITCODE）"
    }

    $source = Join-Path $extractRoot 'python'
    if (-not (Test-Path -LiteralPath (Join-Path $source 'python.exe'))) {
        $found = Get-ChildItem -LiteralPath $extractRoot -Recurse -Filter 'python.exe' |
            Where-Object { $_.Directory.Name -eq 'python' } |
            Select-Object -First 1
        if (-not $found) {
            throw '压缩包中没有找到 python 目录'
        }
        $source = $found.Directory.FullName
    }

    if (Test-Path -LiteralPath $Destination) {
        Remove-Item -LiteralPath $Destination -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null

    $attempt = 0
    while ($true) {
        try {
            Move-Item -LiteralPath $source -Destination $Destination
            break
        }
        catch {
            $attempt++
            if ($attempt -ge 5) { throw }
            Start-Sleep -Milliseconds 400
        }
    }

    if (-not (Test-PortablePython $pythonExe)) {
        throw '便携版 Python 解压后无法运行'
    }
    & $pythonExe -c "import tkinter, venv" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw '便携版 Python 缺少 tkinter 或 venv'
    }

    Write-Host "Python 已就绪：$pythonExe"
    Write-Host "PYTHON_EXE=$pythonExe"
    exit 0
}
catch {
    Write-Host "[下载] 失败：$($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
finally {
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
