[CmdletBinding(DefaultParameterSetName='Identifier')]
param(
    [Parameter(Mandatory,ParameterSetName='Identifier')]
    [string]$Identifier,

    [Parameter(Mandatory,ParameterSetName='Key')]
    [ValidatePattern('^[A-Z0-9]{8}$')]
    [string]$ItemKey,

    [string]$DataDirectory
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$api = 'http://127.0.0.1:23119/api/users/0/items'

function Read-ZoteroJson([string]$Url) {
    $body = & curl.exe --noproxy '*' -fsS --connect-timeout 5 --max-time 25 $Url
    if ($LASTEXITCODE -ne 0) {
        throw "Zotero Local API GET failed at $Url (curl exit $LASTEXITCODE)."
    }
    ConvertFrom-Json -InputObject ($body -join [Environment]::NewLine) -ErrorAction Stop
}

function Resolve-Doi([string]$Text) {
    if (!$Text) { return '' }
    ($Text.Trim() -replace '(?i)^(https?://(?:dx\.)?doi\.org/|doi:\s*)','').Trim()
}

function Normalize-Title([string]$Text) {
    if (!$Text) { return '' }
    (($Text.Trim() -replace '\s+',' ').Normalize([Text.NormalizationForm]::FormC))
}

if ($ItemKey) {
    $matched = @(Read-ZoteroJson "$api/$ItemKey")
    if ($matched.Count -ne 1 -or $matched[0].key -ne $ItemKey -or $matched[0].data.itemType -in @('attachment','note','annotation')) {
        throw 'The supplied key did not resolve to a publication item.'
    }
} else {
    $needle = Resolve-Doi $Identifier
    $isDoi = $needle -match '^10\.\d{4,9}/\S+$'
    $encoded = [Uri]::EscapeDataString($needle)
    $matched = @(
        Read-ZoteroJson "$api/top?q=$encoded&limit=100" | Where-Object {
            if ($isDoi) { (Resolve-Doi $_.data.DOI) -eq $needle }
            else { (Normalize-Title $_.data.title) -eq (Normalize-Title $Identifier) }
        }
    )
    if (!$matched.Count) {
        for ($start = 0; ; $start += 100) {
            $page = @(Read-ZoteroJson "$api/top?limit=100&start=$start")
            $matched += @($page | Where-Object {
                if ($isDoi) { (Resolve-Doi $_.data.DOI) -eq $needle }
                else { (Normalize-Title $_.data.title) -eq (Normalize-Title $Identifier) }
            })
            if ($page.Count -lt 100) { break }
        }
    }
}
if (!$matched.Count) { throw 'No exact title or DOI match found in Zotero.' }

$directories = @()
if ($DataDirectory) { $directories += $DataDirectory }
$profileRoot = Join-Path $env:APPDATA 'Zotero\Zotero\Profiles'
if (Test-Path -LiteralPath $profileRoot -PathType Container) {
    foreach ($pref in Get-ChildItem -LiteralPath $profileRoot -Directory | ForEach-Object { Join-Path $_.FullName 'prefs.js' }) {
        if (!(Test-Path -LiteralPath $pref -PathType Leaf)) { continue }
        $config = Get-Content -Raw -LiteralPath $pref -Encoding utf8
        $entry = [regex]::Match($config,'(?m)^user_pref\("extensions\.zotero\.dataDir",\s*("(?:\\.|[^"\\])*")\);')
        if ($entry.Success) { $directories += ConvertFrom-Json -InputObject $entry.Groups[1].Value }
    }
}
$directories += Join-Path $env:USERPROFILE 'Zotero'

$output = foreach ($item in $matched) {
    $children = @(Read-ZoteroJson "$api/$($item.key)/children?limit=100")
    $pdfs = @(foreach ($child in $children) {
        $attachment = $child.data
        if ($attachment.itemType -ne 'attachment' -or
            ($attachment.contentType -ne 'application/pdf' -and $attachment.filename -notmatch '\.pdf$')) { continue }
        $paths = @(if ($attachment.path -and [IO.Path]::IsPathRooted($attachment.path) -and
            (Test-Path -LiteralPath $attachment.path -PathType Leaf)) {
            (Get-Item -LiteralPath $attachment.path).FullName
        }
        if ($attachment.key -match '^[A-Z0-9]{8}$' -and $attachment.filename -and
            [IO.Path]::GetFileName($attachment.filename) -eq $attachment.filename) {
            foreach ($dir in $directories) {
                $candidate = Join-Path $dir "storage\$($attachment.key)\$($attachment.filename)"
                if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                    (Get-Item -LiteralPath $candidate).FullName
                }
            }
        })
        [pscustomobject]@{
            key = $attachment.key
            title = $attachment.title
            linkMode = $attachment.linkMode
            filename = $attachment.filename
            localPaths = @($paths | Select-Object -Unique)
        }
    })
    $itemData = $item.data
    [pscustomobject]@{
        key = $item.key
        library = $item.library
        title = $itemData.title
        doi = $itemData.DOI
        date = $itemData.date
        journal = $itemData.publicationTitle
        creators = $itemData.creators
        pdfs = $pdfs
    }
}
ConvertTo-Json -InputObject @($output) -Depth 8
