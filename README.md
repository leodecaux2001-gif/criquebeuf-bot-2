# Bot Discord - AS CRIQUEBEUF FB

Ce bot :
- surveille la page FFF des **Seniors 1 / AS CRIQUEBEUF FB** ;
- annonce automatiquement le prochain match dans `#⚽match` ;
- ping `@everyone` ;
- ajoute les réactions `✅` et `❌` ;
- envoie un rappel **24h avant** et **2h avant** ;
- tente d'envoyer le **résultat 5 heures après le coup d'envoi**, avec les buteurs et les minutes **si la FFF les expose sur la fiche du match**.

## Important

Le résultat automatique, les buteurs et les minutes dépendent des données réellement publiées par la FFF sur la fiche du match. Sur certaines feuilles amateur, ces événements ne sont pas renseignés. Dans ce cas, le bot enverra quand même le score si disponible, mais sans la liste des buteurs.

## Installation

1. Installe Python 3.11+
2. Ouvre un terminal dans ce dossier
3. Lance :

```bash
pip install -r requirements.txt
```

4. Mets le token de ton bot dans `config.json`
5. Active **MESSAGE CONTENT INTENT** dans le portail développeur Discord
6. Lance le bot :

```bash
python bot.py
```

## Créer le bot Discord

1. Ouvre le portail développeur Discord
2. Crée une nouvelle application
3. Onglet **Bot** > **Add Bot**
4. Active :
   - `MESSAGE CONTENT INTENT`
5. Copie le token dans `config.json`
6. Invite le bot avec les permissions suivantes :
   - View Channels
   - Send Messages
   - Embed Links
   - Add Reactions
   - Read Message History
   - Mention Everyone

## Commandes

- `!prochainmatch` → affiche le prochain match détecté
- `!forcercheck` → force une vérification immédiate (admin uniquement)

## Hébergement 24/7

Si ton PC est éteint, le bot s'arrête. Pour qu'il reste allumé, héberge-le sur Railway, Render, un VPS, ou un autre hébergement permanent.
