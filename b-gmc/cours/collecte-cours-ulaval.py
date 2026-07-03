
from pathlib import Path
import csv, re, sys, time
import requests
from unidecode import unidecode

BASE_URL = "https://www.ulaval.ca/etudes/cours/"
DOSSIER_CACHE = "cache_html"

def construire_url(sigle, titre):
    titre = unidecode(titre.lower())
    titre = titre.replace("'", "").replace("’", "")
    titre = re.sub(r"[^a-z0-9 -]", "", titre)
    titre = re.sub(r"\s+", "-", titre.strip())
    return f"{BASE_URL}{sigle.lower()}-{titre}"

def lire_csv(fichier_csv):
    cours = []
    with open(fichier_csv, encoding="utf-8-sig") as f:
        premiere = f.readline()
        f.seek(0)
        sep = ";" if premiere.count(";") >= premiere.count(",") else ","
        for ligne in csv.reader(f, delimiter=sep):
            if len(ligne) >= 2:
                cours.append((ligne[0].strip(), ligne[1].strip()))
    return cours

def telecharger_html(url):
    r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    return r.text

def sauvegarder_html(sigle, html):
    d = Path(DOSSIER_CACHE)
    d.mkdir(exist_ok=True)
    (d / f"{sigle}.html").write_text(html, encoding="utf-8")

def main(fichier_csv):
    cours = lire_csv(fichier_csv)
    print(f"{len(cours)} cours trouvés")
    for sigle, titre in cours:
        try:
            url = construire_url(sigle, titre)
            html = telecharger_html(url)
            sauvegarder_html(sigle, html)
            print("OK", sigle)
            time.sleep(0.5)
        except Exception as e:
            print("ERREUR", sigle, e)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python collecte_ulaval.py fichier.csv")
    else:
        main(sys.argv[1])
