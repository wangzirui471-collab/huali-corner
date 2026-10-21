<#
.SYNOPSIS
  重构工程的统一任务入口，支持 Windows 中文与空格目录。
.DESCRIPTION
  Setup 安装锁定依赖；Check 检查新工程；Contracts 生成协议；
  Api 启动本地新 API；Web 启动本地组件预览。每项任务遇到失败即停止。
  不执行真实数据迁移、部署或资源绑定操作。
.EXAMPLE
  .\scripts\refactor.ps1 -Task Check
#>
param(
    [ValidateSet('Setup', 'Check', 'Contracts', 'Api', 'Web')]
    [string]$Task = 'Check'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$apiRoot = Join-Path $projectRoot 'apps/api'
$webRoot = Join-Path $projectRoot 'apps/web'
$apiPython = Join-Path $apiRoot '.venv/Scripts/python.exe'

function Invoke-TaskCommand {
    <# 按参数数组调用工具；路径不会被拼接为命令字符串，失败时停止后续任务。 #>
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "任务执行失败：$Executable（退出码 $LASTEXITCODE）"
    }
}

function Get-UvExecutable {
    <# 优先使用已安装 uv；兼容当前项目此前隔离下载的 uv，不自动联网安装工具。 #>
    $command = Get-Command uv -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $localUv = Join-Path $projectRoot '.local-deps/bin/uv.exe'
    if (Test-Path -LiteralPath $localUv) { return $localUv }
    throw '请先安装 uv 0.13.4，并将 uv 加入 PATH，然后运行 Setup。'
}

Push-Location $projectRoot
$previousPythonPath = $env:PYTHONPATH
$previousPythonUtf8 = $env:PYTHONUTF8
$env:PYTHONUTF8 = '1'
try {
    switch ($Task) {
        'Setup' {
            # 从锁文件安装到项目独立环境，不改变旧服务的依赖。
            $env:UV_CACHE_DIR = Join-Path $projectRoot '.uv-cache'
            $env:UV_PYTHON_INSTALL_DIR = Join-Path $projectRoot '.uv-python'
            Invoke-TaskCommand (Get-UvExecutable) @('sync', '--locked', '--project', $apiRoot, '--python', '3.13')
            Invoke-TaskCommand 'npm.cmd' @('--prefix', $webRoot, 'ci')
        }
        'Check' {
            # 新后端先检查风格、中文方法注释和严格类型，再执行契约与事务测试。
            Push-Location $apiRoot
            try {
                Invoke-TaskCommand $apiPython @('-m', 'ruff', 'check', 'src', 'scripts', 'tests')
                Invoke-TaskCommand $apiPython @('-m', 'ruff', 'format', '--check', 'src', 'scripts', 'tests')
                Invoke-TaskCommand $apiPython @('-m', 'mypy')
                $env:PYTHONPATH = Join-Path $apiRoot 'src'
                Invoke-TaskCommand $apiPython @('-B', '-X', 'utf8', '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py')
            } finally { Pop-Location }
            # 前端检查格式、模板类型、异常与控件行为，最后生成默认构建。
            foreach ($webTask in @('lint', 'typecheck', 'test:unit', 'build')) {
                Invoke-TaskCommand 'npm.cmd' @('--prefix', $webRoot, 'run', $webTask)
            }
        }
        'Contracts' {
            # 服务端是 DTO 权威来源；前端类型由实际 OpenAPI 生成。
            Invoke-TaskCommand $apiPython @((Join-Path $apiRoot 'scripts/export_contract.py'))
            Invoke-TaskCommand 'npm.cmd' @('--prefix', $webRoot, 'run', 'generate:api')
        }
        'Api' {
            # 只监听本机回环地址，明确使用 local 环境。
            $env:HUALI_ENV = 'local'
            Invoke-TaskCommand $apiPython @('-m', 'uvicorn', 'huali.main:app', '--app-dir', (Join-Path $apiRoot 'src'), '--host', '127.0.0.1', '--port', '8001')
        }
        'Web' {
            # Vite 的开发路由只用于组件预览；业务页面按后续切片迁移。
            Invoke-TaskCommand 'npm.cmd' @('--prefix', $webRoot, 'run', 'dev')
        }
    }
} finally {
    $env:PYTHONPATH = $previousPythonPath
    $env:PYTHONUTF8 = $previousPythonUtf8
    Pop-Location
}
