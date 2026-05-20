"""
Nalewak MENGIBAR — GUI projektowania profilu igły i korpusu
-----------------------------------------------------------
Obsługa:
  • Suwak "Skok h" pod przekrojem  = przesuwa igłę góra/dół
  • Przeciągaj ● czerwone  = ściana korpusu
  • Przeciągaj ● niebieskie = profil igły (czepiec)
  • PPM na canvas = dodaj punkt kontrolny
  • Ctrl + klik na punkcie = usuń punkt
  • ▶ Oblicz = wczytaj parametry i przelicz
  • ↺ Reset = przywróć domyślny kształt
"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import numpy as np
import tkinter as tk
from tkinter import ttk
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from scipy.interpolate import CubicSpline

DEFAULTS = dict(
    rho=990.0, dP=0.2, Q_cel=0.2, g=9.81,
    R_body=25.0, R_nozzle=5.0, R_seal=6.5,
    alpha=12.0, beta=45.0, h_max=10.0, L=80.0, Cd=0.65,
)

# ═══════════════════════════════════════════════════════════════
class NeedleDesigner:

    def __init__(self):
        self.p        = dict(DEFAULTS)
        self._drag    = None        # ('body'|'needle', idx)
        self._res     = None
        self.h_var    = None        # tk.DoubleVar (skok suwaka)
        self._init_cp()
        self._build_gui()
        self._recalc()
        self._draw_geo()
        self._draw_res()

    # ── punkty kontrolne ────────────────────────────────────
    def _init_cp(self):
        L, R, Rn = self.p['L'], self.p['R_body'], self.p['R_nozzle']
        self.cp_body = np.array([
            [0,      R     ],
            [L*.20,  R*.90 ],
            [L*.45,  R*.70 ],
            [L*.70,  R*.42 ],
            [L,      Rn    ],
        ], dtype=float)
        self.cp_ndl = np.array([
            [0,      R*.40 ],
            [L*.20,  R*.39 ],
            [L*.45,  R*.33 ],
            [L*.72,  R*.15 ],
            [L,      0.0   ],
        ], dtype=float)

    # ── GUI ─────────────────────────────────────────────────
    def _build_gui(self):
        root = tk.Tk()
        root.title("Nalewak MENGIBAR — Projektowanie profilu igły i korpusu")
        root.geometry("1560x920")
        root.configure(bg='#f0f0f0')
        self.root = root

        # ── pasek parametrów ──────────────────────────────
        pbar = tk.Frame(root, bg='#dde3ea', pady=5)
        pbar.pack(fill=tk.X, padx=6, pady=(6, 0))

        fields = [
            ('α igły [°]','alpha'), ('β fazki [°]','beta'),
            ('R_seal [mm]','R_seal'), ('R_nozzle [mm]','R_nozzle'),
            ('h_max [mm]','h_max'), ('Q_cel [L/s]','Q_cel'),
            ('ΔP [bar]','dP'), ('L [mm]','L'),
        ]
        self._pv = {}
        for col, (lbl, key) in enumerate(fields):
            tk.Label(pbar, text=lbl, bg='#dde3ea',
                     font=('Arial', 9)).grid(row=0, column=col*2, padx=(8,2))
            v = tk.StringVar(value=str(self.p[key]))
            tk.Entry(pbar, textvariable=v, width=7,
                     font=('Arial', 9)).grid(row=0, column=col*2+1, padx=(0,4))
            self._pv[key] = v

        nc = len(fields)*2
        tk.Button(pbar, text='▶  Oblicz', bg='#1565C0', fg='white',
                  font=('Arial', 10, 'bold'), padx=14,
                  command=self._on_calc).grid(row=0, column=nc,   padx=(14,4))
        tk.Button(pbar, text='↺  Reset',  bg='#555',    fg='white',
                  font=('Arial', 10), padx=10,
                  command=self._on_reset).grid(row=0, column=nc+1, padx=4)

        # ── główna ramka ──────────────────────────────────
        mf = tk.Frame(root, bg='#f0f0f0')
        mf.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        # ── LEWA: geometria (szersza) ──────────────────────
        lf = tk.Frame(mf, bg='#f0f0f0')
        lf.pack(side=tk.LEFT, fill=tk.BOTH, expand=False)

        title_geo = ('● czerwone = korpus   '
                     '● niebieskie = igła   '
                     '(PPM=dodaj, Ctrl+klik=usuń)')
        tk.Label(lf, text=title_geo, font=('Arial', 8), bg='#f0f0f0',
                 fg='#444').pack(anchor='w', padx=4)

        self.fig_geo = plt.Figure(figsize=(7.0, 8.2), facecolor='#fafafa')
        self.ax_geo  = self.fig_geo.add_subplot(111)
        self.cv_geo  = FigureCanvasTkAgg(self.fig_geo, master=lf)
        self.cv_geo.get_tk_widget().pack(fill=tk.BOTH, expand=False)
        self.cv_geo.mpl_connect('button_press_event',   self._on_press)
        self.cv_geo.mpl_connect('motion_notify_event',  self._on_motion)
        self.cv_geo.mpl_connect('button_release_event', self._on_release)

        # ── suwak SKOKU pod przekrojem ─────────────────────
        sf = tk.Frame(lf, bg='#e8eef4', pady=4, padx=8)
        sf.pack(fill=tk.X, padx=4, pady=(2,0))

        tk.Label(sf, text='Skok suwaka  h [mm]:', font=('Arial', 10, 'bold'),
                 bg='#e8eef4').pack(side=tk.LEFT, padx=(0,6))

        self.h_var  = tk.DoubleVar(value=0.0)
        self.h_disp = tk.StringVar(value='h = 0.0 mm')

        self.h_scale = tk.Scale(
            sf, from_=-self.p['h_max'], to=self.p['h_max'],
            orient=tk.HORIZONTAL, variable=self.h_var,
            resolution=0.1, length=380,
            showvalue=False, bg='#e8eef4',
            activebackground='#1565C0', troughcolor='#bbdefb',
            command=self._on_h
        )
        self.h_scale.pack(side=tk.LEFT)

        tk.Label(sf, textvariable=self.h_disp,
                 font=('Arial', 11, 'bold'), fg='#C62828',
                 bg='#e8eef4', width=12).pack(side=tk.LEFT, padx=8)

        # przyciski szybkiego ustawienia
        for lbl, val in [('MAX-', None), ('ZAMKNIĘTY', 0), ('½', None), ('OTWARTY', None)]:
            v = val
            if lbl == 'MAX-':    v = -self.p['h_max']
            if lbl == '½':       v = self.p['h_max']/2
            if lbl == 'OTWARTY': v = self.p['h_max']
            tk.Button(sf, text=lbl, font=('Arial', 8), padx=6,
                      bg='#e0e0e0',
                      command=lambda x=v: self._set_h(x)
                      ).pack(side=tk.LEFT, padx=2)

        # ── PRAWA: wykresy ────────────────────────────────
        rf = tk.LabelFrame(mf, text=' Wyniki obliczeń ',
                           font=('Arial', 9), bg='#f0f0f0')
        rf.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6,0))

        self.fig_res, self.axs = plt.subplots(2, 2, figsize=(8.0, 8.2),
                                              facecolor='#fafafa')
        self.fig_res.patch.set_facecolor('#fafafa')
        self.cv_res = FigureCanvasTkAgg(self.fig_res, master=rf)
        self.cv_res.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # pasek statusu
        self.sv = tk.StringVar(value='Gotowy.')
        tk.Label(root, textvariable=self.sv, anchor='w',
                 font=('Arial', 9), bg='#dde3ea', padx=8
                 ).pack(fill=tk.X, side=tk.BOTTOM)

    # ── pomocnik: ustaw h ────────────────────────────────────
    def _set_h(self, val):
        self.h_var.set(val)
        self._on_h(val)

    # ── callback suwaka h ────────────────────────────────────
    def _on_h(self, _=None):
        h = self.h_var.get()
        self.h_disp.set(f'h = {h:.1f} mm')
        self._draw_geo()
        # linia aktualna na wykresach
        if self._res is not None:
            self._mark_h_on_res(h)

    def _mark_h_on_res(self, h_val):
        """Rysuje pionową linię h_val na wykresach bez pełnego przeliczenia."""
        for ax in [self.axs[0,0], self.axs[0,1], self.axs[1,0]]:
            for line in list(ax.lines):
                if getattr(line, '_h_marker', False):
                    line.remove()
            ln = ax.axvline(h_val, color='#C62828', lw=2, ls='-.')
            ln._h_marker = True
        self.fig_res.canvas.draw_idle()

    # ── splajn ───────────────────────────────────────────────
    def _spline(self, cp, N=400):
        idx  = np.argsort(cp[:, 0])
        zp, rp = cp[idx,0], cp[idx,1]
        mask = np.concatenate([[True], np.diff(zp) > 0.02])
        zp, rp = zp[mask], rp[mask]
        if len(zp) < 2:
            return np.array([zp[0]]), np.array([rp[0]])
        cs  = CubicSpline(zp, rp, bc_type='not-a-knot')
        z_f = np.linspace(zp[0], zp[-1], N)
        r_f = np.clip(cs(z_f), 0, self.p['R_body'])
        return z_f, r_f

    # ── punkt uszczelnienia (w układzie igły) ────────────────
    def _find_z_seal(self, z_n, r_n, R_seal):
        """Zwraca z (w układzie igły) gdzie r_ndl = R_seal."""
        above = r_n >= R_seal
        if not np.any(above):
            return z_n[-1]
        if np.all(above):
            return z_n[0]
        # ostatni indeks gdzie r >= R_seal
        idx = np.where(above)[0][-1]
        if idx+1 >= len(z_n):
            return z_n[-1]
        # liniowa interpolacja
        r0, r1 = r_n[idx], r_n[idx+1]
        z0, z1 = z_n[idx], z_n[idx+1]
        if abs(r1-r0) < 1e-9:
            return z0
        return z0 + (R_seal - r0) / (r1 - r0) * (z1 - z0)

    # ── rysowanie geometrii ──────────────────────────────────
    def _draw_geo(self):
        ax  = self.ax_geo
        p   = self.p
        h   = float(self.h_var.get()) if self.h_var else 0.0
        ax.cla()

        z_b, r_b = self._spline(self.cp_body)
        z_n, r_n = self._spline(self.cp_ndl)

        # ── ściana korpusu ─────────────────────────────────
        ax.fill_betweenx(z_b,  r_b,  r_b+5, color='#5D4037', alpha=0.85)
        ax.fill_betweenx(z_b, -r_b-5, -r_b, color='#5D4037', alpha=0.85)
        ax.plot( r_b, z_b, 'k-', lw=2)
        ax.plot(-r_b, z_b, 'k-', lw=2)

        # ── igła przesunięta o -h (w górę) ────────────────
        # W układzie ciała: r_ndl w punkcie z = r_ndl_spline(z + h)
        z_body = np.linspace(0, p['L'], 500)
        r_ndl_body = np.interp(z_body + h, z_n, r_n, left=r_n[0], right=0.0)
        r_ndl_body = np.clip(r_ndl_body, 0, None)

        # maska: igła jest tam gdzie jeszcze nie minęła końcówka
        tip_body = p['L'] - h    # pozycja końcówki w układzie ciała
        mask_ndl = z_body <= tip_body + 0.01

        if np.any(mask_ndl):
            zv = z_body[mask_ndl]
            rv = r_ndl_body[mask_ndl]
            ax.fill_betweenx(zv, -rv, rv, color='#1976D2', alpha=0.45, zorder=3)
            ax.plot( rv, zv, color='#1565C0', lw=2.5, zorder=4)
            ax.plot(-rv, zv, color='#1565C0', lw=2.5, zorder=4)

        # ── końcówka igły (trójkąt) ────────────────────────
        if tip_body >= 0:
            tip_r = 0.8
            ax.fill_betweenx(
                [tip_body, tip_body + 2.5],
                [-tip_r, 0], [tip_r, 0],
                color='#1565C0', alpha=0.9, zorder=5
            )

        # ── pierścień przepływu ────────────────────────────
        z_c  = np.linspace(0, p['L'], 400)
        rb_c = np.interp(z_c, z_b, r_b)
        rn_c = np.interp(z_c + h, z_n, r_n, left=r_n[0], right=0.0)
        rn_c = np.clip(rn_c, 0, rb_c)
        ax.fill_betweenx(z_c,  rn_c, rb_c,  color='#29B6F6', alpha=0.22, zorder=2)
        ax.fill_betweenx(z_c, -rb_c, -rn_c, color='#29B6F6', alpha=0.22, zorder=2)

        # ── punkt i linia uszczelnienia ────────────────────
        R_seal = p['R_seal']
        z_seal_ndl = self._find_z_seal(z_n, r_n, R_seal)
        z_seal_body = z_seal_ndl - h   # w układzie ciała

        if 0 <= z_seal_body <= p['L']:
            # linia uszczelnienia (przerywana)
            ax.axhline(z_seal_body, color='#2E7D32', lw=1.8, ls='--',
                       alpha=0.85, zorder=6,
                       label=f'Uszczeln. z={z_seal_body:.1f}mm')
            ax.plot([ R_seal], [z_seal_body], 'g^', ms=11, zorder=7)
            ax.plot([-R_seal], [z_seal_body], 'g^', ms=11, zorder=7)

            # ← gap annotation
            gap_here = R_seal - np.interp(z_seal_ndl + 0.01*h, z_n, r_n)
            gap_here = max(gap_here, 0)
            if h > 0.05:
                ax.annotate(f' gap={gap_here:.2f}mm',
                            xy=(R_seal, z_seal_body),
                            xytext=(R_seal + 4, z_seal_body - 3),
                            fontsize=8, color='#1B5E20',
                            arrowprops=dict(arrowstyle='->', color='#1B5E20', lw=1.2))

        # ── kryza ──────────────────────────────────────────
        kz = p['L']
        ax.fill_between([ R_seal,  p['R_body']], [kz, kz], [kz+4, kz+4],
                        color='#FF8F00', alpha=0.55, zorder=6)
        ax.fill_between([-p['R_body'], -R_seal], [kz, kz], [kz+4, kz+4],
                        color='#FF8F00', alpha=0.55, zorder=6)
        ax.fill_between([ 0,  R_seal], [kz+4, kz+4], [kz+8, kz+8],
                        color='#ccc', alpha=0.6, zorder=6)
        ax.fill_between([-R_seal, 0], [kz+4, kz+4], [kz+8, kz+8],
                        color='#ccc', alpha=0.6, zorder=6)
        ax.text(0, kz+6, f'Kryza  ø{p["R_nozzle"]*2:.0f}mm',
                ha='center', va='center', fontsize=8, color='#333', zorder=8)

        # ── punkty kontrolne ──────────────────────────────
        ax.scatter( self.cp_body[:,1], self.cp_body[:,0],
                   color='#D32F2F', s=90, zorder=9, label='Korpus CP')
        ax.scatter(-self.cp_body[:,1], self.cp_body[:,0],
                   color='#D32F2F', s=90, zorder=9, alpha=0.35)
        ax.scatter( self.cp_ndl[:,1], self.cp_ndl[:,0],
                   color='#0D47A1', s=90, zorder=9, label='Igła CP')
        ax.scatter(-self.cp_ndl[:,1], self.cp_ndl[:,0],
                   color='#0D47A1', s=90, zorder=9, alpha=0.35)

        # ── linia osi i formatowanie ───────────────────────
        ax.axvline(0, color='k', lw=0.5, alpha=0.3, ls='--')
        ax.set_xlabel('Promień r [mm]', fontsize=9)
        ax.set_ylabel('Głębokość z [mm]  (0 = wlot)', fontsize=9)
        h_pct = h / p['h_max'] * 100 if p['h_max'] > 0 else 0
        ax.set_title(
            f'Przekrój podłużny   |   h = {h:.1f} mm  ({h_pct:.0f}% skoku)',
            fontsize=10, fontweight='bold',
            color='#C62828' if h > 0 else '#333'
        )
        ax.set_xlim(-p['R_body']-9, p['R_body']+9)
        ax.set_ylim(-4, p['L']+12)
        ax.invert_yaxis()
        ax.set_aspect('equal', adjustable='box')
        ax.grid(True, alpha=0.18)
        ax.legend(fontsize=7, loc='lower right')
        self.fig_geo.tight_layout(pad=1.0)
        self.cv_geo.draw()

    # ── obliczenia ───────────────────────────────────────────
    def _recalc(self):
        p    = self.p
        dP   = p['dP']*1e5;  rho = p['rho'];  Cd = p['Cd'];  g = p['g']
        Q_c  = p['Q_cel']*1e-3
        alpha, beta = np.radians(p['alpha']), np.radians(p['beta'])
        R_s  = p['R_seal']*1e-3;  R_n = p['R_nozzle']*1e-3
        h_max = p['h_max']*1e-3;  L = p['L']

        v_tor    = np.sqrt(2*dP/rho)
        A_nozzle = np.pi*R_n**2

        # przepływ pierścieniowy
        z_b, r_b = self._spline(self.cp_body,  N=500)
        z_n, r_n = self._spline(self.cp_ndl,   N=500)
        z_mm = np.linspace(0, L, 500)
        rb = np.interp(z_mm, z_b, r_b)*1e-3
        rn = np.clip(np.interp(z_mm, z_n, r_n)*1e-3, 0, rb)
        A_an = np.maximum(np.pi*(rb**2-rn**2), 1e-12)
        v_an = Q_c / A_an
        dz   = (z_mm[1]-z_mm[0])*1e-3
        a_an = np.abs(v_an * np.gradient(v_an, dz))

        # A(h) na fazce
        N_h  = 300
        h_a  = np.linspace(0, h_max, N_h)
        A_h  = np.pi*2*R_s * h_a * np.sin(beta-alpha)
        Q_h  = np.minimum(Cd*A_h*v_tor, Q_c*2.5)
        v_o  = Q_h / A_nozzle

        h_Qcel = None
        if np.max(Q_h) >= Q_c:
            h_Qcel = h_a[np.argmin(np.abs(Q_h-Q_c))]*1000

        dh   = h_a[1]-h_a[0] if len(h_a)>1 else 1e-9
        dvdh = np.gradient(v_o, dh)
        vs_m = g / max(np.max(np.abs(dvdh[2:-2])), 1e-10)

        self._res = dict(
            z_mm=z_mm, A_an=A_an, v_an=v_an, a_an=a_an,
            h_mm=h_a*1000, A_h=A_h, Q_h=Q_h, v_out=v_o,
            h_Qcel=h_Qcel, vs_max=vs_m, g=g, Q_c=Q_c,
            v_tor=v_tor*Cd,
        )
        a_max = np.max(a_an[:-10])
        s  = f"v_wylot(h_max)={v_o[-1]:.2f} m/s  │  "
        s += f"Q_cel przy h={h_Qcel:.1f}mm  │  " if h_Qcel else "Q_cel nieosiągalne  │  "
        s += f"v_suwak ≤ {vs_m*1000:.1f} mm/s  │  "
        s += f"a_korpus: {'OK ✓' if a_max<=g else f'{a_max:.0f} m/s² (>g)'}"
        self.sv.set(s)

    # ── wykresy wyników ──────────────────────────────────────
    def _draw_res(self):
        r  = self._res;  ax = self.axs
        for a in ax.flat: a.cla()
        h  = r['h_mm']
        hc = self.h_var.get() if self.h_var else 0.0

        # A(h)
        ax[0,0].plot(h, r['A_h']*1e6, 'r-', lw=2)
        ax[0,0].axvline(hc, color='#C62828', lw=2, ls='-.', label=f'h={hc:.1f}mm')
        ax[0,0].set(xlabel='h [mm]', ylabel='A [mm²]', title='Pole szczeliny A(h)')
        ax[0,0].legend(fontsize=8); ax[0,0].grid(True, alpha=0.3)

        # Q(h)
        ax[0,1].plot(h, r['Q_h']*1000, 'r-', lw=2, label='Q(h)')
        ax[0,1].axhline(r['Q_c']*1000, color='k', ls='--', lw=1.5, label='Q_cel')
        ax[0,1].axvline(hc, color='#C62828', lw=2, ls='-.', label=f'h={hc:.1f}mm')
        if r['h_Qcel']:
            ax[0,1].axvline(r['h_Qcel'], color='green', ls='-.', lw=1.5,
                            label=f"h={r['h_Qcel']:.1f}mm→Q_cel")
        ax[0,1].set(xlabel='h [mm]', ylabel='Q [L/s]', title='Przepływ Q(h)')
        ax[0,1].legend(fontsize=7); ax[0,1].grid(True, alpha=0.3)

        # v_wylot(h)
        ax[1,0].plot(h, r['v_out'], 'r-', lw=2)
        ax[1,0].axvline(hc, color='#C62828', lw=2, ls='-.', label=f'h={hc:.1f}mm')
        ax[1,0].axhline(r['v_tor'], color='orange', ls=':', lw=1.5,
                        label=f"v_szczelina={r['v_tor']:.2f}m/s")
        ax[1,0].set(xlabel='h [mm]', ylabel='v [m/s]', title='Prędkość wylotowa')
        ax[1,0].legend(fontsize=7); ax[1,0].grid(True, alpha=0.3)

        # a(z) w korpusie
        z = r['z_mm'][:-10]; a = r['a_an'][:-10]; ok = a <= r['g']
        ax[1,1].fill_betweenx(z, 0, a, where=ok,  color='#4CAF50', alpha=0.25, label='a≤g ✓')
        ax[1,1].fill_betweenx(z, 0, a, where=~ok, color='#F44336', alpha=0.30, label='a>g ✗')
        ax[1,1].plot(a, z, 'b-', lw=1.5)
        ax[1,1].axvline(r['g'], color='k', ls='--', lw=2, label=f"g={r['g']:.1f}")
        ax[1,1].invert_yaxis()
        ax[1,1].set(xlabel='a [m/s²]', ylabel='z [mm]', title='Przyspieszenie w korpusie')
        ax[1,1].legend(fontsize=7); ax[1,1].grid(True, alpha=0.3)

        self.fig_res.tight_layout(pad=2.0)
        self.cv_res.draw()

    # ── drag & drop punktów ──────────────────────────────────
    def _nearest(self, xd, zd, tol=4.5):
        best, bd = None, tol
        for nm, cp in (('body', self.cp_body), ('needle', self.cp_ndl)):
            for i, (z, r) in enumerate(cp):
                d = np.hypot(abs(xd)-r, zd-z)
                if d < bd:
                    bd, best = d, (nm, i)
        return best

    def _on_press(self, ev):
        if ev.inaxes != self.ax_geo or ev.xdata is None: return
        xd, zd = ev.xdata, ev.ydata
        ctrl = getattr(ev, 'key', '') in ('ctrl', 'control', 'ctrl+control')

        if ev.button == 3:  # PPM → dodaj punkt
            cp = self.cp_body if abs(xd) > self.p['R_body']*0.45 else self.cp_ndl
            new = np.array([[zd, abs(xd)]])
            if cp is self.cp_body:
                self.cp_body = np.vstack([self.cp_body, new])
                self.cp_body = self.cp_body[np.argsort(self.cp_body[:,0])]
            else:
                self.cp_ndl = np.vstack([self.cp_ndl, new])
                self.cp_ndl = self.cp_ndl[np.argsort(self.cp_ndl[:,0])]
            self._draw_geo(); return

        found = self._nearest(xd, zd)
        if found is None: return
        nm, idx = found
        cp = self.cp_body if nm=='body' else self.cp_ndl
        if ctrl and len(cp) > 3:  # Ctrl+klik → usuń
            if nm == 'body': self.cp_body = np.delete(self.cp_body, idx, 0)
            else:            self.cp_ndl  = np.delete(self.cp_ndl,  idx, 0)
            self._draw_geo(); return
        self._drag = (nm, idx)

    def _on_motion(self, ev):
        if self._drag is None or ev.inaxes != self.ax_geo or ev.xdata is None: return
        nm, idx = self._drag
        cp = self.cp_body if nm=='body' else self.cp_ndl
        p  = self.p
        zn = np.clip(ev.ydata,
                     cp[idx-1,0]+0.3 if idx>0       else 0.0,
                     cp[idx+1,0]-0.3 if idx<len(cp)-1 else p['L'])
        rn = abs(ev.xdata)
        if nm == 'body':
            if idx == 0:          zn, rn = 0.0,    p['R_body']
            if idx == len(cp)-1:  zn, rn = p['L'], p['R_nozzle']
            rn = np.clip(rn, p['R_nozzle'], p['R_body'])
        else:
            if idx == len(cp)-1:  zn, rn = p['L'], 0.0
            rb_here = np.interp(zn, self.cp_body[:,0], self.cp_body[:,1])
            rn = np.clip(rn, 0.0, rb_here - 0.5)
        cp[idx] = [zn, rn]
        self._draw_geo()

    def _on_release(self, ev):
        if self._drag is not None:
            self._drag = None
            self._recalc()
            self._draw_res()

    # ── przyciski ────────────────────────────────────────────
    def _on_calc(self):
        for k, v in self._pv.items():
            try: self.p[k] = float(v.get())
            except ValueError: pass
        # zaktualizuj suwak h
        self.h_scale.config(from_=-self.p['h_max'], to=self.p['h_max'])
        self._recalc(); self._draw_geo(); self._draw_res()

    def _on_reset(self):
        for k, v in self._pv.items():
            try: self.p[k] = float(v.get())
            except ValueError: pass
        self.h_var.set(0.0)
        self.h_disp.set('h = 0.0 mm')
        self.h_scale.config(from_=-self.p['h_max'], to=self.p['h_max'])
        self._init_cp()
        self._recalc(); self._draw_geo(); self._draw_res()

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    NeedleDesigner().run()
