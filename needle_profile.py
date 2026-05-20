"""
Nalewak MENGIBAR — igła na fazce kryzy
--------------------------------------
Wymiary szacowane z proporcji rysunku złożeniowego (skala 0.75):
  - ø wewnętrzny korpusu    = 50mm  (podany)
  - ø dyszy                 = 10mm  (podany)
  - ø uszczelnienia         ≈ 13mm  (igła siada na fazce, trochę więcej niż dysza)
  - kąt stożka czepca α     ≈ 12°
  - kąt fazki kryzy β       ≈ 45°
  - max ø czepca            ≈ 20mm  (suwak góra = oring 48×3 → niżej czepiec dużo węższy)
  - długość czepca           ≈ 70mm
  - skok suwaka              = 10mm  (podany)
"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Arc, FancyArrowPatch

# ============================================================
# PARAMETRY
# ============================================================
rho     = 990.0      # gęstość płynu [kg/m³]
dP      = 0.2e5      # ciśnienie [Pa]
Q_cel   = 0.2e-3     # docelowy przepływ [m³/s]
g       = 9.81

# Kryza + fazka
R_nozzle = 5e-3      # promień otworu dyszy [m]
R_seal   = 6.5e-3    # promień uszczelnienia (igła na fazce) [m]  ← z proporcji
alpha_deg = 12.0     # półkąt stożka czepca [°]
beta_deg  = 45.0     # półkąt fazki kryzy [°]
h_max    = 10e-3     # max skok suwaka [m]

# Czepiec (kształt w korpusie)
R_body   = 25e-3     # promień wewnętrzny korpusu [m]
R_czep   = 10e-3     # max promień czepca [m]  ← z proporcji
L_czep   = 70e-3     # długość czepca [m]      ← z proporcji
n_czep   = 2.5       # wykładnik kształtu (>1 = wypukły jak w Mengibar)

# Kryza — kształt korpusu dolnego (egg-shape)
L_body   = 80e-3     # długość strefy dolnej korpusu [m]
n_body   = 0.5       # wykładnik (0.5 = eliptyczny, dopasowany do egg-shape na rysunku)

Cd       = 0.65

# ============================================================
# GEOMETRIA KRYZY — A(h) na fazce
# ============================================================
alpha = np.radians(alpha_deg)
beta  = np.radians(beta_deg)
diff  = beta - alpha   # musi być > 0 dla uszczelnienia

N_h   = 300
h_arr = np.linspace(0, h_max, N_h)

# Pole szczeliny pierścieniowej na fazce (wzór na zawór stożkowy):
# A(h) = π * d_seal * h * sin(β - α)
A_kryza = np.pi * 2 * R_seal * h_arr * np.sin(diff)

# Przepływ (przy stałym ΔP):
v_tor   = np.sqrt(2 * dP / rho)
Q_h     = Cd * A_kryza * v_tor
Q_h     = np.minimum(Q_h, Q_cel * 2)   # fizyczny limit

# Prędkość na wylocie dyszy
A_nozzle = np.pi * R_nozzle**2
v_out    = Q_h / A_nozzle

# Przyspieszenie temporalne przy otwieraniu
dh      = h_arr[1] - h_arr[0]
dvdh    = np.gradient(v_out, dh)
vs_max  = g / np.max(np.abs(dvdh[2:-2]))
t_min   = h_max / vs_max

# Skok przy Q = Q_cel
if np.max(Q_h) >= Q_cel:
    h_Qcel = h_arr[np.argmin(np.abs(Q_h - Q_cel))] * 1000
else:
    h_Qcel = None

print("=" * 60)
print("KRYZA + FAZKA")
print("=" * 60)
print(f"  α czepiec          = {alpha_deg}°")
print(f"  β fazka            = {beta_deg}°")
print(f"  β - α              = {beta_deg - alpha_deg}°  (kąt szczeliny)")
print(f"  R_seal             = {R_seal*1000:.1f} mm")
print(f"  A przy h=10mm      = {A_kryza[-1]*1e6:.2f} mm²")
print(f"  Q przy h=10mm      = {Q_h[-1]*1000:.3f} L/s")
if h_Qcel:
    print(f"  Skok dla Q_cel     = {h_Qcel:.2f} mm")
else:
    print(f"  Q_cel {Q_cel*1000:.2f} L/s nieosiągalne — zmień R_seal lub kąty")
print(f"  v_wylot przy h_max = {v_out[-1]:.2f} m/s")
print(f"  Charakt. progresywna: ", end="")
d2 = np.gradient(np.gradient(A_kryza, h_arr), h_arr)
print("TAK ✓" if d2[5] > 0 else "NIE — liniowa (stożkowe uszczelnienie = liniowe A(h))")
print()
print(f"  Warunek a ≤ g:")
print(f"    v_suwak ≤ {vs_max*1000:.2f} mm/s")
print(f"    czas otwarcia ≥ {t_min:.2f} s")

# ============================================================
# PRZEKRÓJ CZEPCA W KORPUSIE
# ============================================================
N     = 500
z_arr = np.linspace(0, L_czep, N)
t_arr = z_arr / L_czep

# Czepiec: r(z) — wypukły (n>1), od R_czep do 0
r_czep = R_czep * (1 - t_arr**n_czep)

# Korpus dolny: r_body(z) — egg-shape
t_body = np.linspace(0, 1, N)
z_body = t_body * L_body
r_body_wall = R_body * np.sqrt(1 - t_body**2) + R_nozzle * t_body  # elipsa + nozzle

# Pole pierścienia wzdłuż czepca (przepływ obejściowy)
A_annular = np.pi * (r_body_wall[:N]**2 - r_czep**2)
A_annular = np.maximum(A_annular, 1e-12)
v_annular = Q_cel / A_annular
a_annular = np.abs(v_annular * np.gradient(v_annular, z_arr[1]-z_arr[0]))

print()
print("=" * 60)
print("PRZEPŁYW W KORPUSIE (wokół czepca)")
print("=" * 60)
print(f"  Luz czepiec-korpus u góry: {(R_body-R_czep)*1000:.1f} mm")
print(f"  v wlotowa (góra):          {v_annular[0]:.3f} m/s")
print(f"  Max a w korpusie:          {np.max(a_annular[:-10]):.1f} m/s²")
print(f"  Dominuje: {'kryza (OK)' if np.max(a_annular[:-10]) < 50 else 'korpus ma za gwałtowne zwężenie'}")

# ============================================================
# WYKRESY
# ============================================================
h_mm  = h_arr * 1000
z_mm  = z_arr * 1000
z_b   = z_body * 1000

fig, axes = plt.subplots(2, 3, figsize=(16, 10))
fig.suptitle(
    f'Nalewak MENGIBAR — igła na fazce kryzy\n'
    f'α={alpha_deg}°  β={beta_deg}°  R_seal={R_seal*1000:.1f}mm  '
    f'ø_dyszy={R_nozzle*2000:.0f}mm  ø_bore={R_body*2000:.0f}mm  skok={h_max*1000:.0f}mm',
    fontsize=12, fontweight='bold'
)

# 1. PRZEKRÓJ PODŁUŻNY
ax = axes[0, 0]
# Korpus (egg-shape)
ax.fill_betweenx(z_b,  r_body_wall*1000,  r_body_wall*1000+5, color='#795548', alpha=0.7)
ax.fill_betweenx(z_b, -r_body_wall*1000-5, -r_body_wall*1000, color='#795548', alpha=0.7)
ax.plot( r_body_wall*1000, z_b, 'k-', lw=2)
ax.plot(-r_body_wall*1000, z_b, 'k-', lw=2)
# Czepiec
ax.fill_betweenx(z_mm, -r_czep*1000, r_czep*1000, color='#1565C0', alpha=0.5, label='Czepiec')
ax.plot( r_czep*1000, z_mm, 'b-', lw=2.5)
ax.plot(-r_czep*1000, z_mm, 'b-', lw=2.5)
# Kryza
kryza_z = L_czep * 1000
ax.fill_betweenx([kryza_z, kryza_z+6],  R_nozzle*1000,  R_body*1000, color='#F57F17', alpha=0.5)
ax.fill_betweenx([kryza_z, kryza_z+6], -R_body*1000, -R_nozzle*1000, color='#F57F17', alpha=0.5, label='Kryza')
# Fazka
faz_r = np.array([R_nozzle*1000, R_seal*1000])
faz_z = np.array([kryza_z+6, kryza_z])
ax.plot( faz_r, faz_z, 'm-', lw=3, label=f'Fazka β={beta_deg}°')
ax.plot(-faz_r, faz_z, 'm-', lw=3)
# Zaznaczenie uszczelnienia
ax.plot([R_seal*1000], [kryza_z], 'ro', ms=8, zorder=5, label=f'R_seal={R_seal*1000:.1f}mm')
ax.plot([-R_seal*1000], [kryza_z], 'ro', ms=8, zorder=5)
# Pierścień przepływu
ax.fill_betweenx(z_mm, r_czep*1000, r_body_wall[:N]*1000,
                 color='#4FC3F7', alpha=0.2, label='Pierścień')

ax.set_xlabel('Promień r [mm]')
ax.set_ylabel('Głębokość z [mm]  (0=góra)')
ax.set_title('Przekrój podłużny\nczepiec w korpusie dolnym')
ax.legend(fontsize=7, loc='lower right')
ax.grid(True, alpha=0.2)
ax.set_xlim(-35, 35)
ax.invert_yaxis()
ax.set_aspect('equal')

# 2. POLE SZCZELINY A(h)
ax = axes[0, 1]
ax.plot(h_mm, A_kryza*1e6, 'r-', lw=2.5)
ax.axhline(A_nozzle*1e6, color='k', ls=':', alpha=0.4, label=f'A_dysza={A_nozzle*1e6:.1f}mm²')
ax.set_xlabel('Skok h [mm]')
ax.set_ylabel('Pole szczeliny A [mm²]')
ax.set_title(f'A(h) = π·d_seal·h·sin(β-α)\nsin({beta_deg-alpha_deg}°) = {np.sin(diff):.3f}')
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)
# Adnotacja — liniowość
ax.text(0.05, 0.6, 'Uszczelnienie stożkowe\n→ A(h) liniowe\n→ Q(h) liniowe',
        transform=ax.transAxes, fontsize=9,
        bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

# 3. PRZEPŁYW Q(h)
ax = axes[0, 2]
ax.plot(h_mm, Q_h*1000, 'r-', lw=2.5, label='Q(h)')
ax.axhline(Q_cel*1000, color='k', ls='--', lw=1.5, label=f'Q_cel={Q_cel*1000:.2f} L/s')
if h_Qcel:
    ax.axvline(h_Qcel, color='green', ls='-.', lw=1.5, label=f'h={h_Qcel:.1f}mm → Q_cel')
ax.set_xlabel('Skok h [mm]')
ax.set_ylabel('Przepływ Q [L/s]')
ax.set_title('Charakterystyka Q(h)')
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)

# 4. PRĘDKOŚĆ WYLOTOWA
ax = axes[1, 0]
ax.plot(h_mm, v_out, 'r-', lw=2.5)
ax.axhline(v_tor*Cd, color='orange', ls=':', lw=1.5, label=f'v_szczelina={v_tor*Cd:.2f} m/s')
ax.set_xlabel('Skok h [mm]')
ax.set_ylabel('Prędkość wylotowa [m/s]')
ax.set_title('Prędkość na wylocie dyszy')
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)

# 5. PRZYSPIESZENIE PRZESTRZENNE w korpusie
ax = axes[1, 1]
a_plot = a_annular[:-10]
z_plot = z_mm[:-10]
ok  = a_plot <= g
bad = ~ok
ax.fill_betweenx(z_plot, 0, a_plot, where=ok,  color='green', alpha=0.2, label='a ≤ g ✓')
ax.fill_betweenx(z_plot, 0, a_plot, where=bad, color='red',   alpha=0.25, label='a > g ✗')
ax.plot(a_plot, z_plot, 'b-', lw=2)
ax.axvline(g, color='k', ls='--', lw=2, label=f'g={g} m/s²')
ax.set_xlabel('Przyspieszenie [m/s²]')
ax.set_ylabel('Głębokość z [mm]')
ax.set_title('Przyspieszenie w pierścieniu\nwokół czepca')
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)
ax.invert_yaxis()

# 6. SCHEMAT KRYZY + KĄTY
ax = axes[1, 2]
ax.set_aspect('equal')
ax.set_xlim(-15, 15)
ax.set_ylim(-8, 8)

# Kryza — przekrój
kryza_h = 4
ax.fill_between([-15, -R_nozzle*1000], [-kryza_h, -kryza_h], [0, 0],
                color='#795548', alpha=0.7)
ax.fill_between([ R_nozzle*1000,  15], [-kryza_h, -kryza_h], [0, 0],
                color='#795548', alpha=0.7)
# Fazka
ax.plot([-R_seal*1000, -R_nozzle*1000], [0, -kryza_h*0.6], 'm-', lw=3)
ax.plot([ R_nozzle*1000,  R_seal*1000], [-kryza_h*0.6, 0], 'm-', lw=3)

# Czepiec (stożek)
tip_h = 6
cone_r = tip_h * np.tan(alpha)
ax.plot([-cone_r*1000, 0, cone_r*1000], [tip_h, 0, tip_h], 'b-', lw=3, label=f'Czepiec α={alpha_deg}°')

# Szczelina h=5mm (połowa skoku)
h_ex = 5e-3
ax.annotate('', xy=(R_seal*1000, h_ex*1000), xytext=(R_seal*1000, 0),
            arrowprops=dict(arrowstyle='<->', color='green', lw=2))
ax.text(R_seal*1000+1, h_ex*500, f'h', fontsize=11, color='green', fontweight='bold')

# Kąty
arc_b = Arc((R_nozzle*1000, -kryza_h*0.6), 6, 6, angle=0,
            theta1=90, theta2=90+beta_deg, color='m', lw=2)
ax.add_patch(arc_b)
ax.text(R_nozzle*1000+0.5, -kryza_h*0.6+3.5, f'β={beta_deg}°', color='m', fontsize=9)

arc_a = Arc((0, 0), 10, 10, angle=0, theta1=90-alpha_deg, theta2=90, color='b', lw=2)
ax.add_patch(arc_a)
ax.text(2, 4, f'α={alpha_deg}°', color='b', fontsize=9)

# Linia styku
ax.plot([R_seal*1000], [0], 'ro', ms=10, zorder=5)
ax.plot([-R_seal*1000], [0], 'ro', ms=10, zorder=5, label=f'Uszczeln. R={R_seal*1000:.1f}mm')

ax.axhline(0, color='k', lw=0.5, alpha=0.3)
ax.axvline(0, color='k', lw=0.5, ls='--', alpha=0.3)
ax.set_title(f'Schemat kryzy + fazka\nβ-α = {beta_deg-alpha_deg}° → sin={np.sin(diff):.3f}')
ax.legend(fontsize=8, loc='upper right')
ax.grid(True, alpha=0.2)
ax.set_xlabel('r [mm]')
ax.set_ylabel('z [mm]')

plt.tight_layout()
out = r'c:\RMPAK_CLIENT\Repozytoria\RM-BAZA-MANAGER\needle_analysis.png'
plt.savefig(out, dpi=150, bbox_inches='tight')
print(f'\n✅ Zapisano: {out}')
