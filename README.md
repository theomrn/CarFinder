# Carnet auto

Comparateur automobile local en français. Trois agents exploitent des fiches d’occasion et des documents publics. Streamlit affiche les observations, les sources et le détail du classement. Le projet a été testé sur Mac Apple Silicon avec Python 3.13 et Ollama.

## Lancer le site

Dans le dossier du projet, ouvrir l’application Ollama puis exécuter :

```sh
.venv/bin/streamlit run app.py
```

Ouvrir [Carnet auto en local](http://127.0.0.1:8501). Pour réinstaller depuis les sources :

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
ollama list
.venv/bin/streamlit run app.py
```

Le modèle initial est `llama3.1:latest`. Si nécessaire, le télécharger avec `ollama pull llama3.1`. La barre latérale liste les modèles présents dans Ollama. Le diagnostic demande au modèle d’appeler un outil puis de restituer le code aléatoire renvoyé. Le résultat positif est conservé quinze minutes. L’interface et Ollama utilisent la boucle locale. Internet sert à consulter les sites automobiles et à découvrir les documents via DDGS. Aucune clé API à renseigner.

## Exemple pour une soutenance

Le scénario principal utilise **Soutenance locale** avec Ollama. Saisir Clio V, 13 000 €, 80 000 km, essence et manuelle. Les agents lisent sept fiches fictives et une notice constructeur embarquée, puis le coordinateur enregistre sa sélection dans SQLite. Retrouver Tours, Lille et Lyon dans le **Carnet de visites**, y compris après actualisation. Le mode **Démonstration** conserve le calcul hors IA. Le mode **Catalogues en direct** consulte les sites publics.

Le diagramme se trouve dans **Architecture des trois agents** dans le site. Le guide couvre la validation par l’enseignant, la présentation en six minutes, la répartition en binôme et les questions techniques. [Guide de soutenance](docs/soutenance.md)

## Méthode multiagent

Le point d’entrée est `comparateur/agents.py`. L’exercice 08 de Worldline fournit le modèle d’agent spécialisé avec `create_agent` et les fonctions Python décorées par `@tool`. L’exercice 09 fournit l’orchestration hiérarchique avec `CompiledSubAgent` et `create_deep_agent`. [Cours et exercices Worldline](https://worldline.github.io/learning-ai/6.agentic/)

- Le **coordinateur** utilise l’outil de délégation `task` pour confier d’abord l’inventaire au spécialiste des annonces, puis les recherches documentaires à l’expert. Un middleware impose cette séquence. Pour chaque action métier, Ollama invoque l’outil autorisé avec le contexte du formulaire. Le coordinateur utilise aussi `enregistrer_selection` pour conserver les trois premières annonces, leurs notes et les critères dans `var/carnet.sqlite3`.
- L’**agent annonces** utilise `collecter` et extrait les motorisations de l’inventaire vérifié. Chaque connecteur lit au maximum 24 fiches par recherche. Les fiches expirées ou illisibles sont écartées. Les prix proviennent des champs de prix du véhicule.
- L’**expert** utilise `rechercher` et `lire`, puis sélectionne des passages de pages effectivement ouvertes. Pour la Clio V, deux références connues complètent la recherche Web. Les rappels et problèmes nécessitent une indication de période et de moteur dans le passage. Une documentation lacunaire laisse une rubrique sans conclusion.
- Le **rédacteur** compose la synthèse et les commentaires à partir de phrases liées aux observations vérifiées et sélectionne une question pour la visite. Cette rédaction contrainte évite que le modèle ajoute un historique d’entretien ou une affirmation de fiabilité à une annonce.

## Calcul du classement

Les critères obligatoires connus éliminent les annonces incompatibles. Une donnée obligatoire inconnue ou un prix comptant manquant place la fiche dans « À vérifier ». Le classement utilise les URL et les identifiants véhicule disponibles pour retirer les doublons. Une même voiture publiée sous deux URL sans identifiant commun peut subsister.

Pour chaque véhicule, la médiane porte sur les **autres** annonces vérifiées de même modèle, génération identifiable, libellé moteur et boîte, dans une fenêtre de deux ans et 25 000 km autour du véhicule. Au moins cinq prix sont nécessaires. L’échantillon est construit avant le filtre de budget. Les libellés techniques divergents peuvent réduire le nombre de comparables.

La note accorde 40 % au prix relatif, 25 % au kilométrage, 15 % aux équipements reconnus, 15 % à l’entretien documenté et 5 % à la garantie. Si des préférences sont saisies, elles reçoivent 10 des 15 points de pondération des équipements. Chaque famille d’équipements compte une fois.

Pour noter le prix avec moins de cinq comparables stricts, le classement utilise les autres annonces du même modèle, de même énergie et boîte, à deux années et 40 000 km près. Ces versions peuvent avoir des finitions différentes. Le détail affiche le prix de référence et la taille de l’échantillon. Sans comparable, seul le sous-score de prix est neutre (5/10). Le kilométrage tient compte du compteur et, si possible, des compteurs de véhicules du même âge. Un accident déclaré retire 2,5 points à la note finale. Un historique inconnu ne déclenche aucun malus accident.

## Vérifier le projet

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/pip check
```

Les tests hors connexion couvrent le classement, le filtrage, les générations, les doublons, les annonces retirées, les mensualités, les petits échantillons et le parcours Streamlit. Les dépendances de l’environnement testé sont figées dans `requirements.txt`.

Lors de la validation en direct le 23 novembre 2026, renew a fourni 23 fiches individuelles pour « Clio V ». Une annonce à 12 651 € et 49 115 km respectait les critères de l’exemple. Sa fiche a été rouverte pour contrôler les valeurs. Spoticar a répondu HTTP 403. Son extracteur de données structurées a été testé sur un exemple contrôlé ; la lecture de son catalogue réel reste à confirmer lorsque l’accès sera disponible. Les deux sources sont interrogées à chaque recherche en direct.
