"""Общие настройки проекта: пути, календарь акций, оформление графиков."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
DATA_REF = ROOT / "data" / "reference"
DATA_MART = ROOT / "data" / "mart"
SQL_DIR = ROOT / "sql"
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"

SEED = 42
START_DATE = "2026-01-05"  # понедельник, неделя 0
N_WEEKS = 28
N_STORES = 20

# Окна анализа (номера недель от START_DATE)
PRE_WEEKS = 4      # недель до старта акции в окне DiD
POST_WEEKS = 2     # недель после акции для event study
PROMO_WEEKS = 3    # длительность каждой волны

# Фиксированные затраты на волну акции: материалы, размещение, работа персонала
FIXED_COST_PER_WAVE = 30_000

# Цвета графиков
INK = "#141A2E"
ACCENT = "#2C52C4"
WARM = "#B5631A"
GRID = "#D8DEEA"
MUTED = "#6B7590"
