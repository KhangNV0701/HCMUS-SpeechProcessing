# Export slides.pptx -> slides.pdf with Microsoft PowerPoint (Windows).
#   powershell -ExecutionPolicy Bypass -File docs/slides/export_pdf.ps1 [-Png]
param([switch]$Png)
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$pptx = Join-Path $here "slides.pptx"
$pdf  = Join-Path $here "slides.pdf"
$app = New-Object -ComObject PowerPoint.Application
try {
    $deck = $app.Presentations.Open($pptx, $true, $false, $false)
    $deck.SaveAs($pdf, 32)          # 32 = ppSaveAsPDF
    if ($Png) {
        $dir = Join-Path $here "png"
        New-Item -ItemType Directory -Force $dir | Out-Null
        $deck.Export($dir, "PNG", 1600, 900)
    }
    $deck.Close()
    Write-Output "exported $pdf"
} finally {
    $app.Quit()
}
