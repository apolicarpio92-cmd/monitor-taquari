MONITOR TAQUARI - CLOUD

Arquivos principais:

app.py
monitor_cloud.py
barragens.py
requirements.txt
render.yaml

Render:

Build Command:
pip install -r requirements.txt

Start Command:
gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120

Health:
https://SEU-SERVICO.onrender.com/health

Dashboard:
https://SEU-SERVICO.onrender.com/
