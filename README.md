# AutoDNA Coder

Streamlit app untuk menganalisis kutipan berita dan mengekspor hasil ke CSV, Excel, JSON, GraphML, dan format `.dna` untuk Discourse Network Analyzer.

## Run Local

```bash
pip install -r requirements.txt
python -m streamlit run app.py
```

## Deploy ke Streamlit Community Cloud

1. Push repository ini ke GitHub.
2. Buka `https://share.streamlit.io`.
3. Pilih repository GitHub.
4. Set main file path ke `app.py`.
5. Deploy.

Untuk file `.dna`, gunakan `Versi database DNA = 3.0` jika DNA menolak database `3.1.0`.
