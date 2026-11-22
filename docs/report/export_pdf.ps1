# Update the table of contents / fields in report.docx and export report.pdf with Microsoft Word.
#   powershell -ExecutionPolicy Bypass -File docs/report/export_pdf.ps1
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$docx = Join-Path $here "report.docx"
$pdf  = Join-Path $here "report.pdf"
$word = New-Object -ComObject Word.Application
$word.Visible = $false
try {
    $doc = $word.Documents.Open($docx)
    foreach ($id in -20, -21) {          # wdStyleTOC1, wdStyleTOC2: compact single-spaced entries
        $pf = $doc.Styles.Item($id).ParagraphFormat
        $pf.SpaceAfter = 2
        $pf.SpaceBefore = 0
        $pf.LineSpacingRule = 0
    }
    $doc.Fields.Update() | Out-Null
    foreach ($toc in $doc.TablesOfContents) { $toc.Update() }
    $doc.Save()
    $doc.ExportAsFixedFormat([string]$pdf, 17)   # 17 = wdExportFormatPDF
    $doc.Close()
    Write-Output "exported $pdf"
} finally {
    $word.Quit()
}
