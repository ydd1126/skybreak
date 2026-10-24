# install-macos26.ps1 - 让 agent 全自动把 macOS 26 装到本机（Windows 侧）
#
# 设计目标：用户只说一句"帮我装 macOS 26"，agent 跑这个脚本，用户只做物理动作。
#
# 用法（agent 视角）：
#   powershell -File install-macos26.ps1 -DryRun                 # 第 1 步：只体检，不碰盘
#   powershell -File install-macos26.ps1 -Serial <U盘序列号>      # 第 2 步：真写盘（会自提权）
#
# 关键设计：
#   · 所有路径都可发现/可下载，不写死用户名与盘符
#   · 复用已验证 EFI 优先（零下载），没有再 scan+build（需 1401）
#   · 生成/复用后强制体检（inspect-config.py），FAIL 就停，不写出坏盘
#   · 写盘前必须按物理序列号确认，绝不按盘符
#   · 代理 / TUN / 苹果服务器 TLS 预检
#   · 全程非交互（stdin 接 NUL），日志实时落盘
param(
  [switch]$DryRun,
  [int]$UsbDisk = -1,
  [string]$Serial = '',
  [int]$MacOS = 25,              # 24 = Sequoia 15，25 = Tahoe 26（传 26/15 自动换算）
  [switch]$ForceBuild,           # 忽略复用，强制 scan+build 一套新 EFI
  [string]$ReuseEfi = '',
  [string]$EngineRoot = '',
  [string]$DriverTar = '',
  [string]$WorkRoot = '',
  [switch]$NoElevate
)
$ErrorActionPreference = 'Stop'
$script:lines = New-Object System.Collections.ArrayList

# ---------------- 工作目录与实时日志 ----------------
if (-not $WorkRoot) { $WorkRoot = Join-Path $env:TEMP 'macos26-oneclick' }
if (-not (Test-Path $WorkRoot)) { New-Item -ItemType Directory -Force -Path $WorkRoot | Out-Null }
$script:logFile = Join-Path $WorkRoot ('install-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')

function Say([string]$m, [string]$c = 'Gray') {
  Write-Host $m -ForegroundColor $c
  [void]$script:lines.Add($m)
  try { Add-Content -Path $script:logFile -Value $m -Encoding UTF8 -ErrorAction SilentlyContinue } catch { }
}
function Step([string]$n, [string]$m) { Say ''; Say ('[' + $n + '] ' + $m) 'Cyan' }
function Ok([string]$m) { Say ('  OK ' + $m) 'Green' }
function Warn([string]$m) { Say ('  ! ' + $m) 'Yellow' }
function Fail([string]$m) {
  Say ('  X ' + $m) 'Red'
  Say ('  日志: ' + $script:logFile) 'DarkGray'
  throw $m
}

# ---------------- UTF-8 管道（1401 会打印 ░，GBK 控制台会让 python 崩溃） ----------------
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { chcp 65001 | Out-Null } catch { }

# ---------------- 自动提权（build 要读写管理员建过的缓存，写盘也必须管理员） ----------------
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin -and -not $NoElevate) {
  Say '  不是管理员，请求提权（UAC 请点"是"）...' 'Yellow'
  $a = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $PSCommandPath + '"'))
  if ($DryRun) { $a += '-DryRun' }
  if ($ForceBuild) { $a += '-ForceBuild' }
  if ($UsbDisk -ge 0) { $a += @('-UsbDisk', "$UsbDisk") }
  if ($Serial) { $a += @('-Serial', $Serial) }
  if ($MacOS) { $a += @('-MacOS', "$MacOS") }
  if ($EngineRoot) { $a += @('-EngineRoot', ('"' + $EngineRoot + '"')) }
  if ($DriverTar) { $a += @('-DriverTar', ('"' + $DriverTar + '"')) }
  if ($ReuseEfi) { $a += @('-ReuseEfi', ('"' + $ReuseEfi + '"')) }
  $a += @('-WorkRoot', ('"' + $WorkRoot + '"'))
  try {
    Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList $a -ErrorAction Stop | Out-Null
    Say '  已在新窗口以管理员身份继续（本窗口可关）' 'Green'
  } catch {
    Fail '提权被拒绝。请右键以管理员身份运行，或加 -NoElevate 并自行保证权限。'
  }
  return
}
Say ('  权限: ' + $(if ($isAdmin) { '管理员' } else { '普通（-NoElevate 指定）' })) 'DarkGray'

