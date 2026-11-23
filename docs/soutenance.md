# Présenter Carnet auto en six minutes

## Sujet à faire valider par l’enseignant

« Un acheteur de voiture d’occasion doit comparer des annonces qui décrivent différemment le même modèle. Notre application réunit les informations sourcées sur la motorisation, compare les prix de véhicules proches et conserve les meilleures annonces dans un carnet de visites. Trois agents LangChain se partagent la collecte, la recherche documentaire et la préparation de la visite. »

Montrer le diagramme dans **Architecture des trois agents**, juste au-dessus du formulaire. La validation du sujet et de l’architecture relève de l’enseignant. Le binôme peut présenter ce pitch et recueillir son accord ou ses ajustements.

## Déroulé à deux

| Temps | Qui | À montrer et expliquer |
|---|---|---|
| 0:00–0:45 | A | Présenter le besoin et l’exemple d’un acheteur qui dispose de 13 000 €. |
| 0:45–1:45 | B | Ouvrir le diagramme. Le navigateur envoie les critères au serveur Streamlit. Le coordinateur délègue l’inventaire, puis la documentation, puis enregistre la sélection. Les trois rôles partagent Ollama. |
| 1:45–3:00 | A | Choisir **Soutenance locale**. Montrer le carnet avant la recherche. Saisir Clio V, 13 000 €, 80 000 km, essence et manuelle. Laisser les préférences vides. Lancer puis suivre les appels réels dans la progression. Expliquer la provenance des données pendant le calcul. |
| 3:00–4:15 | B | Examiner Tours (12 400 €), Lille et Lyon. Ouvrir le détail de la note de Tours. Expliquer pourquoi les quatre véhicules au-dessus du budget contribuent aussi à la comparaison des prix. Montrer la source du manuel ou son extrait embarqué. |
| 4:15–5:15 | A | Dans le journal, relever l’identifiant donné par l’outil d’enregistrement. Ouvrir la sélection portant cet identifiant dans **Carnet de visites**, puis actualiser le navigateur. Le carnet relit les trois annonces depuis SQLite. |
| 5:15–6:00 | B | Présenter la limite de couverture des catalogues et proposer un flux partenaire pour améliorer la stabilité. Rappeler qu’une médiane exige au moins cinq autres véhicules comparables. |

Avant le passage, démarrer Ollama et Streamlit, sélectionner le modèle et laisser finir son diagnostic. Garder le Mac branché. Les sept annonces sont fictives et étiquetées comme telles. L’extrait du manuel Renault est un document enregistré sur le Mac. Le scénario local fonctionne sans Internet avec le modèle déjà téléchargé. Le mode **Catalogues en direct** permet en complément d’ouvrir une annonce actuelle lorsque le réseau est disponible.

## Questions que les deux membres doivent pouvoir expliquer

- **Où est le backend ?** Streamlit sert l’interface dans le navigateur et exécute Python sur le Mac. Son canal WebSocket transporte les événements du formulaire, la progression et les résultats. Les connecteurs, LangChain, le calcul des notes et SQLite s’exécutent côté serveur.
- **Qui décide quoi ?** Le workflow fixe l’ordre des délégations et les outils autorisés. Ollama émet les appels métier. Les agents sélectionnent ensuite les moteurs, les passages documentaires et les observations du rapport. Python vérifie les références, filtre les annonces et calcule les notes.
- **Quelle action peut-on contrôler ?** L’outil du coordinateur écrit les trois premières annonces, leurs notes et les critères dans une transaction SQLite. Le même identifiant apparaît dans la trace et dans le carnet. Deux recherches ont deux identifiants distincts.
- **Que prouve le scénario local ?** Les outils lisent des fichiers du projet, les trois agents utilisent Ollama et le carnet est réellement modifié. La disponibilité de renew et Spoticar se vérifie séparément en mode direct.
- **Que se passe-t-il en cas de panne ?** Une source Web indisponible est signalée dans le journal. Un échec d’Ollama interrompt le parcours agentique et apparaît dans l’interface. Le mode « Démonstration » reste disponible pour explorer le classement sans modèle.

## Correspondance avec le barème

| Critère | Élément observable |
|---|---|
| Application · 4 points | Soumission dans le navigateur, traitement côté serveur, restitution du rapport et relecture du carnet. |
| Architecture · 5 points | Diagramme dans l’application, deux spécialistes LangChain et un coordinateur qui utilise la délégation `task`. |
| Outils et actions · 6 points | Traces de `collecter`, `rechercher`, `lire` et `enregistrer_selection`. Fiches, document source et sélection persistante inspectables. |
| Soutenance · 5 points | Scénario reproductible, répartition de la parole, limite et amélioration. Le respect du temps et la maîtrise individuelle s’évaluent à l’oral. |

MCP et RAG sont des bonus facultatifs. L’expert utilise la recherche Web et la sélection d’extraits sourcés. Le projet ne revendique pas de serveur MCP ni d’index vectoriel.
