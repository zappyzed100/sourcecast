# Sets up upstream submodules after a fresh clone.
#
# sparse-checkout is a local-only setting (not persisted in .gitmodules),
# so this script re-applies it for the emilkowalski-skills submodule.
# The list of adopted skill paths is recorded in .upstream/sources.yaml;
# keep the constants below in sync with that file.

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$skillsSubmodule = Join-Path $repoRoot 'upstream/ui-skills/emilkowalski-skills'
$designMdSubmodule = Join-Path $repoRoot 'upstream/design-md/awesome-design-md'

# Paths kept in sync with .upstream/sources.yaml (id: emil-ui-skills)
$sparsePaths = @(
    '/LICENSE'
    '/README.md'
    'skills/animation-vocabulary/'
    'skills/apple-design/'
    'skills/emil-design-eng/'
    'skills/improve-animations/'
    'skills/review-animations/'
)

# Paths kept in sync with .upstream/sources.yaml (id: awesome-design-md)
$designMdSparsePaths = @(
    '/README.md'
    '/LICENSE'
    'design-md/**/DESIGN.md'
)

Write-Host '==> Initializing submodules...'
git -C $repoRoot submodule update --init --recursive
if ($LASTEXITCODE -ne 0) { throw 'git submodule update failed' }

Write-Host '==> Applying sparse-checkout to emilkowalski-skills...'
git -C $skillsSubmodule sparse-checkout set --no-cone @sparsePaths
if ($LASTEXITCODE -ne 0) { throw 'git sparse-checkout failed' }

Write-Host '==> Checked-out contents:'
Get-ChildItem -Recurse -File $skillsSubmodule |
    ForEach-Object { $_.FullName.Substring($skillsSubmodule.Length + 1) }

Write-Host '==> Applying sparse-checkout to awesome-design-md...'
git -C $designMdSubmodule sparse-checkout set --no-cone @designMdSparsePaths
if ($LASTEXITCODE -ne 0) { throw 'git sparse-checkout failed' }

$designCount = (Get-ChildItem -Recurse -File -Filter 'DESIGN.md' $designMdSubmodule).Count
Write-Host "==> awesome-design-md: $designCount brand DESIGN.md files checked out"

Write-Host '==> Done.'
