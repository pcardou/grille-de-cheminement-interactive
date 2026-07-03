# -*- coding: utf-8 -*-
"""
Created on Tue Jun  9 10:30:07 2026

@author: PHCAR16
"""

from pathlib import Path
import csv
import re

from bs4 import BeautifulSoup


# ------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------

BASE_DIR = Path(__file__).parent

DOSSIER_HTML = BASE_DIR / "pages-html"

# ------------------------------------------------------------------
# CONSTANTES
# ------------------------------------------------------------------

MODE_MAP = {
    "En classe": "P",
    "À distance": "D",
    "Classe virtuelle synchrone": "D",
    "Classe virtuelle": "D",
    "Distance": "D",
    "Hybride": "H",
    "Comodal": "C",
}

JOUR_MAP = {
    "Lundi": 1,
    "Mardi": 2,
    "Mercredi": 3,
    "Jeudi": 4,
    "Vendredi": 5,
    "Samedi": 6,
    "Dimanche": 7,
}

SESSION_MAP = {
    "Automne": "A",
    "Hiver": "H",
    "Été": "E",
    "Ete": "E",
}

# ------------------------------------------------------------------
# OUTILS
# ------------------------------------------------------------------

def normaliser_heure(texte):

    texte = texte.strip()

    m = re.search(r"(\d+)h(\d*)", texte)

    if not m:
        return ""

    h = int(m.group(1))
    mn = int(m.group(2)) if m.group(2) else 0

    return f"{h:02d}:{mn:02d}"


def extraire_session(texte):

    m = re.search(
        r"(Automne|Hiver|Été|Ete)\s+(\d{4})",
        texte,
        flags=re.IGNORECASE
    )

    if not m:
        return None

    saison = m.group(1)
    annee = m.group(2)

    code_saison = SESSION_MAP[saison]

    return f"{code_saison}{annee[-2:]}"


def deduire_sessions_futures(sessions):

    futures = set()

    for session in sessions:

        saison = session[0]
        annee = int(session[1:])

        for i in range(1, 6):
            futures.add(f"{saison}{annee+i:02d}")

    return sorted(futures)


def parse_section_header(bloc, sigle):

    details = bloc.select_one(".header--content-details")
    items = []

    if details is not None:
        items = [
            it.get_text(" ", strip=True)
            for it in details.select(".item")
        ]

    if not items:
        header = bloc.select_one("p.toggle-section--header")
        if header is not None:
            items = [
                part.strip()
                for part in re.split(r"[\|\s]+", header.get_text(" ", strip=True))
                if part.strip()
            ]

    header_text = " ".join(items)
    lower_text = header_text.lower()

    is_linked = (
        "sections liées" in lower_text
        or "section liée" in lower_text
        or "sections liees" in lower_text
    )

    mode = "?"
    for item in items:
        if item in MODE_MAP:
            mode = MODE_MAP[item]
            break

    section = None
    for item in items:
        candidate = item.strip()
        if not candidate or candidate == sigle:
            continue
        if candidate in MODE_MAP:
            continue
        if candidate in {"–", "-", "Restrictions", "Sections liées", "Section liée", "Sections liees"}:
            continue
        if re.fullmatch(r"[A-Z0-9]{1,3}", candidate):
            section = candidate
            break

    return {
        "section": section,
        "mode": mode,
        "is_linked": is_linked,
        "header_text": header_text,
    }


# ------------------------------------------------------------------
# EXTRACTION COURS
# ------------------------------------------------------------------

def extraire_credits(soup):

    texte = soup.get_text(" ", strip=True)

    m = re.search(r"(\d+)\s+crédit", texte, flags=re.IGNORECASE)

    if m:
        return int(m.group(1))

    return None


def extraire_prealables(soup):

    # Chercher d'abord le div dédié aux préalables (cours universitaires)
    div = soup.select_one(".fe--prealables")

    if div:
        p = div.select_one("p.etiquette-container")
        if p:
            return p.get_text(" ", strip=True)
        # Retirer le titre "Préalables" et garder le reste
        for h in div.find_all(["h1", "h2", "h3"]):
            h.decompose()
        return div.get_text(" ", strip=True)

    # Fallback : chercher dans fe--message (préalables préuniversitaires)
    for msg in soup.select(".fe--message"):
        txt = msg.get_text(" ", strip=True)
        if "réalable" in txt.lower():
            return txt

    return ""


