# DDM Tool (Standalone)

Dividend Discount Model untuk emiten IDX, termasuk bank dan lembaga keuangan
lain. Folder ini berdiri sendiri, tidak butuh folder tool DCF sama sekali.

## Kenapa ada file berawalan `s0` di sini

Tujuh file berikut BUKAN sisa dari tool DCF, mereka adalah mesin bersama
yang memang dibutuhkan DDM juga:

| File | Dipakai untuk |
|---|---|
| `s01_fetch.py` | Ambil laporan keuangan dan harga dari yfinance, konversi USD ke IDR |
| `s02_lineitems.py` | Ekstraksi pos laporan keuangan (laba bersih, ekuitas, dll) |
| `s05_beta.py` | Regresi beta harian terhadap IHSG |
| `s06_wacc.py` | CAPM. DDM hanya memakai fungsi `cost_of_equity()` dari file ini, TIDAK memakai tahap penggabungan WACC |
| `config.py` | Asumsi risk-free rate, ERP, beta floor, dll |
| `utils.py` | Helper pencarian label yfinance, pencatatan flag data |
| `theme.py` | Design token navy/ice blue, CSS, Poppins |

Kalau Anda juga punya tool DCF terpisah, ketujuh file ini akan identik
persis dengan yang ada di folder itu. Itu memang disengaja, keduanya
berbagi mesin yang sama.

## Catatan metodologis utama

Dividen didiskontokan dengan **Cost of Equity, bukan WACC**. Dividen adalah
arus kas kepada pemegang saham biasa saja, memakai WACC akan overvalue
secara sistematis, terutama untuk bank yang bobot utangnya besar.

## Cara pakai

```bash
python -m venv venv
venv\Scripts\activate.bat        # Windows CMD
pip install -r requirements.txt

python test_ddm.py               # validasi rumus tanpa jaringan
streamlit run ddm_app.py         # jalankan web app
```

Sidebar berisi input ticker (cukup kode IDX, `.JK` ditambahkan otomatis)
dan empat slider: risk-free rate, equity risk premium, terminal growth,
horizon proyeksi. Coba dengan BBCA, BBRI, atau BMRI, karena DDM justru
dirancang untuk emiten keuangan.

## Peta modul DDM murni

| File | Section | Isi |
|---|---|---|
| `ddm_config.py` | - | Asumsi dan threshold khusus DDM |
| `d01_dividends.py` | D1 | Riwayat dividen dari `Ticker.dividends`, agregasi tahunan |
| `d02_screening.py` | D2 | 10 gate kelayakan. Financials DITERIMA di sini |
| `d03_drivers.py` | D3 | Payout ratio, ROE, Sustainable Growth Rate |
| `d04_forecast.py` | D4 | Proyeksi DPS dengan fade linear |
| `d05_terminal.py` | D5 | Gordon Growth, uji konsistensi payout terminal |
| `d06_valuation.py` | D6 | Diskonto, nilai per saham, rekomendasi |
| `d07_crosscheck.py` | D7 | Fair P/BV dan Residual Income |
| `d08_sensitivity.py` | D8 | Grid Ke x terminal growth |
| `d09_scenario.py` | D9 | Bull / Base / Bear |
| `ddm_main.py` | - | Orkestrator |
| `ddm_report.py` | - | Laporan teks |
| `ddm_app.py` | UI | Aplikasi Streamlit |
| `ddm_charts.py` | UI | Lima chart Plotly |
| `test_ddm.py` | - | Validasi matematika dengan data sintetis |

## Gate screening

| # | Gate | Kriteria |
|---|---|---|
| 1 | Rekam jejak dividen | >= 3 dari 5 tahun lengkap terakhir |
| 2 | Kontinuitas | Tahun lengkap terakhir wajib membayar |
| 3 | Laporan tahunan | >= 4 tahun |
| 4 | Laba bersih | Positif >= 2 dari 3 tahun terakhir |
| 5 | Laba terakhir | Positif |
| 6 | Total ekuitas | Positif |
| 7 | Market cap | >= IDR 1 triliun |
| 8 | Payout ratio | 5% sampai 110% |
| 9 | Volatilitas DPS (CV) | <= 1.20 |
| 10 | DPS tahun terakhir | > 0 |

## Deploy ke Streamlit Community Cloud

Sama seperti tool lain: push folder ini ke GitHub, buka share.streamlit.io,
New app, Main file path isi `ddm_app.py`, Deploy.

## Keterbatasan

- Hanya menangkap nilai yang benar-benar dibagikan sebagai kas. Emiten
  berpayout rendah akan understate.
- Dividen diagregasi per tahun kalender dari ex-date, bukan tahun buku RUPS.
- Payout memakai konvensi lagged (DPS tahun T dipasangkan EPS tahun T-1).
- Dividen spesial ditandai, tidak dipisahkan otomatis.
- Corporate action dan peristiwa setelah tanggal neraca tidak diperhitungkan.

## Disclaimer

Disclaimer On - Abida Massi Armand. Output dihasilkan model otomatis
berbasis data publik dan asumsi pengguna. Belum diverifikasi terhadap
laporan keuangan resmi maupun keputusan RUPS, bukan rekomendasi investasi.
