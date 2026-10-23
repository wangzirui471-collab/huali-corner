# 一键启动「本机开源模型」版 AI 客服（数据不出本机）
#
#   powershell -ExecutionPolicy Bypass -File scripts\start-ai-local.ps1
#   参数：-Port 8093（默认）、-SkipPull（不去下载模型）、-NoPreflight（跳过自检）
#
# 做四件事：确认 Ollama 在 → 确认模型在（不在就拉）→ 确认知识库索引在 → 自检后启动。
# 模型不可用不阻断启动：检索 + 摘录仍然能答，客服页面不会打不开。

param(
    [int]$Port = 8093,
    [switch]$SkipPull,
    [switch]$NoPreflight
)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host ''
Write-Host '  转角 AI 客服 · 本机开源模型' -ForegroundColor Magenta
Write-Host '  ----------------------------------------'

# 1) Python：优先用项目 venv（依赖齐全），没有就退回 PATH
$py = Join-Path $root '.venv-trial\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }
try { $pyVersion = & $py --version 2>&1 } catch {
    Write-Host '  [错误] 找不到 Python。' -ForegroundColor Red
    exit 1
}
Write-Host "  Python：$pyVersion"

# 2) Ollama 在不在
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host ''
    Write-Host '  [错误] 没有安装 Ollama。' -ForegroundColor Red
    Write-Host '  下载：https://ollama.com/download  （装完启动一次，托盘里能看到它）'
    Write-Host ''
    exit 1
}

# 3) 该用哪个模型：按显存自动选（12G+ → 14b，6G+ → 7b，其余 → 1.5b）
$env:HC_AI_PROVIDER = 'ollama'
$env:HC_AI_AUTO_MODEL = '1'
$env:HC_AI_PORT = "$Port"
$env:HC_AI_WARMUP = '1'
Remove-Item Env:\HC_AI_MOCK -ErrorAction SilentlyContinue

$model = (& $py -c "import sys;sys.path.insert(0,'ai_service');import llm;print(llm.model())").Trim()
$vram = (& $py -c "import sys;sys.path.insert(0,'ai_service');import llm;print(llm.vram_gb() or '')").Trim()
if ($vram) { Write-Host "  显卡显存：$vram GB" } else { Write-Host '  显卡：未检测到 NVIDIA，将用 CPU（很慢，仅够试用）' -ForegroundColor Yellow }
Write-Host "  目标模型：$model"

# 4) 模型在不在
$listed = (& ollama list 2>$null) -join "`n"
$baseName = ($model -split ':')[0]
if ($listed -notmatch [regex]::Escape($baseName)) {
    if ($SkipPull) {
        Write-Host "  [警告] 本机没有 $model，已按 -SkipPull 跳过下载；服务会以摘录模式运行。" -ForegroundColor Yellow
    } else {
        Write-Host ''
        Write-Host "  首次需要下载 $model（约 4–5 GB），只下一次，之后都在本地。" -ForegroundColor Cyan
        Write-Host '  下载中…（进度由 ollama 显示，中断了重跑本脚本会接着下）'
        & ollama pull $model
        if ($LASTEXITCODE -ne 0) {
            Write-Host '  [警告] 模型下载失败；服务仍会启动，只是走摘录模式。' -ForegroundColor Yellow
        }
    }
}

# 5) 知识库索引
$index = Join-Path $root 'ai_service\index.json'
if (-not (Test-Path $index)) {
    Write-Host '  没有知识库索引，正在切片…'
    & $py 'ai_service\ingest.py'
    if ($LASTEXITCODE -ne 0) { Write-Host '  [警告] 切片失败，服务会以空知识库启动。' -ForegroundColor Yellow }
}

# 6) 自检（只读，不下载不修改）
if (-not $NoPreflight) {
    & $py 'ai_service\preflight.py'
    if ($LASTEXITCODE -ne 0) {
        Write-Host '  [提示] 自检没全绿，服务照样启动：先答知识库原文，模型修好后自动恢复。' -ForegroundColor Yellow
    }
}

Write-Host ''
Write-Host "  启动 AI 客服服务：http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host '  这个窗口不要关；Ctrl+C 停止。'
Write-Host '  另开一个窗口跑后端：start-trial-8081.bat'
Write-Host ''

& $py 'ai_service\server.py'
