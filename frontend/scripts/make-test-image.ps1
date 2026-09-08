Add-Type -AssemblyName System.Drawing
$b = New-Object System.Drawing.Bitmap(2000, 1200)
$g = [System.Drawing.Graphics]::FromImage($b)
$g.Clear([System.Drawing.Color]::FromArgb(240, 244, 250))
$g.SmoothingMode = 'AntiAlias'
$pen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(60, 80, 200), 6)
for ($i = 0; $i -lt 20; $i++) {
  $g.DrawEllipse($pen, (100 + $i * 60), (100 + $i * 40), (1400 - $i * 60), (900 - $i * 40))
}
$f = New-Object System.Drawing.Font('Segoe UI', 48)
$brush = [System.Drawing.Brushes]::Black
$g.DrawString('清晰度测试 2000px Kate-Cortex', $f, $brush, 200.0, 560.0)
$b.Save('D:\workspace\Kate-Cortex\frontend\release\test-2000px.png', [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose()
$b.Dispose()
Write-Output 'saved'
