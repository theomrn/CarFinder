# Architecture de Carnet auto

## 1. Qui communique avec qui ?

```mermaid
flowchart LR
    browser["Navigateur · formulaire, rapport et carnet"]
    subgraph mac["Sur le Mac"]
        ui["Serveur Python Streamlit"]
        parser["Agent de compréhension · catalogue des modèles"]
        coordinator["Agent coordinateur · Deep Agents"]
        listings["Agent annonces · LangChain"]
        expert["Agent expert · LangChain"]
        model["Ollama · modèle local partagé"]
        files["Fichiers JSON · inventaire fictif et notice Renault"]
        db[("SQLite · carnet de visites")]
    end
    catalogues["Catalogues Web · renew, AutoScout24 et Spoticar"]
    web["Recherche DDGS et pages documentaires"]
    browser <-->|"WebSocket"| ui
    ui <-->|"Critères, progression et rapport"| coordinator
    ui -->|"Phrase"| parser
    parser -->|"Filtres validés"| coordinator
    parser --> model
    coordinator -->|"Délègue la collecte"| listings
    coordinator -->|"Délègue la recherche"| expert
    coordinator --> model
    listings --> model
    expert --> model
    listings -->|"Direct"| catalogues
    expert -->|"Direct"| web
    listings -->|"Soutenance locale"| files
    expert -->|"Soutenance locale"| files
    coordinator -->|"Écrit la sélection"| db
    ui -->|"Relit le carnet"| db
```

L’interface et le backend appartiennent à la même application Streamlit. Le navigateur transmet les événements du formulaire et reçoit les mises à jour via WebSocket. Python exécute les outils, calcule les notes et interroge SQLite. Ollama fournit l’inférence aux agents.

## 2. Que se passe-t-il pendant une recherche ?

```mermaid
sequenceDiagram
    actor User as Utilisateur
    participant UI as Streamlit
    participant Coord as Coordinateur
    participant Ads as Agent annonces
    participant Expert as Agent expert
    participant DB as SQLite

    User->>UI: Soumet Clio V, 13 000 €, 80 000 km
    UI->>Coord: Lance la recherche
    Coord->>Ads: 1. Délègue avec task
    Ads->>Ads: Appelle collecter et lit les fiches
    Ads-->>Coord: Inventaire disponible dans le contexte partagé
    Coord->>Expert: 2. Délègue avec task
    Expert->>Expert: Appelle rechercher puis lire
    Expert-->>Coord: Sources et extraits dans le contexte partagé
    Coord->>Coord: 3. Appelle enregistrer_selection et calcule les notes
    Coord->>DB: Écrit les critères et jusqu’à trois annonces
    DB-->>Coord: Confirme l’écriture
    Coord->>Coord: 4. Prépare la synthèse et les commentaires avec Ollama
    Coord-->>UI: Renvoie le rapport et le journal
    UI-->>User: Affiche le classement et le carnet
    User->>UI: Actualise la page
    UI->>DB: Relit les sélections sauvegardées
    UI-->>User: Affiche le carnet de visites
```

Le code fixe l’ordre des délégations. Ollama émet les appels aux outils autorisés pour chaque étape. Le calcul Python applique les filtres, cherche des comparables dans l’inventaire et classe jusqu’à dix annonces. Le coordinateur sauvegarde jusqu’à trois annonces avant de composer le rapport.

## 3. Quel mode utilise quelles données ?

| Mode | Sources | Agents et carnet |
|---|---|---|
| **Catalogues en direct** | renew, AutoScout24, Spoticar, recherche Web et pages ouvertes | Trois agents avec Ollama. Sélection écrite dans SQLite. |
| **Soutenance locale** | Sept annonces fictives et un extrait du manuel Renault dans le projet | Trois agents avec Ollama. Sélection écrite dans SQLite. Fonctionne sans Internet. |
| **Démonstration** | Les sept annonces fictives | Classement Python seul. La recherche ne crée aucune sélection. |
