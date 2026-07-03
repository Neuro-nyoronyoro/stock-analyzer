# 最小ループ#1: scripts/check_alerts.py のIP直書きを検出→修正→検証→Vault記録
# 前提: Claude Code はプラン認証でログイン済み / ANTHROPIC_API_KEY は未設定
# CLIメモ: --max-turns は現行CLI(確認済み)に存在しないため --max-budget-usd で代替

$ErrorActionPreference = "Stop"

$RepoRoot  = "C:\Users\kimura-h-0\Desktop\株式投資ツール"
$VaultLog  = "C:\Users\kimura-h-0\repos\work-vault\outputs\stock-analyzer\loop-log.md"
$MaxIter   = 3
$MaxBudget = "0.10"
$Model     = "claude-sonnet-4-6"
$PythonExe = "C:\Users\kimura-h-0\anaconda3\envs\stock_analyzer\python.exe"
$GateArgs  = @("-m", "pytest", "tests/test_no_hardcoded_ip.py", "-q")

# --- 0) 課金セーフガード（最重要）---
if ($env:ANTHROPIC_API_KEY) {
    Write-Error "[ABORT] ANTHROPIC_API_KEY が設定されています。プラン課金で回すため、このシェルで環境変数を外してから再実行してください。"
    exit 2
}

Set-Location $RepoRoot

# --- 作業ブランチ（L1: main に直接触れない）---
$stamp  = Get-Date -Format "yyyyMMdd-HHmmss"
$branch = "loop/fix-hardcoded-ip-$stamp"
git checkout -b $branch | Out-Null
Write-Host "作業ブランチ作成: $branch"

$totalCost = 0.0
$sessions  = @()
$lastGate  = ""

for ($i = 1; $i -le $MaxIter; $i++) {
    Write-Host "=== iteration $i / $MaxIter ==="

    # --- Checker: 緑なら即終了（トークン節約）---
    $gateOut = & $PythonExe @GateArgs 2>&1
    if ($LASTEXITCODE -eq 0) { break }

    # --- 無進展検出（停止条件）---
    $sig = ($gateOut -join "`n")
    if ($sig -eq $lastGate) {
        Write-Host "[STOP] 無進展を検出（同一の失敗が継続）。ループを打ち切る。"
        break
    }
    $lastGate = $sig

    Write-Host "[Checker] 赤を検出。Maker を起動します。"

    # --- Maker: プラン認証の claude -p が修正を試みる ---
    $prompt = "scripts/check_alerts.py の49行目にハードコードされたIPアドレス（13.114.149.93）があります。" `
        + " DNS名(app.kimura-stock.com)または config.py の設定値へ外出しして修正してください。" `
        + " 厳守: 変更は scripts/check_alerts.py と config.py の設定読み込み部分のみ。他のファイルに触れない。" `
        + " 修正後に pytest tests/test_no_hardcoded_ip.py が緑になること。" `
        + " 秘密情報（APIキー等）を差分・ログに絶対に含めない。"

    $raw = claude -p $prompt --output-format json --permission-mode acceptEdits --allowedTools "Read,Edit,Write" --max-budget-usd $MaxBudget --model $Model

    # コスト・session_id を取得（フィールド名はバージョンで変わる可能性あり）
    try {
        $j = $raw | ConvertFrom-Json
        $cost = 0.0
        if ($null -ne $j.cost_usd)           { $cost = [double]$j.cost_usd }
        elseif ($null -ne $j.total_cost_usd) { $cost = [double]$j.total_cost_usd }
        elseif ($null -ne $j.cost)           { $cost = [double]$j.cost }
        $totalCost += $cost
        if ($j.session_id) { $sessions += $j.session_id }
    } catch {
        Write-Host "[WARN] JSON解析に失敗。コスト不明。"
    }
}

# --- 検証結果の確定 ---
& $PythonExe @GateArgs *>$null
$greenNow = ($LASTEXITCODE -eq 0)

if ($greenNow) {
    $ErrorActionPreference = "SilentlyContinue"
    git add scripts/check_alerts.py config.py
    $ErrorActionPreference = "Stop"
    $staged = git diff --cached --name-only
    if ($staged) {
        git commit -m "[Work-PC] loop#1: check_alerts.py のIP直書きを設定/DNS名へ外出し" | Out-Null
        git push -u origin $branch | Out-Null
        Write-Host "[INFO] ブランチ '$branch' を push しました。PR作成・マージは人間が行う（L1）。"
    } else {
        Write-Host "[INFO] 変更なし（既に修正済み）。コミットをスキップ。"
    }
}

# --- Vault記録（outputs/stock-analyzer/loop-log.md に追記）---
$status = if ($greenNow) { "GREEN(要レビュー)" } else { "RED(未解決)" }
$row    = "| $stamp | $branch | $i | $status | $([math]::Round($totalCost, 4)) | $($sessions -join ',') |"

$vaultDir = Split-Path $VaultLog
if (-not (Test-Path $vaultDir)) {
    New-Item -ItemType Directory -Force $vaultDir | Out-Null
}
if (-not (Test-Path $VaultLog)) {
    $header = "# ループ実行ログ（loop-01-hardcoded-ip）`n`n| 日時 | ブランチ | 反復 | 結果 | コスト(USD) | session_id |`n|---|---|---|---|---|---|"
    $header | Out-File -Encoding utf8 $VaultLog
}
Add-Content -Encoding utf8 -Path $VaultLog -Value $row

Write-Host "=== 完了: $status / 反復=$i / コスト=$([math]::Round($totalCost, 4)) ==="
Write-Host "PRをレビューしてマージするのは人間（L1）。"
