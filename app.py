from flask import Flask, request, render_template, jsonify
import requests
from google import genai
import urllib.parse
import json
import concurrent.futures
import re 
import time 

app = Flask(__name__)

# --- SYSTÈME DE CACHE AVEC EXPIRATION (TTL) ---
DUREE_CACHE_SECONDES = 86400 # 24 heures

cache_gouv = {}
cache_serper = {}
cache_hunter = {}

def get_cache(dictionnaire_cache, cle):
    if cle in dictionnaire_cache:
        donnees = dictionnaire_cache[cle]
        if time.time() - donnees['timestamp'] < DUREE_CACHE_SECONDES:
            return donnees['valeur']
        else:
            del dictionnaire_cache[cle]
    return None

def set_cache(dictionnaire_cache, cle, valeur):
    dictionnaire_cache[cle] = {
        'valeur': valeur,
        'timestamp': time.time()
    }

def chercher_entreprises_gouv(secteur, ville, page=1):
    recherche_exacte = f"{secteur} {ville}".strip() if ville else secteur
    cache_key = f"{recherche_exacte.lower()}_page_{page}"
    
    resultat_en_cache = get_cache(cache_gouv, cache_key)
    if resultat_en_cache:
        return resultat_en_cache
        
    recherche_encode = urllib.parse.quote(recherche_exacte)
    url = f"https://recherche-entreprises.api.gouv.fr/search?q={recherche_encode}&per_page=25&page={page}"
    
    try:
        reponse = requests.get(url)
        
        if reponse.status_code == 429:
            return {"erreur": "⚠️ L'API du Gouvernement vous a temporairement bloqué pour 'Trop de requêtes'."}
            
        if reponse.status_code == 200:
            entreprises_brutes = reponse.json().get('results', [])
            resultat_final = {"resultats": entreprises_brutes}
            set_cache(cache_gouv, cache_key, resultat_final)
            return resultat_final
            
        return {"erreur": f"⚠️ Erreur de l'API Gouvernement (Code {reponse.status_code})."}
    except Exception as e:
        return {"erreur": f"⚠️ Impossible de contacter l'API de l'État : {str(e)}"}

def nettoyer_description(texte):
    if not texte or texte == 'Aucune description disponible sur le web.':
        return texte
    if "Activité principale" in texte:
        match = re.search(r'Activité principale de la société \(NAF/APE\)\.? :? (.*?)(?:\.|$)', texte, re.IGNORECASE)
        if match: return f"Activité identifiée : {match.group(1).strip().capitalize()}."
    if "Son domaine d'activité est" in texte:
        match = re.search(r"Son domaine d'activité est : (.*?)(?:\.|$)", texte, re.IGNORECASE)
        if match: return f"Activité identifiée : {match.group(1).strip().capitalize()}."
            
    texte_propre = re.sub(r'Adresse.*?(\d{5}|;)', '', texte, flags=re.IGNORECASE)
    texte_propre = re.sub(r'SIRET.*?(\d{14}|;)', '', texte_propre, flags=re.IGNORECASE)
    texte_propre = re.sub(r'Clef NIC.*?\d{5}', '', texte_propre, flags=re.IGNORECASE)
    texte_propre = re.sub(r'Siège social de .*?;', '', texte_propre, flags=re.IGNORECASE)
    texte_propre = re.sub(r'\s+', ' ', texte_propre)
    texte_propre = re.sub(r'[;:]\s*[;:]', ';', texte_propre)
    texte_propre = texte_propre.replace(' ; ', ' ').strip(" ;.")
    
    if len(texte_propre) < 15:
        return "Pas de descriptif d'activité clair disponible en ligne."
    return texte_propre.capitalize() + "."

def trouver_site_serper(nom_entreprise, ville, api_key):
    if not api_key: return {"domaine": "", "description": "Recherche Google désactivée."}
        
    cache_key = f"{nom_entreprise}_{ville}_{api_key}".lower()
    resultat_en_cache = get_cache(cache_serper, cache_key)
    if resultat_en_cache: return resultat_en_cache
        
    url = "https://google.serper.dev/search"
    requete_recherche = f"{nom_entreprise} {ville} site officiel" if ville else f"{nom_entreprise} site officiel"
    payload = json.dumps({"q": requete_recherche, "num": 1, "gl": "fr", "hl": "fr"})
    headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}
    
    try:
        reponse = requests.post(url, headers=headers, data=payload, timeout=5)
        if reponse.status_code in [401, 403, 429]:
            return {"domaine": "", "description": "⚠️ Limite d'API Serper.dev atteinte ou clé invalide."}
        if reponse.status_code == 200:
            donnees = reponse.json()
            if 'organic' in donnees and len(donnees['organic']) > 0:
                resultat = donnees['organic'][0]
                lien_brut = resultat.get('link', '')
                snippet = resultat.get('snippet', 'Aucune description disponible sur le web.')
                domaine = urllib.parse.urlparse(lien_brut).netloc.replace('www.', '')
                description_propre = nettoyer_description(snippet)
                resultat_final = {"domaine": domaine, "description": description_propre}
                set_cache(cache_serper, cache_key, resultat_final)
                return resultat_final
    except Exception:
        pass
    return {"domaine": "", "description": "Aucun site web trouvé."}

