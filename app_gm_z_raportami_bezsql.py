import sys
import tkinter as tk
from tkinter import ttk, messagebox
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import sqlite3
import csv

try:
    import pyodbc
except ImportError:
    pyodbc = None

try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    MATPLOTLIB_OK = True
except Exception:
    MATPLOTLIB_OK = False
    Figure = None
    FigureCanvasTkAgg = None

APP_DIR = Path(__file__).resolve().parent
DBFILE = APP_DIR / "gmsystem.db"
SQLFILE = APP_DIR / "gm_schema_and_data.sql"

# Zmień przed uruchomieniem:
# "sqlite", "sqlserver_1", "sqlserver_2"
ACTIVE_DB = "sqlite"

DB_CONFIG = {
    "sqlite": {
        "type": "sqlite",
        "database": DBFILE,
    },
    "sqlserver_1": {
        "type": "pyodbc",
        "driver": "ODBC Driver 17 for SQL Server",
        "server": r"localhost\SQLEXPRESS",
        "database": "GMSystem1",
        "trusted_connection": "yes",
        "uid": "",
        "pwd": "",
    },
    "sqlserver_2": {
        "type": "pyodbc",
        "driver": "ODBC Driver 17 for SQL Server",
        "server": r"localhost\SQLEXPRESS",
        "database": "GMSystem2",
        "trusted_connection": "yes",
        "uid": "",
        "pwd": "",
    },
}

def get_connection():
    cfg = DB_CONFIG[ACTIVE_DB]

    if cfg["type"] == "sqlite":
        conn = sqlite3.connect(cfg["database"])
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    if cfg["type"] == "pyodbc":
        if pyodbc is None:
            raise RuntimeError("Brak biblioteki pyodbc. Zainstaluj: pip install pyodbc")

        if str(cfg.get("trusted_connection", "yes")).lower() in ("yes", "true", "1"):
            conn_str = (
                f"DRIVER={{{cfg['driver']}}};"
                f"SERVER={cfg['server']};"
                f"DATABASE={cfg['database']};"
                "Trusted_Connection=yes;"
            )
        else:
            conn_str = (
                f"DRIVER={{{cfg['driver']}}};"
                f"SERVER={cfg['server']};"
                f"DATABASE={cfg['database']};"
                f"UID={cfg.get('uid', '')};"
                f"PWD={cfg.get('pwd', '')};"
            )

        return pyodbc.connect(conn_str)

    raise ValueError(f"Nieobsługiwany typ bazy: {cfg['type']}")


def _etykieta_magazynu(kod, opis):
    opis = (opis or "").strip()
    return f"{kod} - {opis}" if opis else (kod or "")


def database_schema_ok():
    """Sprawdzenie przy starcie (jak app_gmamelka) — dla SQLite plik i tabela Materialy."""
    cfg = DB_CONFIG.get(ACTIVE_DB, {})
    if cfg.get("type") != "sqlite":
        return True
    p = Path(cfg["database"])
    if not p.is_file():
        return False
    try:
        conn = sqlite3.connect(p)
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='Materialy'"
        ).fetchone()
        conn.close()
        return row is not None
    except Exception:
        return False


