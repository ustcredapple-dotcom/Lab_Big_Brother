param(
    [string]$NotebookName = "ZZLab Notebook",
    [switch]$Login,
    [switch]$ListNotebooks
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$GraphRoot = "https://graph.microsoft.com/v1.0"
$SyncRoot = Join-Path $Root "sources\onenote_graph"
$RawRoot = Join-Path $SyncRoot "raw"
$HtmlRoot = Join-Path $SyncRoot "html"
$TextRoot = Join-Path $SyncRoot "text"
$EntriesRoot = Join-Path $Root "entries"
$IndicesRoot = Join-Path $Root "indices"
$StatePath = Join-Path $IndicesRoot "onenote_sync_state_powershell.json"
$Stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")

function Assert-GraphModule {
    $module = Get-Module -ListAvailable Microsoft.Graph.Authentication | Select-Object -First 1
    if (-not $module) {
        throw "Microsoft.Graph.Authentication is not installed. Run: Install-Module Microsoft.Graph.Authentication -Scope CurrentUser"
    }
    Import-Module Microsoft.Graph.Authentication -ErrorAction Stop
}

function ConvertTo-Slug {
    param([string]$Value, [int]$Limit = 80)
    if (-not $Value) { $Value = "untitled" }
    $slug = $Value.ToLowerInvariant() -replace "[^a-z0-9\u4e00-\u9fff]+", "-"
    $slug = $slug.Trim("-")
    if (-not $slug) { $slug = "untitled" }
    if ($slug.Length -gt $Limit) { $slug = $slug.Substring(0, $Limit).Trim("-") }
    return $slug
}

function ConvertFrom-HtmlToText {
    param([string]$Html)
    $text = [regex]::Replace($Html, "<script[\s\S]*?</script>", "", "IgnoreCase")
    $text = [regex]::Replace($text, "<style[\s\S]*?</style>", "", "IgnoreCase")
    $text = [regex]::Replace($text, "<br\s*/?>", "`n", "IgnoreCase")
    $text = [regex]::Replace($text, "</p\s*>", "`n`n", "IgnoreCase")
    $text = [regex]::Replace($text, "<[^>]+>", "`n")
    $text = [System.Net.WebUtility]::HtmlDecode($text)
    $text = [regex]::Replace($text, "[ `t]+", " ")
    $text = [regex]::Replace($text, "(\r?\n\s*){3,}", "`n`n")
    return $text.Trim()
}

function Invoke-GraphAll {
    param([string]$Uri)
    $records = @()
    $next = $Uri
    while ($next) {
        $result = Invoke-MgGraphRequest -Method GET -Uri $next
        if ($result.value) {
            $records += $result.value
        }
        $next = $result.'@odata.nextLink'
    }
    return $records
}

function Get-GraphText {
    param([string]$Uri)
    $response = Invoke-MgGraphRequest -Method GET -Uri $Uri -OutputType HttpResponseMessage
    return $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
}

function Write-Utf8File {
    param([string]$Path, [string]$Content)
    $dir = Split-Path -Parent $Path
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    [System.IO.File]::WriteAllText($Path, $Content, [System.Text.UTF8Encoding]::new($false))
}

function Escape-Yaml {
    param([string]$Value)
    if ($null -eq $Value) { return "" }
    return $Value.Replace("\", "\\").Replace('"', '\"')
}

function ConvertTo-Hash {
    param([string]$Text)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
    $hashBytes = $sha.ComputeHash($bytes)
    return ([BitConverter]::ToString($hashBytes)).Replace("-", "").ToLowerInvariant()
}

function Load-State {
    if (-not (Test-Path -LiteralPath $StatePath)) {
        return @{ pages = @{} }
    }
    $raw = Get-Content -LiteralPath $StatePath -Raw -Encoding UTF8 | ConvertFrom-Json
    $state = @{ pages = @{} }
    if ($raw.pages) {
        foreach ($property in $raw.pages.PSObject.Properties) {
            $state.pages[$property.Name] = $property.Value
        }
    }
    return $state
}

function Save-State {
    param([hashtable]$State, [object]$Notebook, [int]$PageCount)
    $State["last_sync"] = $Stamp
    $State["notebook"] = @{
        id = $Notebook.id
        displayName = $Notebook.displayName
    }
    $State["page_count"] = $PageCount
    New-Item -ItemType Directory -Force -Path $IndicesRoot | Out-Null
    $State | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $StatePath -Encoding UTF8
}

Assert-GraphModule

$scopes = @("User.Read", "Notes.Read")
$context = Get-MgContext
if ($Login -or -not $context) {
    Connect-MgGraph -Scopes $scopes -ContextScope CurrentUser -UseDeviceCode | Out-Null
}

$notebooks = Invoke-GraphAll "$GraphRoot/me/onenote/notebooks?`$top=100"

if ($ListNotebooks) {
    foreach ($notebook in $notebooks) {
        Write-Output ("{0} | id={1}" -f $notebook.displayName, $notebook.id)
    }
    return
}

$notebook = $notebooks | Where-Object { $_.displayName -eq $NotebookName } | Select-Object -First 1
if (-not $notebook) {
    $names = ($notebooks | ForEach-Object { $_.displayName }) -join ", "
    throw "Notebook not found: $NotebookName. Visible notebooks: $names"
}

$rawDir = Join-Path $RawRoot $Stamp
New-Item -ItemType Directory -Force -Path $rawDir, $HtmlRoot, $TextRoot, $EntriesRoot, $IndicesRoot | Out-Null
$notebooks | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $rawDir "notebooks.json") -Encoding UTF8

$sections = Invoke-GraphAll $notebook.sectionsUrl
$sections | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $rawDir "sections.json") -Encoding UTF8