def extraire_sigles_preuniversitaires(soup):

    pattern_section = re.compile(
        r"Préalables préuniversitaires nécessaires s[''']il y a lieu\s*:\s*([^\n]+)",
        re.IGNORECASE
    )

    texte_prealables = ""

    for msg in soup.select(".fe--message"):
        texte = msg.get_text("\n", strip=True)
        m = pattern_section.search(texte)
        if m:
            texte_prealables = m.group(1).strip()
            break

    if not texte_prealables:
        texte = soup.get_text("\n", strip=True)
        m = pattern_section.search(texte)
        if m:
            texte_prealables = m.group(1).strip()

    matches = re.findall(r'\b([A-Z]{3}-\d{4})\b[ \t]*(\*)?', texte_prealables)
    return [sigle + ' *' if asterisk else sigle for sigle, asterisk in matches]


def extraire_url(soup):

    canonical = soup.find("link", rel="canonical")

    if canonical:
        return canonical.get("href", "")

    return ""


# ------------------------------------------------------------------
# EXTRACTION HORAIRES
# ------------------------------------------------------------------

def extraire_plages(section, direct_seulement=False):

    plages = set()

    if direct_seulement:
        # Ne garder que les UL qui ne sont pas à l'intérieur d'un toggle-section imbriqué
        blocs = []
        for ul in section.find_all("ul", class_="section-cours--liste"):
            imbrique = False
            for ancetre in ul.parents:
                if ancetre is section:
                    break
                if "toggle-section" in (ancetre.get("class") or []):
                    imbrique = True
                    break
            if not imbrique:
                blocs.append(ul)
    else:
        blocs = section.select("ul.section-cours--liste")

    for bloc in blocs:

        texte = bloc.get_text("\n", strip=True)

        m_jour = re.search(
            r"Journ[eé]e:\s*(.+)",
            texte
        )

        m_horaire = re.search(
            r"Horaire:\s*De\s*(\d+h\d*)\s*[aà]\s*(\d+h\d*)",
            texte
        )

        if not m_jour:
            continue

        if not m_horaire:
            continue

        jour_nom = m_jour.group(1).strip()

        if jour_nom not in JOUR_MAP:
            continue

        jour = JOUR_MAP[jour_nom]

        debut = normaliser_heure(m_horaire.group(1))
        fin = normaliser_heure(m_horaire.group(2))

        plages.add((jour, debut, fin))

    return sorted(plages)


# ------------------------------------------------------------------
# EXTRACTION SECTIONS
# ------------------------------------------------------------------

def extraire_sections(session_div, cours_sigle):

    sections = []
    shared_plages = []

    blocs = session_div.select("div.toggle-section")

    for bloc in blocs:

        header = parse_section_header(bloc, cours_sigle)
        plages = extraire_plages(bloc)

        if header["is_linked"]:
            # Récupérer uniquement les plages directes (pas celles des sous-sections)
            shared_plages = extraire_plages(bloc, direct_seulement=True)
            continue

        if header["section"] is None:
            header["section"] = "A"

        sections.append(
            {
                "sigle": cours_sigle,
                "section": header["section"],
                "mode": header["mode"],
                "plages": plages,
            }
        )

    if shared_plages:
        for section in sections:
            section["plages"] = sorted(
                set(section["plages"]) | set(shared_plages)
            )

    return sections


# ------------------------------------------------------------------
# EXTRACTION DES VERSIONS
# ------------------------------------------------------------------

def extraire_versions(soup, cours_sigle):

    versions = []

    blocs = soup.select("div.collapsible-sections")

    for bloc in blocs:

        titre = bloc.select_one(
            "p.controls-title"
        )

        if titre is None:
            continue

        session = extraire_session(
            titre.get_text(" ", strip=True)
        )

        if session is None:
            continue

        sections = extraire_sections(bloc, cours_sigle)

        versions.append(
            {
                "session": session,
                "sections": sections
            }
        )

    return versions


# ------------------------------------------------------------------
# EXTRACTION D'UN FICHIER
# ------------------------------------------------------------------