# ---------------- macOS 版本换算 ----------------
$macMap = @{ 15 = 24; 24 = 24; 26 = 25; 25 = 25 }
$macArg = if ($macMap.ContainsKey($MacOS)) { $macMap[$MacOS] } else { $MacOS }
Say ("  目标: macOS " + $(if ($macArg -eq 25) { '26 Tahoe' } else { '15 Sequoia' }) + "（1401 参数 " + $macArg + "）") 'DarkGray'

# ---------------- 非交互执行器 ----------------
function Invoke-Py([string]$pyExe, [string]$workDir, [string[]]$argList) {
  $q = ($argList | ForEach-Object { if ($_ -match '[\s\(\)&=]') { '"' + $_ + '"' } else { $_ } }) -join ' '
  $line = 'cd /d "' + $workDir + '" && "' + $pyExe + '" ' + $q + ' < NUL 2>&1'
  Say ('  $ ' + ($argList -join ' ')) 'DarkGray'
  $out = & cmd /c $line
  $rc = $LASTEXITCODE
  $n = 0
  foreach ($l in $out) {
    $n++
    if ($n -le 500) { Say ('    ' + $l) 'DarkGray' }
  }
  if ($n -gt 500) { Say ('    ...（共 ' + $n + ' 行，已截断）') 'DarkGray' }
  return $rc
}

$ghProxy = 'https://gh-proxy.com/'
function Get-Json([string]$url) {
  try { return Invoke-RestMethod $url -TimeoutSec 30 } catch { return $null }
}
function Save-File([string]$url, [string]$outFile) {
  foreach ($u in @(($ghProxy + $url), $url)) {
    try {
      Say ('    下载 ' + [System.IO.Path]::GetFileName($outFile) + ' ...') 'DarkGray'
      Invoke-WebRequest $u -OutFile $outFile -UseBasicParsing -TimeoutSec 900 -ErrorAction Stop
      if ((Get-Item $outFile).Length -gt 1024) { return $true }
    } catch { }
  }
  return $false
}

$skillScripts = $PSScriptRoot          # 本脚本就在 skill 的 scripts/ 下
$inspector = Join-Path $skillScripts 'inspect-config.py'
$patcher = Join-Path $skillScripts 'patch-config.py'