$pages = @()
foreach ($section in $sections) {
    if (-not $section.pagesUrl) { continue }
    $delimiter = "?"
    if ($section.pagesUrl.Contains("?")) { $delimiter = "&" }
    $sectionPages = Invoke-GraphAll ($section.pagesUrl + $delimiter + "`$top=100")
    foreach ($page in $sectionPages) {
        $page | Add-Member -NotePropertyName "_sectionName" -NotePropertyValue $section.displayName -Force
        $pages += $page
    }
}
$pages | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $rawDir "pages.json") -Encoding UTF8

$state = Load-State
$changed = 0
$skipped = 0

foreach ($page in $pages) {
    $pageId = [string]$page.id
    $modified = [string]$page.lastModifiedDateTime
    $existing = $state.pages[$pageId]
    if ($existing -and $existing.lastModifiedDateTime -eq $modified) {
        $skipped += 1
        continue
    }

    $html = Get-GraphText $page.contentUrl
    $text = ConvertFrom-HtmlToText $html
    $hash = ConvertTo-Hash $html

    $sectionSlug = ConvertTo-Slug $page._sectionName
    $pageSlug = ConvertTo-Slug $page.title
    $idSlug = ConvertTo-Slug $pageId 32
    $htmlPath = Join-Path (Join-Path $HtmlRoot $sectionSlug) "$pageSlug-$idSlug.html"
    $textPath = Join-Path (Join-Path $TextRoot $sectionSlug) "$pageSlug-$idSlug.txt"
    Write-Utf8File $htmlPath $html
    Write-Utf8File $textPath $text

    $entryId = "onenote-$idSlug"
    $entryPath = Join-Path $EntriesRoot "$entryId.md"
    $datePart = (Get-Date).ToString("yyyy-MM-dd")
    if ($modified -match "^\d{4}-\d{2}-\d{2}") {
        $datePart = $Matches[0]
    }
    $relText = [System.IO.Path]::GetRelativePath($Root, $textPath).Replace("\", "/")
    $relHtml = [System.IO.Path]::GetRelativePath($Root, $htmlPath).Replace("\", "/")
    $safeTitle = Escape-Yaml $page.title
    $safeSection = Escape-Yaml $page._sectionName
    $summary = Escape-Yaml (($page.title -replace "\s+", " ").Trim())
    $webUrl = ""
    if ($page.links -and $page.links.oneNoteWebUrl -and $page.links.oneNoteWebUrl.href) {
        $webUrl = $page.links.oneNoteWebUrl.href
    }

    $entry = @"
---
id: $entryId
title: "$safeTitle"
type: notebook_page
status: active
date: $datePart
projects: []
people: []
tags: ["onenote-graph-powershell-sync", "onenote", "$safeSection"]
source_refs: ["$relText", "$relHtml"]
confidence: high
onenote_page_id: "$pageId"
onenote_section: "$safeSection"
last_modified: "$modified"
content_hash: "$hash"
summary: "$summary"
---

## OneNote Page

- Section: ``$($page._sectionName)``
- Last modified: ``$modified``
- Web URL: $webUrl

## Extracted Text

$text
"@
    Write-Utf8File $entryPath $entry

    $state.pages[$pageId] = @{
        title = $page.title
        section = $page._sectionName
        lastModifiedDateTime = $modified
        content_hash = $hash
        html_path = $relHtml
        text_path = $relText
        entry_path = [System.IO.Path]::GetRelativePath($Root, $entryPath).Replace("\", "/")
        synced_at = $Stamp
    }
    $changed += 1
}

Save-State $state $notebook $pages.Count

Write-Output "Notebook: $($notebook.displayName)"
Write-Output "Sections: $($sections.Count)"
Write-Output "Pages: $($pages.Count)"
Write-Output "Changed pages: $changed"
Write-Output "Skipped pages: $skipped"
Write-Output "State: $StatePath"
