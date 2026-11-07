# Contribuer

*[English version](../en/contributing.md)*

Comment proposer une modification, pour un humain ou un agent de code. Les règles elles-mêmes sont dans
[AGENTS.md](../../AGENTS.md#rules) ; cette page décrit la démarche. Les contributions sont faites sous la licence du
projet, Apache 2.0 ([LICENSE](../../LICENSE)).

## Démarche

1. **Comprendre avant de modifier** : lire `AGENTS.md` et la page de `doc/agents/` du domaine touché. Pour un
   comportement observé chez soi, partir des données (historique Home Assistant du relais, de la puissance, des
   compteurs et des entités de l'intégration) et énoncer le problème observé avec ses chiffres.
2. **Créer une branche** depuis `main` (`git switch -c <sujet>`), un sujet par branche.
3. **Écrire d'abord le test** quand on corrige un bug (il doit échouer sans la correction), puis la modification.
4. **Lancer** `make test-model` en travaillant, puis `make lint`, `make typecheck` et `make test` avant de committer.
5. **Mettre à jour la documentation** dans le même commit : `doc/agents/` pour la description technique, `doc/en/`,
   `doc/fr/` et les traductions pour ce que lisent les utilisateurs, les deux langues ensemble.
6. **Relire** avec `make review` (revue par IA des fichiers Python modifiés, commités ou non, voir
   [doc/agents/review.md](../agents/review.md)) : corriger les remarques bloquantes, peser les autres.
7. **Committer** (voir ci-dessous) et ouvrir une pull request (voir ci-dessous). La CI lance le lint, le typecheck,
   tous les tests, hassfest (le validateur de Home Assistant) et la validation HACS.

## Messages de commit

En anglais :

```
Short summary, no final period

Why: the observed problem, with the measures (date, values, entity).
What: what changes, the options and entities involved.
Measured effect: the estimate before → after on a recorded history, when applicable.
```

- Pas de préfixe (ni initiales, ni étiquette) : l'auteur est celui du commit.
- Lignes du corps coupées vers 100 colonnes.
- Pas d'attribution d'outil : les agents de code n'ajoutent aux commits et aux pull requests aucune mention de leur
  outil (ni `Co-Authored-By:` pour l'agent, ni « Generated with … », ni lien de session). Une personne qui a
  co-écrit le changement est créditée par `Co-authored-by:`.
- **Un sujet par commit.** Une refactorisation et un changement de comportement font deux commits.
- **Un commit de refactorisation ne touche pas aux tests** : les tests inchangés qui passent prouvent que le
  comportement est conservé.

## Pull requests

Titre en anglais, `[type] Short summary, no final period`, où `type` indique ce que contient la pull request :

| Type | Contenu |
|------|---------|
| `feature` | Un nouveau comportement ou une nouvelle possibilité (entité, attribut, option, valeur apprise…) |
| `bugfix` | La correction d'un comportement faux, avec le test qui échoue sans elle |
| `hotfix` | La correction urgente d'un problème vu en production, à fusionner et déployer tout de suite |
| `maintenance` | Aucun changement de comportement pour l'utilisateur : refactorisation, tests, documentation, CI, outillage, dépendances |
| `perf` | Un calcul plus rapide ou plus léger au même résultat, avec la mesure avant → après |
| `release` | Une version de l'intégration : `version`, `CHANGELOG.md` et le tag `vX.Y.Z` (voir plus bas) |
| `revert` | L'annulation d'une pull request fusionnée, avec la raison de son retrait |

Une pull request qui mélange plusieurs types est découpée ; ses commits gardent la forme de message ci-dessus.

Description :

```markdown
## Problem
Ce qui a été observé (données, dates, chiffres) ou ce qui manque.

## Change
Ce qui change et pourquoi cette approche.

## Compatibility
Options nouvelles ou modifiées et leur défaut ; entités ajoutées ou modifiées ; état enregistré dont le format
change. Indiquer qu'une installation configurée avant cette PR fonctionne sans changement après (ou, pour un
changement voulu, ce que l'utilisateur doit faire).

## Validation
- `make lint`, `make typecheck`, `make test` : OK
- Nouveaux tests : …
- Estimation : rejouée sur … (historique, dates) : niveau et énergie jusqu'au plein avant → après

## Changed tests
Pour chaque test existant dont l'attendu a changé ou qui a été supprimé : voir ci-dessous. « Aucun » sinon.
```

## Quand un test existant change

Un test qui casse est d'abord supposé avoir trouvé une régression. Le modifier n'est permis que si l'ancien attendu
était faux ou si le changement de comportement est voulu. Pour chaque test concerné, la PR (et le corps du commit)
indique :

- **Test** : `chemin::nom_du_test`.
- **Avant → après** : la valeur ou le comportement attendu, ancien et nouveau.
- **Pourquoi** : pourquoi l'ancien attendu ne tient plus, avec des chiffres pour un changement du modèle.
- **Ce qui garantit encore le comportement** : l'assertion conservée ou le nouveau test qui le couvre.

Interdit sans cette justification : élargir une tolérance, affaiblir ou supprimer une assertion, ajouter `skip` /
`xfail`, supprimer un test.

## Changements de l'estimation

L'énergie stockée, la place restante et l'état de charge corrigé pilotent des batteries à travers les automatisations
et les planificateurs d'énergie des utilisateurs (règle 25 d'`AGENTS.md`) :

1. Un changement du modèle ou de sa calibration est rejoué sur au moins un historique enregistré couvrant un cycle
   complet (une charge complète et une décharge jusqu'au seuil vide), anonymisé dans `tests/model/data/`.
2. La PR compare l'estimation avant → après sur cet historique, avec des chiffres.
3. Une nouvelle calibration arrive derrière une option tant qu'elle n'est pas validée sur de vraies installations.

## Rétrocompatibilité

Rien de ce qui fonctionnait avant un changement ne doit casser après :

- **Entrées de configuration** : un schéma modifié incrémente la version de l'entrée et migre les anciennes ; une
  nouvelle option a un défaut qui garde l'ancien comportement.
- **État enregistré** : un format modifié incrémente sa version et le précédent reste lisible ; un redémarrage ne perd
  jamais l'estimation ni la calibration.
- **Entités** : `unique_id`, sens, unité, `device_class` et `state_class` restent ; un changement est annoncé dans le
  changelog comme cassant, avec ce qu'il faut faire.

## Publier une version

Les versions suivent le versionnage sémantique (`0.x` tant que les options et les entités ne sont pas stables). Pour
publier `X.Y.Z` : incrémenter `version` dans `custom_components/smart_hass_battery/manifest.json` et
`pyproject.toml`, décrire la version dans `CHANGELOG.md`, puis poser le tag `vX.Y.Z` et publier une release GitHub
(HACS propose les releases).

## Liste de relecture

- [ ] Règles d'`AGENTS.md` respectées (modèle pur, Home Assistant dans le tracker, lecture seule, configuration et non
      code, unités, temps)
- [ ] Code, commentaires, logs et messages de commit en anglais ; traductions dans `en.json` et `fr.json`
- [ ] Tests ajoutés dans la bonne famille ; une correction de bug a un test qui échoue sans elle
- [ ] Tests modifiés justifiés ; les commits de refactorisation ne touchent pas aux tests
- [ ] Entrées de configuration, état enregistré et entités d'avant fonctionnent toujours
- [ ] Changements de l'estimation rejoués sur un historique enregistré
- [ ] Documentation à jour (`AGENTS.md`, `doc/agents/`, `doc/en/` et `doc/fr/`, `CHANGELOG.md`) ; une règle du quality
      scale désormais remplie est marquée `done` dans `quality_scale.yaml`
- [ ] Aucun secret, token ni donnée personnelle