def obtenir_emails_hunter(domaine, api_key):
    if not api_key or not domaine: return {"emails": [], "erreur": "Clé API Hunter manquante ou site web invalide."}
        
    cache_key = f"{domaine}_{api_key}".lower()
    resultat_en_cache = get_cache(cache_hunter, cache_key)
    if resultat_en_cache: return resultat_en_cache
        
    url = f"https://api.hunter.io/v2/domain-search?domain={domaine}&api_key={api_key}"
    try:
        reponse = requests.get(url, timeout=5)
        if reponse.status_code in [401, 403, 429]:
            return {"emails": [], "erreur": "⚠️ Limite d'API Hunter.io mensuelle atteinte ou clé invalide."}
        if reponse.status_code == 200:
            donnees = reponse.json()
            resultat_final = {"emails": donnees['data'].get('emails', []), "erreur": None}
            set_cache(cache_hunter, cache_key, resultat_final)
            return resultat_final
    except Exception:
        pass
    return {"emails": [], "erreur": "Erreur inattendue de connexion à Hunter.io."}

def traiter_une_entreprise(ent, ville_recherchee, domaine_recherche, serper_key):
    nom = ent.get('nom_complet', 'Nom inconnu')
    
    # Sécurisation des données de localisation pour éviter les erreurs "NoneType"
    siege = ent.get('siege') or {}
    ville_api = siege.get('libelle_commune') or 'France'
    ville_affichage = ville_recherchee.title() if ville_recherchee else ville_api.title()
    code_postal = siege.get('code_postal') or ''
    departement = code_postal[:2] if code_postal else 'N/A'
    etat_administratif = ent.get('etat_administratif', 'A')
    
    info_site = trouver_site_serper(nom, ville_affichage, serper_key)
    site_web = info_site['domaine']
    description = "⚠️ Cette entreprise est déclarée fermée ou radiée." if etat_administratif == 'C' else info_site['description']
    
    return {
        "nom": nom,
        "ville": ville_affichage,
        "departement": departement,
        "description": description,
        "domaine": domaine_recherche,
        "site_web": site_web
    }

@app.route('/', methods=['GET', 'POST'])
def accueil():
    secteurs_populaires = ["Informatique", "Agriculture", "Bâtiment et Travaux Publics", "Commerce de détail", "Restauration", "Santé et Action sociale", "Transport et Logistique", "Services aux entreprises", "Immobilier", "Marketing et Communication", "Hôtellerie", "Banque et Assurance"]

    if request.method == 'POST':
        ville_recherchee = request.form.get('ville', '').strip()
        domaine_recherche = request.form.get('domaine', '').strip()
        serper_key = request.form.get('serper_key', '')
        
        reponse_gouv = chercher_entreprises_gouv(domaine_recherche, ville_recherchee, page=1)
        
        if "erreur" in reponse_gouv:
            return render_template('resultats.html', erreur_globale=reponse_gouv["erreur"], entreprises=[])
            
        entreprises_brutes = reponse_gouv.get("resultats", [])
        resultats_entreprises = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
            futures = [executor.submit(traiter_une_entreprise, ent, ville_recherchee, domaine_recherche, serper_key) for ent in entreprises_brutes]
            for future in concurrent.futures.as_completed(futures):
                resultats_entreprises.append(future.result())
                
        return render_template('resultats.html', entreprises=resultats_entreprises, ville=ville_recherchee, domaine=domaine_recherche)
        
    return render_template('index.html', domaines=secteurs_populaires)

@app.route('/charger-plus', methods=['POST'])
def charger_plus():
    donnees = request.get_json()
    ville = donnees.get('ville', '').strip()
    domaine = donnees.get('domaine', '').strip()
    serper_key = donnees.get('serper_key', '')
    page = donnees.get('page', 2)

    reponse_gouv = chercher_entreprises_gouv(domaine, ville, page)

    if "erreur" in reponse_gouv:
        return f"<div class='col-span-1 bg-red-50 p-4 text-red-700 rounded-lg text-center font-bold'>{reponse_gouv['erreur']}</div>", 400

    entreprises_brutes = reponse_gouv.get("resultats", [])
    if not entreprises_brutes:
        return "" 

    resultats_entreprises = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
        futures = [executor.submit(traiter_une_entreprise, ent, ville, domaine, serper_key) for ent in entreprises_brutes]
        for future in concurrent.futures.as_completed(futures):
            resultats_entreprises.append(future.result())

    return render_template('resultats.html', entreprises=resultats_entreprises, uniquement_cartes=True, page=page)

@app.route('/chercher-contacts', methods=['POST'])
def chercher_contacts():
    donnees = request.get_json()
    domaine = donnees.get('domaine', '')
    hunter_key = donnees.get('hunter_key', '')
    
    resultat = obtenir_emails_hunter(domaine, hunter_key)
    return jsonify(resultat)

@app.route('/generer-email', methods=['POST'])
def generer_email():
    donnees = request.get_json()
    gemini_key = donnees.get('gemini_key', '')
    if not gemini_key: return jsonify({'succes': False, 'erreur': 'Clé API Google Gemini non configurée.'}), 400

    prompt = f"""
    Rédige un email de candidature spontanée professionnel, concis et percutant.
    Paramètres :
    - Entreprise cible : {donnees.get('entreprise', '')}
    - Secteur d'activité : {donnees.get('domaine', '')}
    - Destinataire : {donnees.get('contact', 'Responsable')} ({donnees.get('poste', 'Recrutement')})
    - Profil : Développeur Web / Logiciel
    Contraintes : Longueur max 150 mots. Ton professionnel et direct.
    """
    try:
        gemini_client = genai.Client(api_key=gemini_key)
        reponse = gemini_client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        return jsonify({'succes': True, 'email_texte': reponse.text})
    except Exception as e:
        erreur_msg = str(e)
        if "429" in erreur_msg or "quota" in erreur_msg.lower(): erreur_msg = "⚠️ Limite d'API Google Gemini dépassée. Veuillez réessayer plus tard."
        return jsonify({'succes': False, 'erreur': erreur_msg}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)