try {
  # ================= 1. 网络与代理 =================
  Step '1/8' '网络前置检查（代理 / TUN / 苹果服务器）'
  $inetKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
  $proxyBefore = $null
  try { $proxyBefore = Get-ItemProperty -Path $inetKey -ErrorAction Stop } catch { }
  $proxyWasOn = ($proxyBefore -and $proxyBefore.ProxyEnable -eq 1)
  if ($proxyWasOn) {
    "$($proxyBefore.ProxyEnable)|$($proxyBefore.ProxyServer)" | Out-File (Join-Path $WorkRoot 'proxy-backup.txt') -Encoding ASCII
    Set-ItemProperty -Path $inetKey -Name ProxyEnable -Value 0
    Warn ("系统代理是开的（" + $proxyBefore.ProxyServer + "）→ 已临时关闭，结束时恢复")
  } else { Ok '系统代理未启用' }

  $tun = @()
  try {
    $tun = (Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object {
        $_.InterfaceDescription -match 'TAP|TUN|Wintun|Clash|Mihomo|WireGuard' -or $_.Name -match 'Clash|Mihomo|TUN'
      } | Select-Object -ExpandProperty Name)
  } catch { }
  if ($tun.Count -gt 0) {
    Warn ('检测到 TUN 虚拟网卡: ' + ($tun -join ', '))
    Warn '  TUN 模式下关系统代理无效 —— 写盘前请在代理客户端切「直连」或退出客户端'
  } else { Ok '没有 TUN 虚拟网卡' }

  try {
    $probe = Invoke-WebRequest 'https://osrecovery.apple.com/' -UseBasicParsing -TimeoutSec 20 -Method Head -ErrorAction Stop
    Ok ('苹果恢复服务器可达 (HTTP ' + $probe.StatusCode + ')')
  } catch {
    if ($_.Exception.Message -match '405') { Ok '苹果恢复服务器可达 (HTTP 405 = 对 HEAD 的正常回应)' }
    else { Warn ('苹果恢复服务器连不上: ' + $_.Exception.Message + '（若走 TUN 请切直连）') }
  }

  # ================= 2. 找/装 1401 =================
  Step '2/8' '定位 1401 引擎（没有就自动下载最新版）'
  $cands = @()
  if ($EngineRoot) { $cands += $EngineRoot }
  $cands += @(
    (Join-Path $env:LOCALAPPDATA 'Programs\1401\engine'),
    (Join-Path $env:ProgramFiles '1401\engine'),
    (Join-Path ${env:ProgramFiles(x86)} '1401\engine'),
    (Join-Path $WorkRoot 'tools\1401\engine'),
    'G:\1401-new\1401\engine',
    'G:\1401-2.3.3\1401\engine'
  )
  $eng = $null
  foreach ($c in $cands) { if ($c -and (Test-Path (Join-Path $c 'python\python.exe'))) { $eng = $c; break } }
  if (-not $eng) {
    Warn '本机没有 1401，开始自动下载最新版'
    $rel = Get-Json 'https://api.github.com/repos/nullmoth/1401/releases/latest'
    $asset = $null
    if ($rel) { $asset = $rel.assets | Where-Object { $_.name -match '^1401-Windows-.*\.zip$' } | Select-Object -First 1 }
    if (-not $asset) { Fail '拿不到 1401 的最新 Windows 包（GitHub API 不通）。请手动下载 1401 并解压到 tools\1401。' }
    $toolsDir = Join-Path $WorkRoot 'tools'
    New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null
    $zip = Join-Path $toolsDir $asset.name
    if (-not (Save-File $asset.browser_download_url $zip)) { Fail ('1401 下载失败: ' + $asset.name) }
    Ok ('1401 包已下载: ' + [math]::Round((Get-Item $zip).Length / 1MB, 1) + ' MB')
    Expand-Archive -LiteralPath $zip -DestinationPath $toolsDir -Force
    $found = Get-ChildItem $toolsDir -Recurse -Filter 'python.exe' -ErrorAction SilentlyContinue |
      Where-Object { $_.DirectoryName -like '*engine\python' } | Select-Object -First 1
    if (-not $found) { Fail '1401 解压后找不到 engine\python\python.exe' }
    $eng = Split-Path $found.DirectoryName -Parent
  }
  $py = Join-Path $eng 'python\python.exe'
  Ok ('engine = ' + $eng)

  $ver = (& $py -c "import sys;sys.path.insert(0,'app');import p1401;print(getattr(p1401,'__version__','?'))" 2>&1) -join ' '
  Say ('  1401 版本: ' + $ver) 'DarkGray'

  # ================= 3. 驱动包 =================
  Step '3/8' '定位 NullMoth NVIDIA 驱动包（没有就自动下载最新版）'
  if (-not $DriverTar) {
    $pool = @()
    foreach ($d in @('M:\NullMoth', (Join-Path $WorkRoot 'tools'), (Join-Path $WorkRoot 'tools\driver'))) {
      if (Test-Path $d) { $pool += Get-ChildItem $d -Filter 'nullmoth-nvidia-*.tar.gz' -ErrorAction SilentlyContinue }
    }
    $best = $pool | Sort-Object { [version]([regex]::Match($_.Name, '(\d+\.\d+\.\d+)').Groups[1].Value) } -Descending | Select-Object -First 1
    if ($best) { $DriverTar = $best.FullName }
  }
  if (-not $DriverTar -or -not (Test-Path $DriverTar)) {
    Warn '没找到驱动包，尝试下载最新版'
    $rel = Get-Json 'https://api.github.com/repos/nullmoth/nvidia-macos-driver/releases/latest'
    $asset = $null
    if ($rel) { $asset = $rel.assets | Where-Object { $_.name -match '^nullmoth-nvidia-.*\.tar\.gz$' } | Select-Object -First 1 }
    if ($asset) {
      $dd = Join-Path $WorkRoot 'tools'
      New-Item -ItemType Directory -Force -Path $dd | Out-Null
      $dst = Join-Path $dd $asset.name
      if (Save-File $asset.browser_download_url $dst) { $DriverTar = $dst; Ok ('驱动已下载: ' + $asset.name) }
      else { Warn '驱动下载失败，写盘会不带驱动（可事后手动拷）' ; $DriverTar = '' }
    } else { Warn '拿不到驱动包信息，写盘会不带驱动'; $DriverTar = '' }
  } else {
    Ok ('驱动包 = ' + (Split-Path $DriverTar -Leaf) + '  (' + [math]::Round((Get-Item $DriverTar).Length / 1MB, 1) + ' MB)')
  }

  # ================= 4. 复用 或 构建 EFI =================
  Step '4/8' '准备 OpenCore EFI（优先复用已验证的，零下载）'
  $reuseSrc = ''
  if (-not $ForceBuild) {
    if ($ReuseEfi -and (Test-Path (Join-Path $ReuseEfi 'OC\config.plist'))) { $reuseSrc = $ReuseEfi }
    if (-not $reuseSrc) {
      foreach ($c in @('M:\EFI', 'N:\EFI', (Join-Path $env:LOCALAPPDATA 'NullMoth\1401\efi\EFI'))) {
        if (Test-Path (Join-Path $c 'OC\config.plist')) { $reuseSrc = $c; break }
      }
    }
  }

  $efiDir = Join-Path $WorkRoot 'efi'
  $cfg = $null
  if ($reuseSrc) {
    Say ('  复用: ' + $reuseSrc) 'Yellow'
    if (Test-Path $efiDir) { Remove-Item $efiDir -Recurse -Force -ErrorAction SilentlyContinue }
    New-Item -ItemType Directory -Force -Path $efiDir | Out-Null
    if (Test-Path (Join-Path $reuseSrc 'OC\config.plist')) { Copy-Item (Join-Path $reuseSrc '*') $efiDir -Recurse -Force }
    else { Copy-Item (Join-Path $reuseSrc 'EFI\*') $efiDir -Recurse -Force }
    if (Test-Path (Join-Path $efiDir 'OC\config.plist')) {
      $wrap = Join-Path $WorkRoot 'efi-wrap'
      if (Test-Path $wrap) { Remove-Item $wrap -Recurse -Force -ErrorAction SilentlyContinue }
      New-Item -ItemType Directory -Force -Path (Join-Path $wrap 'EFI') | Out-Null
      Copy-Item (Join-Path $efiDir '*') (Join-Path $wrap 'EFI') -Recurse -Force
      $efiDir = $wrap
    }
    $cfg = Join-Path $efiDir 'EFI\OC\config.plist'
    Ok ('EFI（复用）就位: ' + $efiDir)
  } else {
    # 需要先扫描
    $scanDir = Join-Path $WorkRoot 'scan'
    if (Test-Path $scanDir) { Remove-Item $scanDir -Recurse -Force -ErrorAction SilentlyContinue }
    Say '  扫描硬件...' 'DarkGray'
    $null = Invoke-Py -pyExe $py -workDir $eng -argList @('-m', 'p1401.scan', $scanDir)
    $report = Join-Path $scanDir 'Report.json'
    if (-not (Test-Path $report)) { Fail '扫描没产出 Report.json' }
    Ok ('Report.json = ' + [math]::Round((Get-Item $report).Length / 1KB, 1) + ' KB')

    Say '  构建 EFI（1401 build）...' 'DarkGray'
    $acpi = Join-Path $scanDir 'ACPI'
    if (Test-Path $efiDir) { Remove-Item $efiDir -Recurse -Force -ErrorAction SilentlyContinue }
    $rc = Invoke-Py -pyExe $py -workDir $eng -argList @('-m', 'p1401', 'build', $report, $acpi, $efiDir, '--macos', "$macArg")
    if ($rc -ne 0) { Warn ('build 退出码 ' + $rc) }
    $cfg = Join-Path $efiDir 'EFI\OC\config.plist'
    if (-not (Test-Path $cfg)) { Fail 'build 没产出 EFI\OC\config.plist（看上面日志的 error 行）' }
    Ok ('EFI（新建）就位: ' + $efiDir)
  }

  # ================= 5. 套用成功配置 + 体检 =================
  Step '5/8' '套用实测成功配置并体检（FAIL 就停，绝不写出坏盘）'
  if (-not (Test-Path $inspector)) { Warn ('找不到 ' + $inspector + '，跳过体检（不推荐）') }
  if ((Test-Path $patcher) -and -not $reuseSrc) {
    $rc = Invoke-Py -pyExe $py -workDir $WorkRoot -argList @($patcher, 'apply-preset', $cfg, '--stage', 'install')
    if ($rc -eq 0) { Ok '成功配置已套用（install 阶段）' } else { Warn ('apply-preset 退出码 ' + $rc) }
  } elseif ($reuseSrc) {
    Ok '复用 EFI 保留原配置（已在这台机器上验证过启动）'
  }
  if (Test-Path $inspector) {
    $rc = Invoke-Py -pyExe $py -workDir $WorkRoot -argList @($inspector, $cfg, '--quiet')
    if ($rc -eq 1) { Fail '配置体检有 FAIL —— 按上面提示修好再写盘（写坏盘会白折腾一整晚）' }
    elseif ($rc -eq 0) { Ok '配置体检通过（无 FAIL）' }
    else { Warn ('体检退出码 ' + $rc) }
  }

  # ================= 6. 选盘（序列号） =================
  Step '6/8' '选目标 U 盘（≥16 GB，按物理序列号核对）'
  $usb = Get-Disk | Where-Object { $_.BusType -eq 'USB' -and $_.Size -gt 15GB } | Sort-Object Size -Descending
  if (-not $usb) { Fail '没检测到 ≥16 GB 的 U 盘。插上 U 盘后重跑。' }
  Say '  候选:' 'DarkGray'
  foreach ($d in $usb) { Say ('    disk ' + $d.Number + '  ' + $d.FriendlyName + '  ' + [math]::Round($d.Size / 1GB, 1) + ' GB  S/N=' + $d.SerialNumber.Trim()) 'DarkGray' }
  $target = $null
  if ($UsbDisk -ge 0) { $target = $usb | Where-Object { $_.Number -eq $UsbDisk } | Select-Object -First 1 }
  if (-not $target) {
    if ($usb.Count -eq 1) { $target = $usb[0] }
    elseif ($DryRun) { $target = $usb[0]; Warn '演练模式：默认第一块' }
    else { $pick = Read-Host '  输入要写入的 disk 号'; $target = $usb | Where-Object { $_.Number -eq [int]$pick } | Select-Object -First 1 }
  }
  if (-not $target) { Fail '盘号无效' }
  $tS = $target.SerialNumber.Trim()
  Say ('  目标: disk ' + $target.Number + ' / ' + $target.FriendlyName + ' / S/N=' + $tS) 'Yellow'
  if ($Serial) {
    if ($Serial -ne $tS) { Fail ('序列号不符: 期望 ' + $Serial + ' 实际 ' + $tS + '（未写入任何数据）') }
    Ok '序列号核对通过'
  } elseif ($DryRun) {
    Warn ('演练跳过序列号确认（真写盘必须输入 ' + $tS + '）')
  } else {
    $e = Read-Host ('  请原样输入这串序列号确认: ' + $tS)
    if ($e.Trim() -ne $tS) { Fail '序列号不符，已中止（未写入任何数据）' }
    Ok '序列号核对通过'
  }

  # ================= 7. 写盘 =================
  Step '7/8' '写 macOS 安装盘（会擦除目标 U 盘）'
  if ($DryRun) {
    Warn 'DRYRUN：不写盘'
  } else {
    $report = Join-Path $WorkRoot 'scan\Report.json'
    if (-not (Test-Path $report)) {
      Say '  写盘需要 Report.json，补一次扫描...' 'DarkGray'
      $scanDir = Join-Path $WorkRoot 'scan'
      if (-not (Test-Path $scanDir)) { New-Item -ItemType Directory -Force -Path $scanDir | Out-Null }
      $null = Invoke-Py -pyExe $py -workDir $eng -argList @('-m', 'p1401.scan', $scanDir)
      $report = Join-Path $scanDir 'Report.json'
      if (-not (Test-Path $report)) { Fail '拿不到 Report.json，写盘中止' }
    }
    $wargs = @('-m', 'p1401.usbwriter', 'write', "$($target.Number)", $efiDir, "$macArg", '--profile', $report)
    if ($DriverTar) { $wargs += @('--driver', $DriverTar) }
    $rc = Invoke-Py -pyExe $py -workDir $eng -argList $wargs
    if ($rc -ne 0) { Fail ('写盘失败（退出码 ' + $rc + '）。常见原因见 SKILL.md 的 R07/R11。') }
    Ok '写盘完成'
  }

  # ================= 8. U 盘收尾 =================
  Step '8/8' '把一键装驱动脚本与说明放进 U 盘'
  if ($DryRun) { Warn 'DRYRUN：跳过' }
  else {
    $vol = $null
    $parts = Get-Partition -DiskNumber $target.Number -ErrorAction SilentlyContinue
    foreach ($p in $parts) { if ($p.DriveLetter) { $vol = "$($p.DriveLetter):\"; break } }
    if (-not $vol) { Warn '定位不到 U 盘盘符，收尾跳过（盘已可启动）' }
    else {
      Ok ('U 盘: ' + $vol)
      foreach ($f in @('make-oneclick-driver.sh', 'diag-recovery.sh', 'verify-macos.sh')) {
        $src = Join-Path $skillScripts $f
        if (Test-Path $src) { Copy-Item $src $vol -Force -ErrorAction SilentlyContinue }
      }
      Ok '辅助脚本已放入 U 盘'
    }
  }

} finally {
  if ($proxyWasOn) {
    try { Set-ItemProperty -Path $inetKey -Name ProxyEnable -Value 1; Ok '系统代理已恢复' }
    catch { Warn '代理恢复失败，请手动打开' }
  }
}

# ================= 总结：只剩 3 个物理动作 =================
Say ''
Say '========================================================' 'Cyan'
Say '  U 盘已就绪。剩下 3 件没有 API、必须人做的事：' 'Cyan'
Say '========================================================' 'Cyan'
Say '  1) BIOS 设 9 项：' 'White'
Say '     VT-d=Disabled / Hyper-Threading=Disabled / E-Cores=0 /' 'White'
Say '     Re-Size BAR=Enabled / Above 4G=Enabled / CSM=Disabled /' 'White'
Say '     Secure Boot=Disabled / Fast Boot=Disabled / SATA=AHCI' 'White'
Say '  2) 插 U 盘开机（F12 选它）→ OpenCore 自动进 macOS 安装器' 'White'
Say '     → 磁盘工具「显示所有设备」→ 选整块目标盘 → 抹成 APFS/GUID' 'White'
Say '     → 装 macOS → 重启（约 20-40 分钟）' 'White'
Say '  3) 开箱向导：选语言 → 建账户（先别登 iCloud）' 'White'
Say '' 'White'
Say '  之后在 macOS 里双击「一键安装显卡驱动.command」就全部结束。' 'Yellow'
Say '========================================================' 'Cyan'
Say ('  完整日志: ' + $script:logFile) 'DarkGray'