def analyser_fichier(html_file):

    with open(html_file, encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    sigle = html_file.stem[:8].upper()

    titre = ""

    titre_tag = soup.find("h1")

    if titre_tag:
    
        titre = titre_tag.get_text(" ", strip=True)
    
        titre = re.sub(
            r"^[A-Z]{3}-\d{4}\s*",
            "",
            titre
        )

    prealables = extraire_prealables(soup)
    sigles_preuniv = extraire_sigles_preuniversitaires(soup)
    if sigles_preuniv:
        extra = " ET ".join(sigles_preuniv)
        marqueur = re.compile(
            r"\s*Préalables préuniversitaires nécessaires s[''']il y a lieu\s*:.*",
            re.IGNORECASE | re.DOTALL
        )
        m = marqueur.search(prealables)
        if m:
            # Le marqueur est déjà dans les préalables réguliers : remplacer
            # le marqueur et tout ce qui suit par les sigles extraits
            avant = prealables[:m.start()].strip()
            prealables = (avant + " ET " + extra) if avant else extra
        elif prealables:
            # Pas de doublon : encapsuler les deux parties entre parenthèses
            prealables = f"({prealables}) ET ({extra})"
        else:
            prealables = extra

    cours = {
        "sigle": sigle,
        "titre": titre,
        "credits": extraire_credits(soup),
        "prealables": prealables,
        "url": extraire_url(soup),
        "versions": extraire_versions(soup, sigle)
    }

    return cours


# ------------------------------------------------------------------
# EXPORT CSV
# ------------------------------------------------------------------

def charger_titres_courts_et_couleurs():
    """
    Lit format-pastilles.csv (encodage Windows-1252, séparateur ;) pour extraire
    les titres courts et couleurs associés à chaque sigle de cours.
    Colonnes attendues : sigle ; titre ; titre_court ; couleur
    """

    mapping = {}
    pastilles_csv = BASE_DIR / "format-pastilles.csv"

    with open(pastilles_csv, newline="", encoding="utf-8-sig") as f:

        reader = csv.reader(f, delimiter=";")
        next(reader, None)  # ignorer l'en-tête

        for row in reader:

            if len(row) < 4:
                continue

            sigle = row[0].strip()
            if not sigle:
                continue

            mapping[sigle] = {
                "titre_court": row[2].strip(),
                "couleur":     row[3].strip(),
            }

    return mapping


def exporter(cours_liste):

    titres_couleurs = charger_titres_courts_et_couleurs()

    cours_csv = BASE_DIR / "cours.csv"
    plages_csv = BASE_DIR / "plages-horaires.csv"

    with open(cours_csv, "w", newline="", encoding="utf-8") as f:

        writer = csv.writer(f, delimiter=";")

        writer.writerow(
            ["sigle", "titre", "credits", "prealables", "url", "titre_court", "couleur"]
        )

        for cours in cours_liste:

            tc = titres_couleurs.get(cours["sigle"], {})

            writer.writerow([
                cours["sigle"],
                cours["titre"],
                cours["credits"],
                cours["prealables"],
                cours["url"],
                tc.get("titre_court", ""),
                tc.get("couleur", ""),
            ])

    with open(plages_csv, "w", newline="", encoding="utf-8") as f:

        writer = csv.writer(f, delimiter=";")

        writer.writerow([
            "sigle", "session", "section", "mode",
            "jour", "heure_debut", "heure_fin"
        ])

        for cours in cours_liste:

            # Plages des sessions connues
            for version in cours["versions"]:

                for section in version["sections"]:

                    for plage in section["plages"]:

                        writer.writerow([
                            cours["sigle"],
                            version["session"],
                            section["section"],
                            section["mode"],
                            plage[0],
                            plage[1],
                            plage[2]
                        ])

            # Sessions futures prédites (sigle + session seulement)
            sessions = [v["session"] for v in cours["versions"]]

            for s in deduire_sessions_futures(sessions):

                writer.writerow([
                    cours["sigle"], s, "", "", "", "", ""
                ])


# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------

def main():

    cours_liste = []

    for html_file in sorted(
        DOSSIER_HTML.glob("*.html")
    ):

        try:

            cours = analyser_fichier(
                html_file
            )

            cours_liste.append(cours)

            print(
                f"OK : {cours['sigle']}"
            )

        except Exception as e:

            print(
                f"ERREUR : {html_file.name}"
            )

            print(e)

    exporter(cours_liste)

    print()
    print("Terminé.")


if __name__ == "__main__":
    main()