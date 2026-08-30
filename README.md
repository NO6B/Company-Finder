Application web en Python (Flask) pour automatiser la recherche d'entreprises et la prospection B2B sur le marché français. 

## Comment ça marche ?
* **Recherche d'entreprises :** L'outil utilise l'API de l'État (SIRENE) pour trouver des entreprises par secteur et ville.
* **Enrichissement & Contacts :** Il trouve les sites officiels via Google (Serper.dev) et extrait les e-mails professionnels à la demande (Hunter.io).
* **Génération d'e-mails :** L'intelligence artificielle (Google Gemini) rédige automatiquement un e-mail de prospection personnalisé selon l'entreprise et le poste du contact.

## Clés API requises (BYOK)
Vous devez générer vos propres clés API gratuites et les insérer directement dans l'interface web (via la roue crantée en haut à droite) :
1. **Hunter.io API Key** : Pour extraire les adresses e-mails.
2. **Serper.dev API Key** : Pour trouver les sites web officiels.
3. **Google Gemini API Key** : Pour la rédaction IA des messages.
*(Les clés sont stockées de façon sécurisée, uniquement dans la mémoire locale de votre navigateur).*

## Installation et lancement

Ouvrez votre terminal dans le dossier du projet et exécutez ces commandes étape par étape :

**1. Créer l'environnement virtuel**
```bash
python3 -m venv venv

```

**2. Activer l'environnement virtuel**

* Sur Mac / Linux :

```bash
source venv/bin/activate

```

* Sur Windows :

```cmd
venv\Scripts\activate

```

**3. Installer les dépendances**

```bash
pip install -r requirements.txt

```

**4. Lancer l'application**

```bash
python3 app.py

```

**5. Utiliser l'outil**
Ouvrez votre navigateur web et allez à l'adresse : `http://127.0.0.1:5000`

```

```
