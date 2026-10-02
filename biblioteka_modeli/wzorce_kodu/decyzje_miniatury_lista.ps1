$ErrorActionPreference = 'Continue'
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices; using System.Drawing;
public static class Thumb4 {
 [ComImport, Guid("bcc18b79-ba16-442f-80c4-8a59c30c463b"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
 interface IShellItemImageFactory { [PreserveSig] int GetImage(SIZE size, int flags, out IntPtr phbm); }
 [StructLayout(LayoutKind.Sequential)] struct SIZE { public int cx, cy; }
 [DllImport("shell32.dll", CharSet=CharSet.Unicode, PreserveSig=false)] static extern void SHCreateItemFromParsingName(string p, IntPtr pbc, ref Guid riid, [MarshalAs(UnmanagedType.Interface)] out IShellItemImageFactory f);
 public static Bitmap Get(string path, int sz) {
  Guid g = new Guid("bcc18b79-ba16-442f-80c4-8a59c30c463b"); IShellItemImageFactory f; SHCreateItemFromParsingName(path, IntPtr.Zero, ref g, out f);
  IntPtr h; SIZE s = new SIZE(); s.cx = sz; s.cy = sz; int hr = f.GetImage(s, 0x8, out h); if (hr != 0) return null; return Image.FromHbitmap(h); }
}
'@ -ReferencedAssemblies System.Drawing
$E = 'G:\Mój dysk\SUBIEKT\Elesa'
$S = 'C:\Users\mongo\AppData\Local\Temp\claude\C--Users-mongo-Documents-Finanse\adc06e96-b93e-4d14-a36d-131ee88ec0fe\scratchpad\thumbs'
Remove-Item $S -Recurse -Force -ErrorAction SilentlyContinue; New-Item -ItemType Directory $S | Out-Null
$groups = @(@('zrobione', $E, $true), @('do_decyzji', "$E\_do_decyzji", $false), @('w_bibliotece', "$E\_juz_w_bibliotece", $false), @('rzadkie', "$E\_rzadkie", $false))
$rows = @()
foreach ($g in $groups) {
  $dirs = Get-ChildItem $g[1] -Directory | ? { $g[2] -eq $false -or ($_.Name -notmatch '^_' -and $_.Name -ne 'miniatury') } | Sort-Object Name
  $n = 0
  foreach ($d in $dirs) {
    $n++
    $files = @(Get-ChildItem $d.FullName -File)
    $main = $files | ? { $_.Extension -eq '.iam' } | select -First 1
    if (-not $main) { $main = $files | ? { $_.Extension -eq '.ipt' } | select -First 1 }
    if (-not $main) { $main = $files | ? { $_.Extension -in '.stp', '.step' } | select -First 1 }
    $png = ''
    if ($main -and $main.Extension -ne '.stp' -and $main.Extension -ne '.step') {
      $b = [Thumb4]::Get($main.FullName, 200)
      if ($b) { $png = "$S\$($g[0])__$n.png"; $b.Save($png); $b.Dispose() }
    }
    $rows += [pscustomobject]@{ grupa = $g[0]; nr = $n; nazwa = $d.Name; plik = $(if ($main) { $main.Name } else { '' }); ext = $(if ($main) { $main.Extension } else { '' }); liczba_plikow = $files.Count; png = $png }
  }
}
$rows | Export-Csv "$S\manifest.csv" -Delimiter ';' -Encoding UTF8 -NoTypeInformation
$rows | group grupa | % { "$($_.Name): $($_.Count), z miniaturą: $(($_.Group | ? { $_.png }).Count)" }