class MagazynApp:
    def __init__(self, root):
        self.root = root
        self.root.title("System GM - Gospodarka Magazynowa")
        self.root.geometry("1180x780")

        self.materialy_dict = {}
        self.magazyny_dict = {}
        self.current_chart_canvas = None
        self.current_figure = None
        self.chart_mode = "bar"

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        self.raport_filtry_podsum_var = tk.StringVar(value="")
        self.create_przyjecia_tab()
        self.create_wydania_tab()
        self.create_kartoteka_tab()
        self.create_stan_zapasu_tab()
        self.create_inwentaryzacja_tab()
        self.create_raporty_tab()
        self.load_combobox_data()
        self.refresh_stan_zapasu()

    def create_przyjecia_tab(self):
        self.przyjecia_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.przyjecia_frame, text="Przyjęcia")

        form_frame = ttk.LabelFrame(self.przyjecia_frame, text="Dodaj nowe przyjęcie", padding=10)
        form_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(form_frame, text="Materiał").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.przyjecia_material_combo = ttk.Combobox(form_frame, state="readonly", width=40)
        self.przyjecia_material_combo.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(form_frame, text="Ilość").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.przyjecia_ilosc_entry = ttk.Entry(form_frame, width=20)
        self.przyjecia_ilosc_entry.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(form_frame, text="Data operacji").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.przyjecia_data_entry = ttk.Entry(form_frame, width=20)
        self.przyjecia_data_entry.grid(row=2, column=1, sticky="w", padx=5, pady=5)
        self.przyjecia_data_entry.insert(0, datetime.now().strftime("%Y-%m-%d"))

        ttk.Label(form_frame, text="Magazyn").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        self.przyjecia_magazyn_combo = ttk.Combobox(form_frame, state="readonly", width=30)
        self.przyjecia_magazyn_combo.grid(row=3, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(form_frame, text="Dostawca").grid(row=4, column=0, sticky="w", padx=5, pady=5)
        self.przyjecia_dostawca_entry = ttk.Entry(form_frame, width=50)
        self.przyjecia_dostawca_entry.grid(row=4, column=1, padx=5, pady=5)

        ttk.Label(form_frame, text="Konto kosztowe").grid(row=6, column=0, sticky="w", padx=5, pady=5)
        self.przyjecia_konto_combo = ttk.Combobox(form_frame, state="readonly", width=30)
        self.przyjecia_konto_combo.grid(row=6, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(form_frame, text="Uwagi").grid(row=5, column=0, sticky="nw", padx=5, pady=5)
        self.przyjecia_uwagi_text = tk.Text(form_frame, height=3, width=50)
        self.przyjecia_uwagi_text.grid(row=5, column=1, padx=5, pady=5)

        button_frame = ttk.Frame(form_frame)
        button_frame.grid(row=6, column=0, columnspan=3, pady=10)
        ttk.Button(button_frame, text="Dodaj przyjęcie", command=self.add_przyjecie).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Odśwież", command=self.refresh_przyjecia).pack(side="left", padx=5)

        table_frame = ttk.LabelFrame(self.przyjecia_frame, text="Historia przyjęć", padding=10)
        table_frame.pack(fill="both", expand=True, padx=10, pady=10)
        scrollbar = ttk.Scrollbar(table_frame)
        scrollbar.pack(side="right", fill="y")

        cols = ("ID", "Materiał", "Ilość", "Data", "Magazyn", "Dostawca", "Uwagi")
        self.przyjecia_tree = ttk.Treeview(table_frame, columns=cols, show="headings", yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.przyjecia_tree.yview)
        for col in cols:
            self.przyjecia_tree.heading(col, text=col)
            self.przyjecia_tree.column(col, width=140)
        self.przyjecia_tree.pack(fill="both", expand=True)

        self.refresh_przyjecia()

    def create_wydania_tab(self):
        self.wydania_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.wydania_frame, text="Wydania")

        form = ttk.LabelFrame(self.wydania_frame, text="Nowe wydanie z magazynu", padding=10)
        form.pack(fill="x", padx=10, pady=5)

        ttk.Label(form, text="Materiał:").grid(row=0, column=0, sticky="w")
        self.wydania_material_combo = ttk.Combobox(form, state="readonly", width=40)
        self.wydania_material_combo.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(form, text="Ilość:").grid(row=1, column=0, sticky="w")
        self.wydania_ilosc_entry = ttk.Entry(form, width=20)
        self.wydania_ilosc_entry.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(form, text="Magazyn:").grid(row=2, column=0, sticky="w")
        self.wydania_magazyn_combo = ttk.Combobox(form, state="readonly", width=30)
        self.wydania_magazyn_combo.grid(row=2, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(form, text="Pracownik/Zlecenie:").grid(row=3, column=0, sticky="w")
        self.wydania_pracownik_entry = ttk.Entry(form, width=40)
        self.wydania_pracownik_entry.grid(row=3, column=1, padx=5, pady=5)

        ttk.Label(form, text="Data (RRRR-MM-DD):").grid(row=4, column=0, sticky="w")
        self.wydania_data_entry = ttk.Entry(form, width=20)
        self.wydania_data_entry.insert(0, datetime.now().strftime("%Y-%m-%d"))
        self.wydania_data_entry.grid(row=4, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(form, text="Uwagi:").grid(row=5, column=0, sticky="nw")
        self.wydania_uwagi_text = tk.Text(form, height=3, width=50)
        self.wydania_uwagi_text.grid(row=5, column=1, padx=5, pady=5)

        ttk.Label(form, text="Konto kosztowe").grid(row=6, column=0, sticky="w")
        self.wydania_konto_combo = ttk.Combobox(form, state="readonly", width=30)
        self.wydania_konto_combo.grid(row=6, column=1, sticky="w", padx=5, pady=5)

        ttk.Button(form, text="WYDAJ TOWAR", command=self.add_wydanie).grid(row=6, column=1, pady=10)

        cols = ("ID", "Materiał", "Ilość", "Data", "Magazyn", "Odbiorca", "Uwagi")
        self.wydania_tree = ttk.Treeview(self.wydania_frame, columns=cols, show="headings")
        for c in cols:
            self.wydania_tree.heading(c, text=c)
            self.wydania_tree.column(c, width=140)
        self.wydania_tree.pack(fill="both", expand=True, padx=10, pady=10)

        self.refresh_wydania()

    def create_raporty_tab(self):
        self.raporty_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.raporty_frame, text="Raporty i wykresy")

        ctrl_frame = ttk.LabelFrame(self.raporty_frame, text="Opcje raportu", padding=10)
        ctrl_frame.pack(fill="x", padx=10, pady=10)

        ttk.Button(ctrl_frame, text="1. Stan zapasu", command=self.raport_stan_zapasu).pack(side="left", padx=5)
        ttk.Button(ctrl_frame, text="2. Analiza miesięczna", command=self.raport_miesieczny).pack(side="left", padx=5)
        ttk.Button(ctrl_frame, text="3. Ruchy magazynowe", command=self.raport_ruchy).pack(side="left", padx=5)
        ttk.Button(ctrl_frame, text="4. Ranking produktów", command=self.raport_ranking).pack(side="left", padx=5)
        ttk.Button(ctrl_frame, text="5. Niskie stany", command=self.raport_niskie_stany).pack(side="left", padx=5)
        ttk.Button(ctrl_frame, text="Tryb słupkowy", command=self.configure_bar_chart).pack(side="left", padx=5)
        ttk.Button(ctrl_frame, text="Tryb liniowy", command=self.configure_line_chart).pack(side="left", padx=5)
        ttk.Button(ctrl_frame, text="Eksportuj CSV", command=self.export_csv).pack(side="left", padx=5)
        ttk.Button(ctrl_frame, text="6. Ranking ruchu", command=self.raport_ranking_ruchu).pack(side="left", padx=5)

        row2 = ttk.Frame(ctrl_frame)
        row2.pack(fill="x", pady=(10, 0))
        ttk.Label(row2, text="Jak u Amelki (wersja rozszerzona):").pack(side="left", padx=(0, 8))
        ttk.Button(row2, text="2b. Miesiąc + materiał + magazyn", command=self.raport_miesieczny_szczegolowy).pack(side="left", padx=4)
        ttk.Button(row2, text="4b. Ranking wydań (ilość)", command=self.raport_ranking_wydan).pack(side="left", padx=4)

        filtry = ttk.LabelFrame(self.raporty_frame, text="Filtry (okres + magazyn) — raport / wykresy jak w app_gmamelka", padding=8)
        filtry.pack(fill="x", padx=10, pady=(0, 6))
        ttk.Label(filtry, text="Okres (RRRR-MM):").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.rap_okres_entry = ttk.Entry(filtry, width=12)
        self.rap_okres_entry.grid(row=0, column=1, padx=4, pady=4)
        self.rap_okres_entry.insert(0, datetime.now().strftime("%Y-%m"))
        ttk.Label(filtry, text="Magazyn:").grid(row=0, column=2, sticky="w", padx=4, pady=4)
        self.rap_mag_filtr_combo = ttk.Combobox(filtry, state="readonly", width=32)
        self.rap_mag_filtr_combo.grid(row=0, column=3, padx=4, pady=4)
        self._load_rap_filtry_magazyny()
        bf = ttk.Frame(filtry)
        bf.grid(row=1, column=0, columnspan=4, pady=6, sticky="w")
        ttk.Button(bf, text="Raport szczegółowy", command=self.generuj_raport_szczegolowy_filtr).pack(side="left", padx=4)
        ttk.Button(bf, text="Wykres słupkowy (wartości)", command=self.wykres_slupkowy_filtr).pack(side="left", padx=4)
        ttk.Button(bf, text="Wykres liniowy (skumul. stan)", command=self.wykres_liniowy_filtr).pack(side="left", padx=4)
        ttk.Button(bf, text="Raport stanów (miesięcznie)", command=self.raport_stany_miesieczne_filtr).pack(side="left", padx=4)

        self.chart_frame = ttk.LabelFrame(self.raporty_frame, text="Wykres", padding=10)
        self.chart_frame.pack(fill="both", expand=False, padx=10, pady=(0, 10))

        chart_controls = ttk.Frame(self.chart_frame)
        chart_controls.pack(fill="x", pady=(0, 8))

        ttk.Label(chart_controls, text="Metryka").grid(row=0, column=0, padx=4, pady=4, sticky="w")
        self.chart_metric_combo = ttk.Combobox(chart_controls, state="readonly", width=18, values=["Ilość", "Wartość", "Liczba operacji"])
        self.chart_metric_combo.grid(row=0, column=1, padx=4, pady=4)
        self.chart_metric_combo.set("Ilość")

        ttk.Label(chart_controls, text="Grupowanie").grid(row=0, column=2, padx=4, pady=4, sticky="w")
        self.chart_group_combo = ttk.Combobox(chart_controls, state="readonly", width=18, values=["Materiał", "Magazyn", "Miesiąc"])
        self.chart_group_combo.grid(row=0, column=3, padx=4, pady=4)
        self.chart_group_combo.set("Materiał")

        ttk.Label(chart_controls, text="Typ operacji").grid(row=0, column=4, padx=4, pady=4, sticky="w")
        self.chart_type_combo = ttk.Combobox(chart_controls, state="readonly", width=14, values=["Wszystkie", "Przyjcie", "Wydanie"])
        self.chart_type_combo.grid(row=0, column=5, padx=4, pady=4)
        self.chart_type_combo.set("Wszystkie")

        ttk.Label(chart_controls, text="Limit").grid(row=0, column=6, padx=4, pady=4, sticky="w")
        self.chart_limit_entry = ttk.Entry(chart_controls, width=6)
        self.chart_limit_entry.grid(row=0, column=7, padx=4, pady=4)
        self.chart_limit_entry.insert(0, "10")

        ttk.Button(chart_controls, text="Rysuj wykres", command=self.draw_embedded_chart).grid(row=0, column=8, padx=6, pady=4)
        ttk.Button(chart_controls, text="Wyczyść wykres", command=self.clear_chart).grid(row=0, column=9, padx=6, pady=4)

        self.chart_message = ttk.Label(self.chart_frame, text="Wybierz parametry i kliknij 'Rysuj wykres'.")
        self.chart_message.pack(anchor="w", pady=(0, 6))

        self.chart_canvas_holder = ttk.Frame(self.chart_frame, height=320)
        self.chart_canvas_holder.pack(fill="both", expand=True)
        self.chart_canvas_holder.pack_propagate(False)

        table_frame = ttk.LabelFrame(self.raporty_frame, text="Wyniki raportu", padding=10)
        table_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.raport_y_scroll = ttk.Scrollbar(table_frame)
        self.raport_y_scroll.pack(side="right", fill="y")
        self.raport_x_scroll = ttk.Scrollbar(table_frame, orient="horizontal")
        self.raport_x_scroll.pack(side="bottom", fill="x")

        cols = ("Lp.", "Materiał", "Magazyn", "Ilość", "Wartość", "Wyszczególnienie")
        self.raporty_tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=16, yscrollcommand=self.raport_y_scroll.set, xscrollcommand=self.raport_x_scroll.set)
        self.raport_y_scroll.config(command=self.raporty_tree.yview)
        self.raport_x_scroll.config(command=self.raporty_tree.xview)

        widths = {"Lp.": 50, "Materiał": 240, "Magazyn": 90, "Ilość": 140, "Wartość": 140, "Wyszczególnienie": 280}
        for col in cols:
            self.raporty_tree.heading(col, text=col)
            self.raporty_tree.column(col, width=widths[col], anchor="w")
        self.raporty_tree.pack(fill="both", expand=True)
        self.raporty_tree.tag_configure("p", foreground="darkgreen")
        self.raporty_tree.tag_configure("w", foreground="darkred")
        ttk.Label(table_frame, textvariable=self.raport_filtry_podsum_var, font=("Helvetica", 9, "bold")).pack(anchor="w", pady=(4, 0))

    def create_kartoteka_tab(self):
        self.kartoteka_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.kartoteka_frame, text="Kartoteka")

        split = ttk.Frame(self.kartoteka_frame)
        split.pack(fill="both", expand=True, padx=6, pady=6)
        left = ttk.Frame(split)
        left.pack(side="left", fill="both", expand=True, padx=4)
        right = ttk.Frame(split)
        right.pack(side="right", fill="both", expand=True, padx=4)

        f = ttk.LabelFrame(left, text="Dodaj nowy produkt", padding=10)
        f.pack(fill="x", padx=4, pady=4)

        ttk.Label(f, text="Nazwa:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.ent_mat_nazwa = ttk.Entry(f, width=28)
        self.ent_mat_nazwa.grid(row=0, column=1, columnspan=3, sticky="ew", padx=5, pady=2)

        ttk.Label(f, text="Indeks:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.ent_mat_indeks = ttk.Entry(f, width=12)
        self.ent_mat_indeks.grid(row=1, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(f, text="Cena:").grid(row=1, column=2, sticky="w", padx=5, pady=2)
        self.ent_mat_cena = ttk.Entry(f, width=12)
        self.ent_mat_cena.grid(row=1, column=3, sticky="w", padx=5, pady=2)

        ttk.Label(f, text="Kategoria:").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        self.ent_mat_kat = ttk.Entry(f, width=28)
        self.ent_mat_kat.grid(row=2, column=1, columnspan=3, sticky="ew", padx=5, pady=2)

        ttk.Label(f, text="Jednostka:").grid(row=3, column=0, sticky="w", padx=5, pady=2)
        self.ent_mat_jedn = ttk.Entry(f, width=12)
        self.ent_mat_jedn.insert(0, "szt")
        self.ent_mat_jedn.grid(row=3, column=1, sticky="w", padx=5, pady=2)

        ttk.Button(f, text="Zapisz", command=self.dodaj_material_sql).grid(row=4, column=0, columnspan=4, pady=8)

        mlist = ttk.LabelFrame(left, text="Lista materiałów", padding=8)
        mlist.pack(fill="both", expand=True, padx=4, pady=4)
        msb = ttk.Scrollbar(mlist)
        msb.pack(side="right", fill="y")
        cols = ("ID", "Nazwa", "Indeks", "Kategoria", "Cena", "Jm")
        self.kart_tree = ttk.Treeview(mlist, columns=cols, show="headings", yscrollcommand=msb.set)
        msb.config(command=self.kart_tree.yview)
        for c, w in (("ID", 40), ("Nazwa", 160), ("Indeks", 60), ("Kategoria", 90), ("Cena", 70), ("Jm", 50)):
            self.kart_tree.heading(c, text=c)
            self.kart_tree.column(c, width=w)
        self.kart_tree.pack(fill="both", expand=True)

        gf = ttk.LabelFrame(right, text="Dodaj magazyn", padding=10)
        gf.pack(fill="x", padx=4, pady=4)
        ttk.Label(gf, text="Kod:").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        self.kart_mag_kod = ttk.Entry(gf, width=14)
        self.kart_mag_kod.grid(row=0, column=1, padx=4, pady=2)
        ttk.Label(gf, text="Opis:").grid(row=1, column=0, sticky="w", padx=4, pady=2)
        self.kart_mag_opis = ttk.Entry(gf, width=28)
        self.kart_mag_opis.grid(row=1, column=1, padx=4, pady=2)
        ttk.Button(gf, text="Dodaj magazyn", command=self.add_magazyn).grid(row=2, column=0, columnspan=2, pady=8)

        glist = ttk.LabelFrame(right, text="Lista magazynów", padding=8)
        glist.pack(fill="both", expand=True, padx=4, pady=4)
        gsb = ttk.Scrollbar(glist)
        gsb.pack(side="right", fill="y")
        gcols = ("ID", "Kod", "Opis", "Lokalizacja")
        self.mag_tree = ttk.Treeview(glist, columns=gcols, show="headings", yscrollcommand=gsb.set)
        gsb.config(command=self.mag_tree.yview)
        for c, w in (("ID", 40), ("Kod", 70), ("Opis", 160), ("Lokalizacja", 100)):
            self.mag_tree.heading(c, text=c)
            self.mag_tree.column(c, width=w)
        self.mag_tree.pack(fill="both", expand=True)

        self.odswiez_kartoteke()
        self.odswiez_liste_magazynow()

    def dodaj_material_sql(self):
        nazwa = self.ent_mat_nazwa.get().strip()
        indeks = self.ent_mat_indeks.get().strip()
        cena = self.ent_mat_cena.get().strip()
        kategoria = self.ent_mat_kat.get().strip()
        jednostka = self.ent_mat_jedn.get().strip() or "szt"

        if not (nazwa and indeks and cena):
            messagebox.showwarning("Błąd", "Wszystkie pola (Nazwa, Indeks, Cena) muszą być wypełnione!")
            return

        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO Materialy (Nazwa, Indeks, Kategoria, Cenajedn, Jednostka) VALUES (?, ?, ?, ?, ?)",
                (nazwa, int(indeks), kategoria or None, float(cena), jednostka),
            )
            conn.commit()

            self.ent_mat_nazwa.delete(0, tk.END)
            self.ent_mat_indeks.delete(0, tk.END)
            self.ent_mat_cena.delete(0, tk.END)
            self.ent_mat_kat.delete(0, tk.END)
            self.ent_mat_jedn.delete(0, tk.END)
            self.ent_mat_jedn.insert(0, "szt")

            self.odswiez_kartoteke()
            self.load_combobox_data()
            if hasattr(self, "stan_tree"):
                self.refresh_stan_zapasu()
        except sqlite3.IntegrityError:
            messagebox.showerror("Błąd", "Ten numer indeksu już istnieje w bazie!")
        except Exception as e:
            messagebox.showerror("Błąd", f"Niepoprawne dane: {e}")
        finally:
            conn.close()

    def odswiez_kartoteke(self):
        for i in self.kart_tree.get_children():
            self.kart_tree.delete(i)
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT MaterialID, Nazwa, Indeks, COALESCE(Kategoria, ''), Cenajedn, COALESCE(Jednostka, 'szt') "
                "FROM Materialy ORDER BY Nazwa"
            )
            for row in cur.fetchall():
                self.kart_tree.insert("", "end", values=row)
        finally:
            conn.close()

    def odswiez_liste_magazynow(self):
        if not hasattr(self, "mag_tree"):
            return
        for i in self.mag_tree.get_children():
            self.mag_tree.delete(i)
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT MagazynID, Kod, COALESCE(Opis, ''), COALESCE(Lokalizacja, '') FROM Magazyny ORDER BY Kod")
            for row in cur.fetchall():
                self.mag_tree.insert("", "end", values=row)
        finally:
            conn.close()

    def create_stan_zapasu_tab(self):
        self.stan_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.stan_frame, text="Stan zapasu")

        ctrl = ttk.Frame(self.stan_frame)
        ctrl.pack(fill="x", padx=10, pady=8)
        ttk.Button(ctrl, text="Odśwież", command=self.refresh_stan_zapasu).pack(side="left", padx=5)
        self.stan_summary_var = tk.StringVar(value="")
        ttk.Label(ctrl, textvariable=self.stan_summary_var, font=("Helvetica", 10, "bold")).pack(side="left", padx=16)

        tf = ttk.LabelFrame(self.stan_frame, text="Bieżący stan zapasów", padding=10)
        tf.pack(fill="both", expand=True, padx=10, pady=5)
        sb = ttk.Scrollbar(tf)
        sb.pack(side="right", fill="y")
        cols = ("Materiał", "Magazyn", "Lokalizacja", "Ilość", "Jednostka", "Cena jedn.", "Wartość zapasu")
        self.stan_tree = ttk.Treeview(tf, columns=cols, show="headings", yscrollcommand=sb.set)
        sb.config(command=self.stan_tree.yview)
        widths = {"Materiał": 220, "Magazyn": 90, "Lokalizacja": 110, "Ilość": 70, "Jednostka": 70, "Cena jedn.": 90, "Wartość zapasu": 120}
        for c in cols:
            self.stan_tree.heading(c, text=c)
            self.stan_tree.column(c, width=widths.get(c, 100), anchor="center")
        self.stan_tree.pack(fill="both", expand=True)
        self.stan_tree.tag_configure("ujemny", foreground="red")
        self.stan_tree.tag_configure("zero", foreground="orange")
        self.stan_tree.tag_configure("ok", foreground="green")

    def refresh_stan_zapasu(self):
        if not hasattr(self, "stan_tree"):
            return
        for item in self.stan_tree.get_children():
            self.stan_tree.delete(item)
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    m.Nazwa,
                    mag.Kod,
                    COALESCE(mag.Lokalizacja, '-'),
                    (COALESCE(SUM(CASE WHEN o.TypOperacji='Przyjcie' THEN o.Ilo ELSE 0 END), 0) -
                     COALESCE(SUM(CASE WHEN o.TypOperacji='Wydanie' THEN o.Ilo ELSE 0 END), 0)) AS ilosc,
                    COALESCE(m.Jednostka, 'szt'),
                    m.Cenajedn,
                    ((COALESCE(SUM(CASE WHEN o.TypOperacji='Przyjcie' THEN o.Ilo ELSE 0 END), 0) -
                      COALESCE(SUM(CASE WHEN o.TypOperacji='Wydanie' THEN o.Ilo ELSE 0 END), 0)) * m.Cenajedn) AS wartosc
                FROM OperacjeMagazynowe o
                JOIN Materialy m ON o.MaterialID = m.MaterialID
                JOIN Magazyny mag ON o.MagazynID = mag.MagazynID
                GROUP BY m.Nazwa, mag.Kod, mag.Lokalizacja, m.Jednostka, m.Cenajedn
                ORDER BY m.Nazwa, mag.Kod
                """
            )
            rows = cur.fetchall()
            total = 0.0
            for row in rows:
                mat, mag, lok, ilosc, jedn, cena, wartosc = row
                w = float(wartosc or 0)
                total += w
                tag = "ujemny" if ilosc < 0 else ("zero" if ilosc == 0 else "ok")
                self.stan_tree.insert(
                    "",
                    "end",
                    values=(mat, mag, lok, ilosc, jedn, f"{float(cena or 0):.2f} zł", f"{w:.2f} zł"),
                    tags=(tag,),
                )
            self.stan_summary_var.set(f"Łączna wartość zapasów: {total:,.2f} zł")
        except Exception as e:
            messagebox.showerror("Błąd", str(e))
        finally:
            conn.close()

    def create_inwentaryzacja_tab(self):
        self.inw_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.inw_frame, text="Inwentaryzacja")

        top = ttk.LabelFrame(self.inw_frame, text="Wprowadź stan rzeczywisty", padding=10)
        top.pack(fill="x", padx=10, pady=8)

        ttk.Label(top, text="Materiał:").grid(row=0, column=0, sticky="w", padx=5, pady=4)
        self.inw_mat_combo = ttk.Combobox(top, state="readonly", width=42)
        self.inw_mat_combo.grid(row=0, column=1, padx=5, pady=4)

        ttk.Label(top, text="Magazyn:").grid(row=1, column=0, sticky="w", padx=5, pady=4)
        self.inw_mag_combo = ttk.Combobox(top, state="readonly", width=42)
        self.inw_mag_combo.grid(row=1, column=1, padx=5, pady=4)

        ttk.Label(top, text="Stan rzeczywisty:").grid(row=2, column=0, sticky="w", padx=5, pady=4)
        self.inw_stan_entry = ttk.Entry(top, width=18)
        self.inw_stan_entry.grid(row=2, column=1, sticky="w", padx=5, pady=4)

        bf = ttk.Frame(top)
        bf.grid(row=3, column=0, columnspan=2, pady=8)
        ttk.Button(bf, text="Sprawdź różnicę", command=self.sprawdz_roznice_inwent).pack(side="left", padx=5)
        ttk.Button(bf, text="Pokaż stany systemowe", command=self.pokaz_stany_systemowe_inwent).pack(side="left", padx=5)
        ttk.Button(bf, text="Wyczyść", command=self.clear_inwentaryzacja).pack(side="left", padx=5)

        self.inw_wynik_var = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.inw_wynik_var, font=("Helvetica", 10, "bold"), foreground="navy").grid(
            row=4, column=0, columnspan=2, pady=5
        )

        tf = ttk.LabelFrame(self.inw_frame, text="Zestawienie", padding=10)
        tf.pack(fill="both", expand=True, padx=10, pady=5)
        sb = ttk.Scrollbar(tf)
        sb.pack(side="right", fill="y")
        icols = ("Materiał", "Magazyn", "Stan systemowy", "Stan rzeczywisty", "Różnica", "Wartość różnicy", "Ocena")
        self.inw_tree = ttk.Treeview(tf, columns=icols, show="headings", yscrollcommand=sb.set)
        sb.config(command=self.inw_tree.yview)
        iw = {"Materiał": 200, "Magazyn": 140, "Stan systemowy": 110, "Stan rzeczywisty": 110, "Różnica": 80, "Wartość różnicy": 120, "Ocena": 110}
        for c in icols:
            self.inw_tree.heading(c, text=c)
            self.inw_tree.column(c, width=iw.get(c, 100), anchor="center")
        self.inw_tree.pack(fill="both", expand=True)
        self.inw_tree.tag_configure("niedobor", foreground="red")
        self.inw_tree.tag_configure("nadwyzka", foreground="blue")
        self.inw_tree.tag_configure("zgodnosc", foreground="green")

        self._reload_inw_combos()

    def _reload_inw_combos(self):
        if not hasattr(self, "inw_mat_combo"):
            return
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT MaterialID, Nazwa FROM Materialy ORDER BY Nazwa")
            mat = cur.fetchall()
            self._inw_mat = {r[1]: r[0] for r in mat}
            self.inw_mat_combo["values"] = [r[1] for r in mat]
            cur.execute("SELECT MagazynID, Kod, COALESCE(Opis, '') FROM Magazyny ORDER BY Kod")
            mag = cur.fetchall()
            self._inw_mag = {_etykieta_magazynu(r[1], r[2]): r[0] for r in mag}
            self.inw_mag_combo["values"] = list(self._inw_mag.keys())
        except Exception as e:
            print(f"Inwentaryzacja combo: {e}")
        finally:
            conn.close()

    def sprawdz_roznice_inwent(self):
        mat_n = self.inw_mat_combo.get()
        mag_n = self.inw_mag_combo.get()
        stan_s = self.inw_stan_entry.get().strip()
        if not mat_n or not mag_n:
            messagebox.showerror("Błąd", "Wybierz materiał i magazyn.")
            return
        if not stan_s:
            messagebox.showerror("Błąd", "Podaj stan rzeczywisty.")
            return
        try:
            stan_rzecz = int(stan_s)
        except ValueError:
            messagebox.showerror("Błąd", "Stan musi być liczbą całkowitą.")
            return
        mat_id = self._inw_mat[mat_n]
        mag_id = self._inw_mag[mag_n]
        stan_sys = self.get_available_stock(mat_id, mag_id)
        roznica = stan_rzecz - stan_sys
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT Cenajedn FROM Materialy WHERE MaterialID=?", (mat_id,))
            r = cur.fetchone()
            cena = float(r[0] or 0) if r else 0.0
        finally:
            conn.close()
        wartosc = roznica * cena
        if roznica < 0:
            ocena, tag = "NIEDOBÓR", "niedobor"
        elif roznica > 0:
            ocena, tag = "NADWYŻKA", "nadwyzka"
        else:
            ocena, tag = "ZGODNOŚĆ", "zgodnosc"
        self.inw_wynik_var.set(
            f"Sys.: {stan_sys}  |  Rzecz.: {stan_rzecz}  |  Różnica: {roznica:+d}  |  Wartość: {wartosc:+.2f} zł  →  {ocena}"
        )
        self.inw_tree.insert(
            "",
            "end",
            values=(mat_n, mag_n, stan_sys, stan_rzecz, f"{roznica:+d}", f"{wartosc:+.2f} zł", ocena),
            tags=(tag,),
        )

    def pokaz_stany_systemowe_inwent(self):
        for item in self.inw_tree.get_children():
            self.inw_tree.delete(item)
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT m.Nazwa, mag.Kod,
                    (COALESCE(SUM(CASE WHEN o.TypOperacji='Przyjcie' THEN o.Ilo ELSE 0 END), 0) -
                     COALESCE(SUM(CASE WHEN o.TypOperacji='Wydanie' THEN o.Ilo ELSE 0 END), 0)) AS stan
                FROM OperacjeMagazynowe o
                JOIN Materialy m ON o.MaterialID = m.MaterialID
                JOIN Magazyny mag ON o.MagazynID = mag.MagazynID
                GROUP BY m.Nazwa, mag.Kod
                ORDER BY m.Nazwa, mag.Kod
                """
            )
            for mat, mag, stan in cur.fetchall():
                stan = int(stan or 0)
                self.inw_tree.insert(
                    "",
                    "end",
                    values=(mat, mag, stan, "—", "—", "—", "Do weryfikacji"),
                    tags=("zgodnosc",),
                )
        except Exception as e:
            messagebox.showerror("Błąd", str(e))
        finally:
            conn.close()

    def clear_inwentaryzacja(self):
        if not hasattr(self, "inw_mat_combo"):
            return
        self.inw_mat_combo.set("")
        self.inw_mag_combo.set("")
        self.inw_stan_entry.delete(0, tk.END)
        self.inw_wynik_var.set("")
        for item in self.inw_tree.get_children():
            self.inw_tree.delete(item)

    def load_combobox_data(self):
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT MaterialID, Nazwa FROM Materialy ORDER BY Nazwa")
            mats = cursor.fetchall()
            self.materialy_dict = {row[1]: row[0] for row in mats}
            cursor.execute("SELECT MagazynID, Kod, COALESCE(Opis, '') FROM Magazyny ORDER BY Kod")
            mags = cursor.fetchall()
            self.magazyny_dict = {_etykieta_magazynu(r[1], r[2]): r[0] for r in mags}
            cursor.execute("SELECT KontoID, Kod FROM KontaKosztowe ORDER BY Kod")
            konta = cursor.fetchall()
            self.konta_dict = {row[1]: row[0] for row in konta}
            
            if hasattr(self, 'przyjecia_material_combo'):
                self.przyjecia_material_combo["values"] = list(self.materialy_dict.keys())
            if hasattr(self, 'przyjecia_magazyn_combo'):
                self.przyjecia_magazyn_combo["values"] = list(self.magazyny_dict.keys())
            if hasattr(self, 'wydania_material_combo'):
                self.wydania_material_combo["values"] = list(self.materialy_dict.keys())
            if hasattr(self, 'wydania_magazyn_combo'):
                self.wydania_magazyn_combo["values"] = list(self.magazyny_dict.keys())
            if hasattr(self, 'przyjecia_konto_combo'):
                self.przyjecia_konto_combo["values"] = list(self.konta_dict.keys())
            if hasattr(self, 'wydania_konto_combo'):
                self.wydania_konto_combo["values"] = list(self.konta_dict.keys())
            if hasattr(self, "inw_mat_combo"):
                self._reload_inw_combos()
            if hasattr(self, "rap_mag_filtr_combo"):
                self._load_rap_filtry_magazyny()
        except Exception as e:
            print(f"DEBUG: Problem z combo: {e}")
        finally:
            conn.close()


    def add_przyjecie(self):
        try:
            material_name = self.przyjecia_material_combo.get()
            magazyn_name = self.przyjecia_magazyn_combo.get()
            if not material_name:
                messagebox.showerror("Błąd", "Wybierz materiał.")
                return
            if not magazyn_name:
                messagebox.showerror("Błąd", "Wybierz magazyn.")
                return
            ilosc = int(self.przyjecia_ilosc_entry.get())
            if ilosc <= 0:
                raise ValueError("Ilość musi być większa od zera.")
            konto_name = self.przyjecia_konto_combo.get()
            if not konto_name:
                messagebox.showerror("Błąd", "Wybierz konto kosztowe.")
                return
            data = self.przyjecia_data_entry.get().strip()
            datetime.strptime(data, "%Y-%m-%d")
            material_id = self.materialy_dict[material_name]
            magazyn_id = self.magazyny_dict[magazyn_name]
            konto_id = self.konta_dict[konto_name]
            dostawca = self.przyjecia_dostawca_entry.get().strip()
            uwagi = self.przyjecia_uwagi_text.get("1.0", "end-1c").strip()
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO OperacjeMagazynowe (MaterialID, MagazynID, KontoID, TypOperacji, Ilo, DataOperacji, Dostawca, ZlecPracownika, Uwagi) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (material_id, magazyn_id, konto_id, "Przyjcie", ilosc, data, dostawca or None, None, uwagi or None),
            )
            conn.commit()
            conn.close()
            self.clear_przyjecie_form()
            self.refresh_przyjecia()
            messagebox.showinfo("OK", "Dodano przyjęcie.")
            if hasattr(self, "stan_tree"):
                self.refresh_stan_zapasu()
        except Exception as e:
            messagebox.showerror("Błąd", str(e))

    def get_available_stock(self, material_id, magazyn_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN TypOperacji='Przyjcie' THEN Ilo ELSE 0 END), 0) -
                COALESCE(SUM(CASE WHEN TypOperacji='Wydanie' THEN Ilo ELSE 0 END), 0)
            FROM OperacjeMagazynowe
            WHERE MaterialID = ? AND MagazynID = ?
            """,
            (material_id, magazyn_id),
        )
        row = cur.fetchone()
        conn.close()
        return int(row[0] or 0)

    def add_wydanie(self):
        try:
            material_name = self.wydania_material_combo.get()
            magazyn_name = self.wydania_magazyn_combo.get()
            if not material_name:
                messagebox.showerror("Błąd", "Wybierz materiał.")
                return
            if not magazyn_name:
                messagebox.showerror("Błąd", "Wybierz magazyn.")
                return
            ilosc = int(self.wydania_ilosc_entry.get())
            if ilosc <= 0:
                raise ValueError("Ilość musi być większa od zera.")
            konto_name = self.wydania_konto_combo.get()
            if not konto_name:
                messagebox.showerror("Błąd", "Wybierz konto kosztowe.")
                return
            data = self.wydania_data_entry.get().strip()
            datetime.strptime(data, "%Y-%m-%d")
            material_id = self.materialy_dict[material_name]
            magazyn_id = self.magazyny_dict[magazyn_name]
            konto_id = self.konta_dict[konto_name]
            pracownik = self.wydania_pracownik_entry.get().strip()
            uwagi = self.wydania_uwagi_text.get("1.0", "end-1c").strip()

            dostepna_ilosc = self.get_available_stock(material_id, magazyn_id)
            if ilosc > dostepna_ilosc:
                raise ValueError(
                    f"Brak wystarczającego stanu magazynowego. Dostępna ilość: {dostepna_ilosc}, próba wydania: {ilosc}."
                )

            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO OperacjeMagazynowe (MaterialID, MagazynID, KontoID, TypOperacji, Ilo, DataOperacji, Dostawca, ZlecPracownika, Uwagi) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (material_id, magazyn_id, konto_id, "Wydanie", ilosc, data, None, pracownik or None, uwagi or None),
            )
            conn.commit()
            conn.close()
            self.clear_wydanie_form()
            self.refresh_wydania()
            messagebox.showinfo("OK", "Dodano wydanie.")
            if hasattr(self, "stan_tree"):
                self.refresh_stan_zapasu()
        except Exception as e:
            messagebox.showerror("Błąd", str(e))

    def clear_przyjecie_form(self):
        self.przyjecia_material_combo.set("")
        self.przyjecia_ilosc_entry.delete(0, tk.END)
        self.przyjecia_data_entry.delete(0, tk.END)
        self.przyjecia_data_entry.insert(0, datetime.now().strftime("%Y-%m-%d"))
        self.przyjecia_magazyn_combo.set("")
        self.przyjecia_dostawca_entry.delete(0, tk.END)
        self.przyjecia_uwagi_text.delete("1.0", tk.END)
        self.przyjecia_konto_combo.set("")

    def clear_wydanie_form(self):
        self.wydania_material_combo.set("")
        self.wydania_ilosc_entry.delete(0, tk.END)
        self.wydania_data_entry.delete(0, tk.END)
        self.wydania_data_entry.insert(0, datetime.now().strftime("%Y-%m-%d"))
        self.wydania_magazyn_combo.set("")
        self.wydania_pracownik_entry.delete(0, tk.END)
        self.wydania_uwagi_text.delete("1.0", tk.END)
        self.wydania_konto_combo.set("")

    def add_magazyn(self):
        try:
            kod = self.kart_mag_kod.get().strip()
            opis = self.kart_mag_opis.get().strip()
            if not kod:
                messagebox.showerror("Błąd", "Podaj kod magazynu.")
                return
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO Magazyny (Kod, Opis) VALUES(?,?)", (kod, opis or None))
            conn.commit()
            conn.close()
            self.kart_mag_kod.delete(0, tk.END)
            self.kart_mag_opis.delete(0, tk.END)
            self.load_combobox_data()
            self.odswiez_liste_magazynow()
            if hasattr(self, "stan_tree"):
                self.refresh_stan_zapasu()
            messagebox.showinfo("OK", "Dodano magazyn.")
        except Exception as e:
            messagebox.showerror("Błąd", str(e))


    def refresh_przyjecia(self):
        for item in self.przyjecia_tree.get_children():
            self.przyjecia_tree.delete(item)
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT o.OperacjaID, m.Nazwa, o.Ilo, o.DataOperacji, mag.Kod, o.Dostawca, o.Uwagi FROM OperacjeMagazynowe o JOIN Materialy m ON o.MaterialID=m.MaterialID JOIN Magazyny mag ON o.MagazynID=mag.MagazynID WHERE o.TypOperacji=? ORDER BY o.DataOperacji DESC, o.OperacjaID DESC",
            ("Przyjcie",),
        )
        for row in cur.fetchall():
            self.przyjecia_tree.insert("", "end", values=row)
        conn.close()

    def refresh_wydania(self):
        for item in self.wydania_tree.get_children():
            self.wydania_tree.delete(item)
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT o.OperacjaID, m.Nazwa, o.Ilo, o.DataOperacji, mag.Kod, o.ZlecPracownika, o.Uwagi FROM OperacjeMagazynowe o JOIN Materialy m ON o.MaterialID=m.MaterialID JOIN Magazyny mag ON o.MagazynID=mag.MagazynID WHERE o.TypOperacji=? ORDER BY o.DataOperacji DESC, o.OperacjaID DESC",
            ("Wydanie",),
        )
        for row in cur.fetchall():
            self.wydania_tree.insert("", "end", values=row)
        conn.close()

    def clear_report_table(self):
        cols = ("Lp.", "Materiał", "Magazyn", "Ilość", "Wartość", "Wyszczególnienie")
        widths = {"Lp.": 50, "Materiał": 240, "Magazyn": 90, "Ilość": 140, "Wartość": 140, "Wyszczególnienie": 280}
        self.raporty_tree["columns"] = cols
        for c in cols:
            self.raporty_tree.heading(c, text=c)
            self.raporty_tree.column(c, width=widths[c], anchor="w")
        for item in self.raporty_tree.get_children():
            self.raporty_tree.delete(item)
        self.raport_filtry_podsum_var.set("")

    def _load_rap_filtry_magazyny(self):
        if not hasattr(self, "rap_mag_filtr_combo"):
            return
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT Kod, COALESCE(Opis, '') FROM Magazyny ORDER BY Kod")
            rows = cur.fetchall()
            conn.close()
            vals = ["(wszystkie)"] + [_etykieta_magazynu(r[0], r[1]) for r in rows]
            self.rap_mag_filtr_combo["values"] = vals
            self.rap_mag_filtr_combo.current(0)
        except Exception:
            pass

    def _raport_filtr_sql_fragment(self):
        okres = self.rap_okres_entry.get().strip()
        mag_sel = self.rap_mag_filtr_combo.get()
        parts = ["1=1"]
        params = []
        if mag_sel and mag_sel != "(wszystkie)":
            kod = mag_sel.split(" - ")[0].strip()
            parts.append("mag.Kod = ?")
            params.append(kod)
        if okres:
            parts.append("strftime('%Y-%m', o.DataOperacji) = ?")
            params.append(okres)
        return " AND ".join(parts), params

    def _get_raport_rows_filtr(self):
        frag, params = self._raport_filtr_sql_fragment()
        sql = f"""
            SELECT
                o.DataOperacji,
                m.Nazwa,
                mag.Kod,
                o.TypOperacji,
                o.Ilo,
                m.Cenajedn,
                CASE WHEN o.TypOperacji = 'Wydanie' THEN -(o.Ilo * m.Cenajedn) ELSE (o.Ilo * m.Cenajedn) END,
                COALESCE(o.Dostawca, o.ZlecPracownika, '-')
            FROM OperacjeMagazynowe o
            JOIN Materialy m ON o.MaterialID = m.MaterialID
            JOIN Magazyny mag ON o.MagazynID = mag.MagazynID
            WHERE {frag}
            ORDER BY o.DataOperacji DESC, o.OperacjaID DESC
        """
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        conn.close()
        return rows

    def _raporty_columns_szczegol_ruchow(self):
        cols = ("Data", "Materiał", "Magazyn", "Typ", "Ilość", "Cena jedn.", "Wartość", "Odpowiedzialny")
        widths = {"Data": 100, "Materiał": 200, "Magazyn": 100, "Typ": 90, "Ilość": 60, "Cena jedn.": 90, "Wartość": 100, "Odpowiedzialny": 150}
        self.raporty_tree["columns"] = cols
        for c in cols:
            self.raporty_tree.heading(c, text=c)
            self.raporty_tree.column(c, width=widths[c], anchor="center")

    def _raporty_columns_stany_mies(self):
        cols = ("Okres", "Materiał", "Magazyn", "Przyjęcia", "Wydania", "Saldo", "Wartość zapasu")
        widths = {"Okres": 80, "Materiał": 200, "Magazyn": 90, "Przyjęcia": 80, "Wydania": 70, "Saldo": 70, "Wartość zapasu": 120}
        self.raporty_tree["columns"] = cols
        for c in cols:
            self.raporty_tree.heading(c, text=c)
            self.raporty_tree.column(c, width=widths[c], anchor="center")

    def generuj_raport_szczegolowy_filtr(self):
        self.raport_filtry_podsum_var.set("")
        for item in self.raporty_tree.get_children():
            self.raporty_tree.delete(item)
        self._raporty_columns_szczegol_ruchow()
        try:
            rows = self._get_raport_rows_filtr()
            suma_przyj = 0.0
            suma_wydan = 0.0
            for row in rows:
                data, material, magazyn, typ, ilosc, cena, wartosc, kto = row
                wartosc = float(wartosc or 0)
                if typ == "Przyjcie":
                    suma_przyj += wartosc
                    tag = "p"
                else:
                    suma_wydan += abs(wartosc)
                    tag = "w"
                self.raporty_tree.insert(
                    "",
                    "end",
                    values=(
                        str(data)[:10],
                        material,
                        magazyn,
                        typ,
                        ilosc,
                        f"{float(cena or 0):.2f} zł",
                        f"{wartosc:+.2f} zł",
                        kto,
                    ),
                    tags=(tag,),
                )
            saldo = suma_przyj - suma_wydan
            self.raport_filtry_podsum_var.set(
                f"Przyjęcia: +{suma_przyj:,.2f} zł  |  Wydania: -{suma_wydan:,.2f} zł  |  Saldo: {saldo:+,.2f} zł"
            )
        except Exception as e:
            messagebox.showerror("Błąd", str(e))

    def _pokaz_wykres_okno(self, fig):
        win = tk.Toplevel(self.root)
        win.title("Wykres – System GM")
        win.geometry("950x550")
        canvas = FigureCanvasTkAgg(fig, master=win)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        ttk.Button(win, text="Zamknij", command=win.destroy).pack(pady=5)

    def wykres_slupkowy_filtr(self):
        if not MATPLOTLIB_OK:
            messagebox.showerror("Brak biblioteki", "Zainstaluj matplotlib.")
            return
        try:
            rows = self._get_raport_rows_filtr()
            if not rows:
                messagebox.showinfo("Brak danych", "Brak danych dla wybranych filtrów.")
                return
            sums = defaultdict(float)
            for row in rows:
                _, material, _, typ, _, _, wartosc, _ = row
                sums[(material, typ)] += float(wartosc or 0)
            materials = sorted({m for (m, _) in sums})
            przyj = [sums.get((m, "Przyjcie"), 0.0) for m in materials]
            wyd = [abs(sums.get((m, "Wydanie"), 0.0)) for m in materials]
            fig = Figure(figsize=(10, 5), dpi=100)
            ax = fig.add_subplot(111)
            x = range(len(materials))
            w = 0.35
            ax.bar([i - w / 2 for i in x], przyj, width=w, label="Przyjęcia", color="#2ecc71", edgecolor="white")
            ax.bar([i + w / 2 for i in x], wyd, width=w, label="Wydania (|wartość|)", color="#e74c3c", edgecolor="white")
            ax.set_xticks(list(x))
            ax.set_xticklabels([n[:25] for n in materials], rotation=45, ha="right", fontsize=8)
            ax.set_ylabel("Wartość operacji [zł]")
            ax.set_title(f"Wartość operacji wg materiału — {self.rap_okres_entry.get().strip() or 'wszystkie okresy'}")
            ax.legend()
            ax.grid(axis="y", linestyle="--", alpha=0.5)
            fig.tight_layout()
            self._pokaz_wykres_okno(fig)
        except Exception as e:
            messagebox.showerror("Błąd wykresu", str(e))

    def wykres_liniowy_filtr(self):
        if not MATPLOTLIB_OK:
            messagebox.showerror("Brak biblioteki", "Zainstaluj matplotlib.")
            return
        mag_sel = self.rap_mag_filtr_combo.get()
        parts = ["1=1"]
        params = []
        if mag_sel and mag_sel != "(wszystkie)":
            parts.append("mag.Kod = ?")
            params.append(mag_sel.split(" - ")[0].strip())
        frag = " AND ".join(parts)
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT o.DataOperacji, m.Nazwa,
                    CASE WHEN o.TypOperacji='Przyjcie' THEN o.Ilo ELSE -o.Ilo END
                FROM OperacjeMagazynowe o
                JOIN Materialy m ON o.MaterialID=m.MaterialID
                JOIN Magazyny mag ON o.MagazynID=mag.MagazynID
                WHERE {frag}
                ORDER BY o.DataOperacji, o.OperacjaID
                """,
                params,
            )
            rows = cur.fetchall()
            conn.close()
            if not rows:
                messagebox.showinfo("Brak danych", "Brak danych do wykresu.")
                return
            by_date = defaultdict(lambda: defaultdict(float))
            for data, nazwa, zmiana in rows:
                ds = str(data)[:10]
                by_date[ds][nazwa] += float(zmiana or 0)
            dates = sorted(by_date.keys())
            materials = sorted({m for d in dates for m in by_date[d]})
            fig = Figure(figsize=(11, 5), dpi=100)
            ax = fig.add_subplot(111)
            for m in materials:
                cum = 0.0
                ys = []
                for ds in dates:
                    cum += by_date[ds].get(m, 0.0)
                    ys.append(cum)
                ax.plot(dates, ys, marker="o", linewidth=2, markersize=4, label=m[:20])
            ax.set_xlabel("Data operacji")
            ax.set_ylabel("Skumulowany stan ilościowy")
            ax.set_title("Zmiany stanów zapasów w czasie (filtr magazynu)")
            ax.legend(loc="best", fontsize=7, ncol=2)
            ax.grid(True, linestyle="--", alpha=0.5)
            for lbl in ax.get_xticklabels():
                lbl.set_rotation(35)
                lbl.set_horizontalalignment("right")
            fig.tight_layout()
            self._pokaz_wykres_okno(fig)
        except Exception as e:
            messagebox.showerror("Błąd wykresu", str(e))

    def raport_stany_miesieczne_filtr(self):
        self.raport_filtry_podsum_var.set("")
        for item in self.raporty_tree.get_children():
            self.raporty_tree.delete(item)
        self._raporty_columns_stany_mies()
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    strftime('%Y-%m', o.DataOperacji) AS okres,
                    m.Nazwa,
                    mag.Kod,
                    SUM(CASE WHEN o.TypOperacji='Przyjcie' THEN o.Ilo ELSE 0 END),
                    SUM(CASE WHEN o.TypOperacji='Wydanie' THEN o.Ilo ELSE 0 END),
                    SUM(CASE WHEN o.TypOperacji='Przyjcie' THEN o.Ilo ELSE -o.Ilo END),
                    CAST(
                        (SUM(CASE WHEN o.TypOperacji='Przyjcie' THEN o.Ilo ELSE 0 END) -
                         SUM(CASE WHEN o.TypOperacji='Wydanie' THEN o.Ilo ELSE 0 END)) * MAX(m.Cenajedn) AS REAL
                    )
                FROM OperacjeMagazynowe o
                JOIN Materialy m ON o.MaterialID=m.MaterialID
                JOIN Magazyny mag ON o.MagazynID=mag.MagazynID
                GROUP BY strftime('%Y-%m', o.DataOperacji), m.Nazwa, mag.Kod
                ORDER BY okres, m.Nazwa
                """
            )
            rows = cur.fetchall()
            conn.close()
            for row in rows:
                okres, material, magazyn, przyj, wyd, saldo, wartosc = row
                w = float(wartosc or 0)
                self.raporty_tree.insert(
                    "",
                    "end",
                    values=(okres, material, magazyn, przyj, wyd, saldo, f"{w:.2f} zł"),
                )
            self.raport_filtry_podsum_var.set(f"Łącznie wierszy: {len(rows)}")
        except Exception as e:
            messagebox.showerror("Błąd", str(e))

    def raport_miesieczny_szczegolowy(self):
        self.clear_report_table()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                strftime('%Y-%m', o.DataOperacji) AS Miesiac,
                m.Nazwa,
                mag.Kod,
                SUM(CASE WHEN o.TypOperacji='Przyjcie' THEN o.Ilo ELSE 0 END),
                SUM(CASE WHEN o.TypOperacji='Wydanie' THEN o.Ilo ELSE 0 END),
                SUM(CASE WHEN o.TypOperacji='Przyjcie' THEN o.Ilo ELSE -o.Ilo END)
            FROM OperacjeMagazynowe o
            JOIN Materialy m ON o.MaterialID=m.MaterialID
            JOIN Magazyny mag ON o.MagazynID=mag.MagazynID
            WHERE o.DataOperacji IS NOT NULL
            GROUP BY strftime('%Y-%m', o.DataOperacji), m.Nazwa, mag.Kod
            ORDER BY Miesiac DESC, mag.Kod, m.Nazwa
            """
        )
        for lp, row in enumerate(cur.fetchall(), 1):
            mies, nazwa, mag, przyj, wyd, saldo = row
            self.raporty_tree.insert(
                "",
                "end",
                values=(lp, nazwa, mag, f"P:{przyj} / W:{wyd}", f"Saldo: {saldo}", mies),
            )
        conn.close()

    def raport_ranking_wydan(self):
        """Ranking wg sumy ilości wydań (jak u Amelki — przycisk 4)."""
        self.clear_report_table()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                m.Nazwa,
                COUNT(o.OperacjaID),
                SUM(o.Ilo),
                SUM(o.Ilo * m.Cenajedn)
            FROM OperacjeMagazynowe o
            JOIN Materialy m ON o.MaterialID=m.MaterialID
            WHERE o.TypOperacji='Wydanie'
            GROUP BY m.Nazwa
            ORDER BY SUM(o.Ilo) DESC, m.Nazwa
            """
        )
        for lp, row in enumerate(cur.fetchall(), 1):
            nazwa, liczba, ilosc, wartosc = row
            self.raporty_tree.insert(
                "",
                "end",
                values=(
                    lp,
                    nazwa,
                    "-",
                    f"{ilosc} szt.",
                    f"{float(wartosc or 0):.2f} PLN",
                    f"Liczba operacji: {liczba}",
                ),
            )
        conn.close()

    def raport_stan_zapasu(self):
        self.clear_report_table()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                m.Nazwa, 
                mag.Kod, 
                SUM(CASE WHEN o.TypOperacji = 'Przyjcie' THEN o.Ilo ELSE -o.Ilo END) AS Stan,
                SUM(CASE WHEN o.TypOperacji = 'Przyjcie' THEN o.Ilo * m.Cenajedn ELSE -(o.Ilo * m.Cenajedn) END) AS Wartosc,
                m.Cenajedn
            FROM Materialy m
            JOIN OperacjeMagazynowe o ON m.MaterialID = o.MaterialID
            JOIN Magazyny mag ON o.MagazynID = mag.MagazynID
            GROUP BY m.Nazwa, mag.Kod
            HAVING Stan != 0
            ORDER BY mag.Kod, m.Nazwa
        """)
        total = 0.0
        for lp, row in enumerate(cur.fetchall(), 1):
            nazwa, magazyn, ilosc, wartosc, cena = row
            val = float(wartosc or 0)
            total += val
            self.raporty_tree.insert("", "end", values=(
                lp, nazwa, magazyn, f"{ilosc} szt.", f"{val:.2f} PLN", f"Cena: {cena:.2f}"
            ))
        self.raporty_tree.insert("", "end", values=("", "RAZEM", "", "", f"{total:.2f} PLN", ""))
        conn.close()

    def raport_miesieczny(self):
        self.clear_report_table()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                strftime('%Y-%m', o.DataOperacji) AS Miesiac,
                SUM(CASE WHEN o.TypOperacji = 'Przyjcie' THEN o.Ilo ELSE 0 END) AS Przyjecia,
                SUM(CASE WHEN o.TypOperacji = 'Wydanie' THEN o.Ilo ELSE 0 END) AS Wydania,
                SUM(CASE WHEN o.TypOperacji = 'Przyjcie' THEN o.Ilo ELSE -o.Ilo END) AS Saldo
            FROM OperacjeMagazynowe o
            GROUP BY Miesiac
            ORDER BY Miesiac DESC
        """)
        for lp, row in enumerate(cur.fetchall(), 1):
            miesiac, przyjecia, wydania, saldo = row
            self.raporty_tree.insert("", "end", values=(
                lp, "Podsumowanie okresu", "-", 
                f"P:{przyjecia} / W:{wydania}", f"Saldo: {saldo}", miesiac
            ))
        conn.close()

    def raport_ruchy(self):
        self.clear_report_table()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                o.DataOperacji,
                m.Nazwa,
                mag.Kod,
                o.TypOperacji,
                o.Ilo,
                m.Cenajedn,
                CASE WHEN o.TypOperacji = 'Przyjcie' THEN o.Ilo * m.Cenajedn ELSE -(o.Ilo * m.Cenajedn) END AS Wartosc,
                COALESCE(o.Dostawca, o.ZlecPracownika, '-') AS Kto
            FROM OperacjeMagazynowe o
            JOIN Materialy m ON o.MaterialID = m.MaterialID
            JOIN Magazyny mag ON o.MagazynID = mag.MagazynID
            ORDER BY o.DataOperacji DESC, o.OperacjaID DESC
        """)
        for lp, row in enumerate(cur.fetchall(), 1):
            data, nazwa, magazyn, typ, ilosc, cena, wartosc, kto = row
            self.raporty_tree.insert("", "end", values=(lp, nazwa, magazyn, f"{typ}: {ilosc}", f"{float(wartosc or 0):.2f} PLN", f"{data} | {kto}"))
        conn.close()
    
    def raport_ranking(self):
        self.clear_report_table()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                m.Nazwa, 
                mag.Kod, 
                SUM(CASE WHEN o.TypOperacji = 'Przyjcie' THEN o.Ilo ELSE -o.Ilo END) AS Stan
            FROM Materialy m
            JOIN OperacjeMagazynowe o ON m.MaterialID = o.MaterialID
            JOIN Magazyny mag ON o.MagazynID = mag.MagazynID
            GROUP BY m.Nazwa, mag.Kod
            HAVING Stan < 20
            ORDER BY Stan ASC
        """)
        for lp, row in enumerate(cur.fetchall(), 1):
            nazwa, mag, stan = row
            self.raporty_tree.insert("", "end", values=(lp, nazwa, mag, f"{stan} szt.", "-", "NISKI STAN"))
        conn.close()

    def raport_niskie_stany(self):
        """Materiały o stanie < 20 z podziałem na przyjęcia i wydania (jak u Amelki)."""
        self.clear_report_table()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT
                m.Nazwa,
                mag.Kod,
                SUM(CASE WHEN o.TypOperacji = 'Przyjcie' THEN o.Ilo ELSE 0 END) AS Przyjecia,
                SUM(CASE WHEN o.TypOperacji = 'Wydanie' THEN o.Ilo ELSE 0 END) AS Wydania,
                SUM(CASE WHEN o.TypOperacji = 'Przyjcie' THEN o.Ilo ELSE -o.Ilo END) AS StanKon
            FROM Materialy m
            JOIN OperacjeMagazynowe o ON m.MaterialID = o.MaterialID
            JOIN Magazyny mag ON o.MagazynID = mag.MagazynID
            GROUP BY m.Nazwa, mag.Kod
            HAVING SUM(CASE WHEN o.TypOperacji = 'Przyjcie' THEN o.Ilo ELSE -o.Ilo END) < 20
            ORDER BY SUM(CASE WHEN o.TypOperacji = 'Przyjcie' THEN o.Ilo ELSE -o.Ilo END) ASC
        """)
        for lp, row in enumerate(cur.fetchall(), 1):
            nazwa, mag, przyj, wyd, stan = row
            self.raporty_tree.insert("", "end", values=(lp, nazwa, mag, f"{stan} szt.", f"P:{przyj} / W:{wyd}", "NISKI STAN"))
        conn.close()

    def raport_ranking_ruchu(self):
        self.clear_report_table()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT poz, nazwa, liczba, przyj, wyd, ruch FROM (
                SELECT
                    RANK() OVER (ORDER BY SUM(o.Ilo) DESC) AS poz,
                    m.Nazwa AS nazwa,
                    COUNT(o.OperacjaID) AS liczba,
                    SUM(CASE WHEN o.TypOperacji = 'Przyjcie' THEN o.Ilo ELSE 0 END) AS przyj,
                    SUM(CASE WHEN o.TypOperacji = 'Wydanie' THEN o.Ilo ELSE 0 END) AS wyd,
                    SUM(o.Ilo) AS ruch
                FROM OperacjeMagazynowe o
                JOIN Materialy m ON m.MaterialID = o.MaterialID
                GROUP BY m.Nazwa
            ) AS ranked
            ORDER BY poz, nazwa
        """)
        for row in cur.fetchall():
            poz, nazwa, liczba, przyjecia, wydania, ruch = row
            self.raporty_tree.insert("", "end", values=(
                poz, nazwa, "-", f"P:{przyjecia} / W:{wydania}", f"Ruch: {ruch}", f"Operacji: {liczba}"
            ))
        conn.close()

    def export_csv(self):
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("""
            SELECT 
                m.Nazwa, 
                mag.Kod, 
                SUM(CASE WHEN o.TypOperacji = 'Przyjcie' THEN o.Ilo ELSE -o.Ilo END) AS StanIlosc,
                SUM(CASE WHEN o.TypOperacji = 'Przyjcie' THEN o.Ilo * m.Cenajedn ELSE -(o.Ilo * m.Cenajedn) END) AS StanWartosc
            FROM OperacjeMagazynowe o
            JOIN Materialy m ON o.MaterialID = m.MaterialID
            JOIN Magazyny mag ON o.MagazynID = mag.MagazynID
            GROUP BY m.Nazwa, mag.Kod
            ORDER BY mag.Kod ASC, m.Nazwa ASC;
            """)
            filename = APP_DIR / f"raport_zapasu_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            with open(filename, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Materiał", "Magazyn", "Ilość", "Wartość PLN"])
                writer.writerows(cur.fetchall())
            conn.close()
            messagebox.showinfo("Sukces", f"Raport wyeksportowany do:\n{filename}")
        except Exception as e:
            messagebox.showerror("Błąd", str(e))

    def configure_bar_chart(self):
        self.chart_mode = "bar"
        self.chart_message.config(text="Wybrano tryb słupkowy. Kliknij 'Rysuj wykres'.")

    def configure_line_chart(self):
        self.chart_mode = "line"
        self.chart_message.config(text="Wybrano tryb liniowy. Kliknij 'Rysuj wykres'.")

    def clear_chart(self):
        if self.current_chart_canvas is not None:
            try:
                self.current_chart_canvas.get_tk_widget().pack_forget()
                self.current_chart_canvas.get_tk_widget().destroy()
            except Exception:
                pass
            self.current_chart_canvas = None
        if self.current_figure is not None:
            try:
                self.current_figure.clear()
            except Exception:
                pass
            self.current_figure = None
        for child in self.chart_canvas_holder.winfo_children():
            child.destroy()
        self.chart_message.config(text="Wykres wyczyszczony.")
        self.root.update_idletasks()

    def draw_embedded_chart(self):
        if not MATPLOTLIB_OK:
            messagebox.showerror("Brak biblioteki", "Matplotlib nie jest dostępny. Zainstaluj pakiet matplotlib.")
            return

        metric_label = self.chart_metric_combo.get()
        group_label = self.chart_group_combo.get()
        type_label = self.chart_type_combo.get()
        try:
            limit = max(1, int(self.chart_limit_entry.get().strip()))
        except Exception:
            limit = 10

        metric_map = {"Ilość": "Ilo", "Wartość": "wartosc", "Liczba operacji": "liczba"}
        metric = metric_map.get(metric_label, "Ilo")

        if group_label == "Miesiąc":
            xexpr = "strftime('%Y-%m', o.DataOperacji)"
            xlabel = "Miesiąc"
            order_expr = "x ASC"
        elif group_label == "Magazyn":
            xexpr = "mag.Kod"
            xlabel = "Magazyn"
            order_expr = "y DESC, x ASC"
        else:
            xexpr = "m.Nazwa"
            xlabel = "Materiał"
            order_expr = "y DESC, x ASC"

        if metric == "Ilo":
            agg = "SUM(o.Ilo)"
            ylabel = "Ilość"
        elif metric == "wartosc":
            agg = "SUM(o.Ilo * m.Cenajedn)"
            ylabel = "Wartość"
        else:
            agg = "COUNT(o.OperacjaID)"
            ylabel = "Liczba operacji"

        where_clause = ""
        params = []
        if type_label in ("Przyjcie", "Wydanie"):
            where_clause = "WHERE o.TypOperacji = ?"
            params.append(type_label)

        query = f"""
            SELECT {xexpr} AS x, {agg} AS y
            FROM OperacjeMagazynowe o
            JOIN Materialy m ON m.MaterialID = o.MaterialID
            JOIN Magazyny mag ON mag.MagazynID = o.MagazynID
            {where_clause}
            GROUP BY x
            ORDER BY {order_expr}
            LIMIT ?
        """
        params.append(limit)

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()
        conn.close()

        if not rows:
            messagebox.showwarning("Brak danych", "Brak danych do wygenerowania wykresu.")
            return

        self.clear_chart()

        x_values = [r[0] for r in rows]
        y_values = [float(r[1] or 0) for r in rows]

        fig = Figure(figsize=(8.8, 3.6), dpi=100)
        ax = fig.add_subplot(111)

        if self.chart_mode == "bar":
            ax.bar(x_values, y_values, color="#2a6fdb")
            ax.set_title(f"Wykres słupkowy: {metric_label} wg {group_label}")
        else:
            ax.plot(x_values, y_values, marker="o", linewidth=2.0, color="#0f766e")
            ax.set_title(f"Wykres liniowy: {metric_label} wg {group_label}")

        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=0.25)
        for label in ax.get_xticklabels():
            label.set_rotation(35)
            label.set_horizontalalignment("right")

        fig.tight_layout()
        self.current_figure = fig
        self.current_chart_canvas = FigureCanvasTkAgg(fig, master=self.chart_canvas_holder)
        self.current_chart_canvas.draw_idle()
        widget = self.current_chart_canvas.get_tk_widget()
        widget.pack(fill="both", expand=True)
        widget.update_idletasks()
        self.chart_message.config(text=f"Wyświetlono wykres {self.chart_mode} dla: {metric_label} / {group_label}.")
        self.root.update_idletasks()


def main():
    root = tk.Tk()
    root.withdraw()
    if not database_schema_ok():
        messagebox.showerror(
            "Brak bazy lub tabel",
            "Nie znaleziono poprawnej bazy SQLite albo tabela Materialy nie istnieje.\n\n"
            f"Oczekiwany plik: {DBFILE}\n"
            "Uruchom inicjalizację bazy (np. init_db.py) albo skopiuj gmsystem.db do folderu aplikacji.",
        )
        sys.exit(1)
    root.deiconify()
    app = MagazynApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

'''
Zadanie 1. Napisz zapytanie SQL aby wyświetlać raporty dla funkcji: raport_stan_zapasu, raport_miesieczny, raport_ruchy, raport_ranking i export_csv.


Zadanie 2. Napisz zapytanie SQL wyświetlające materiały o niskim stanie magazynowym. 
Stan oblicz jako suma przyjęć minus suma wydań dla każdego materiału w każdym magazynie. 
Wyświetl nazwę materiału, magazyn, sumę przyjęć, sumę wydań i stan końcowy. 
Pokaż tylko te pozycje, dla których stan jest niższy niż 20. Wynik posortuj rosnąco według stanu.

Zadanie 3. Napisz zapytanie SQL tworzące ranking materiałów o największym ruchu magazynowym. 
Przez ruch rozumiej sumę wszystkich ilości z operacji przyjęć i wydań. Wyświetl nazwę materiału, 
liczbę operacji, sumę przyjęć, sumę wydań oraz łączny ruch. Wynik posortuj malejąco według łącznego ruchu.
W wersji rozszerzonej dodaj pozycję rankingową.

Zadania dla grup projektowych

Zadanie 4: przygotuj raport trendów miesięcznych dla operacji przyjęć i wydań. 
Oblicz dla każdego miesiąca łączną ilość przyjęć i wydań, a następnie przedstaw wynik w tabeli oraz na wykresie liniowym lub słupkowym.

Zadanie 5: przygotuj raport obrotów magazynowych według materiału. 
Dla dowolnego ateriału oblicz sumę przyjęć, sumę wydań i łączny obrót miesiąc po miesiącu, a wynik pokaż w formie wykresu słupkowego.



'''
