$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$zip = Join-Path $repo "downloads\AI-Stamp-Collection-Scanner-v2.1.zip"
if(-not (Test-Path $zip)){ throw "Missing v2.1 package" }
$temp = Join-Path ([IO.Path]::GetTempPath()) ("stamp-tests-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $temp | Out-Null
try {
  Expand-Archive -LiteralPath $zip -DestinationPath $temp
  $root = Get-ChildItem $temp -Directory | Select-Object -First 1
  foreach($name in "Stamp-Inventory-Template.xlsx","Stamp-Inventory-SAMPLE.xlsx","2-AI-Photo-ID-Prompt.pdf","5-Photo-Linking-and-Images-Addendum.pdf","CHANGELOG.txt"){
    if(-not (Test-Path (Join-Path $root.FullName $name))){ throw "Missing package file: $name" }
  }
  foreach($book in "Stamp-Inventory-Template.xlsx","Stamp-Inventory-SAMPLE.xlsx"){
    $bookDir = Join-Path $temp ($book -replace '\.xlsx$','')
    $bookZip = Join-Path $temp ($book + ".zip")
    Copy-Item -LiteralPath (Join-Path $root.FullName $book) -Destination $bookZip
    Expand-Archive -LiteralPath $bookZip -DestinationPath $bookDir
    $xml = (Get-ChildItem $bookDir -Recurse -Filter *.xml | Get-Content -Raw) -join "`n"
    foreach($required in "record_id","photo_number","original_filename","photo_references","stamp_image_reference","Images"){
      if($xml -notmatch [regex]::Escape($required)){ throw "$book missing $required" }
    }
    if($book -like '*SAMPLE*'){
      foreach($sample in "REC-0001","Photo 001","Photo 002"){
        if($xml -notmatch [regex]::Escape($sample)){ throw "Sample missing $sample" }
      }
    }
  }
  Write-Output "Stamp workbook package tests passed for photo links, sample IDs and fallback assets."
} finally {
  Remove-Item -LiteralPath $temp -Recurse -Force
}