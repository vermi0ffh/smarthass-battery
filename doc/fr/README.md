# Smart Hass - Battery

Smart Hass - Battery estime l'énergie réellement stockée dans une batterie domestique. Le BMS d'une batterie
publie un état de charge, mais sur beaucoup de batteries il se trompe de quelques kWh au milieu de la plage : il est
en avance pendant la charge, en retard pendant la décharge, et tient des paliers (par exemple à 89 % alors que 2 kWh
entrent encore). L'intégration compte l'énergie qui entre et sort de la batterie depuis le dernier repère physique,
et publie une énergie stockée, une place restante et un état de charge corrigé.

Elle lit et estime seulement : elle ne pilote jamais l'onduleur ni la batterie.

## Comment elle estime

- **Repères** : la batterie est **pleine** quand une cellule atteint sa tension de pleine charge (3,50 V pour le LFP
  par défaut ; sans tensions de cellules, quand l'état de charge atteint 100 %), **vide** quand l'état de charge passe
  le seuil vide pendant une décharge. À un repère l'énergie stockée est connue : l'énergie entre les repères à
  pleine, 0 à vide.
- **Comptage** : entre les repères, l'énergie qui entre et sort (la puissance DC de la batterie, ou ses compteurs
  d'énergie) fait bouger l'estimation ; ce qui entre compte multiplié par le rendement (les pertes sont mises à
  l'entrée : l'estimation est ce qui ressortira).
- **Apprentissage** : d'un repère au suivant du même type, ce qui est sorti sur ce qui est entré est le rendement ;
  d'un type à l'autre, l'énergie entre eux. Les deux sont toujours mesurés (capteurs de diagnostic) ; ils remplacent
  les valeurs configurées une fois *Utiliser les valeurs apprises* activé (par défaut), dès 5 cycles.
  *Paramètres* > *Réparations* signale quand elles sont prêtes alors que l'option est désactivée (un clic l'active),
  et quand l'une s'écarte de plus de 10 % de la valeur configurée (une erreur de configuration, une batterie qui a
  perdu de la capacité, ou une source qui compte mal).
- **Départ** : avant le premier repère, l'estimation part de l'état de charge, et en repart si le comptage s'en
  écarte de plus de 3 kWh.

Sur 10 jours d'une vraie batterie (4 Pylontech US5000, 19,2 kWh), l'état de charge multiplié par la capacité se
trompait de 0,63 kWh en moyenne et 1,89 au pire ; le comptage depuis les repères de 0,43 et 1,09.

## Prérequis

- Home Assistant 2026.10 ou plus récent.
- L'**état de charge** de la batterie donné par son BMS (%).
- Sa **puissance DC** (W ou kW) et/ou ses **compteurs d'énergie** entrée et sortie (DC, cumulés ou journaliers ;
  Wh, kWh, MWh) : la puissance, ou les deux compteurs. Avec les deux, les compteurs comptent ce que la puissance
  manque quand elle est indisponible (et pendant un redémarrage de Home Assistant).
- Recommandé : la **tension de cellule la plus haute** de chaque pack (V ou mV) : le repère plein. Sans elle, c'est
  l'état de charge à 100 % — plus tard et moins exact sur les batteries dont le BMS saute à 100 %.

## Installation

Avec HACS : ajouter `https://github.com/vermi0ffh/smarthass-battery` comme dépôt personnalisé (catégorie
*Intégration*), installer **Smart Hass - Battery**, redémarrer Home Assistant, puis *Paramètres → Appareils et
services → Ajouter une intégration*.

## Configuration

| Option | Défaut | Description |
|--------|--------|-------------|
| Nom | Battery | Le nom de l'appareil |
| État de charge | — | L'état de charge du BMS (%) |
| Puissance batterie | aucune | Puissance DC (W ou kW), positive en charge |
| Puissance positive en décharge | désactivé | Pour un onduleur qui la donne dans l'autre sens |
| Énergie entrée, Énergie sortie | aucun | Compteurs cumulés ou journaliers de l'énergie DC entrée et sortie (les deux ou aucun) |
| Tensions des cellules | aucune | La tension de cellule la plus haute de chaque pack (la plus haute d'entre elles est utilisée) |
| Capacité nominale | — | La capacité de la batterie sur sa fiche technique (kWh) |
| Seuil vide | 9 % | L'état de charge considéré comme vide (là où votre automatisation bascule la maison sur le réseau) |
| Tension de cellule pleine | 3,50 V | Une cellule à cette tension est le repère plein |
| Rendement aller-retour | 96 % | Énergie DC sortie pour l'énergie entrée (96,4 % mesuré sur 8 cycles journaliers en LFP) |
| Énergie entre les repères | la capacité nominale au-dessus du seuil vide | Ce que la batterie rend de pleine à vide |
| Puissance maximale | 30 kW | Une hausse de compteur plus rapide est ignorée comme aberrante |
| Utiliser les valeurs apprises | activé | Compter le rendement et l'énergie appris à la place des deux ci-dessus |

Les paramètres de la batterie se changent ensuite (*Configurer* sur l'intégration), les entités lues en la
reconfigurant (*Reconfigurer* dans son menu) : l'estimation reste, des compteurs remplacés sont comptés depuis leur
première lecture.

## Entités

| Entité | Unité | Description |
|--------|-------|-------------|
| Énergie stockée | kWh | Ce que la batterie peut encore rendre au-dessus du seuil vide ; ses attributs donnent à un planificateur la batterie (capacité, énergie entre les repères et rendement utilisés, seuil vide), la place, l'incertitude, le dernier repère, les derniers plein et vide, et les entités sources |
| État de charge | % | L'énergie stockée sur l'échelle du BMS (le seuil vide à vide, 100 % à pleine), linéaire en énergie |
| Place restante | kWh | Ce qu'elle peut encore prendre avant pleine, en kWh rendus |
| Incertitude (diagnostic) | kWh | De combien l'estimation peut se tromper : celle de son départ (pleine 0,4 kWh, vide 0,8, l'état de charge 2, fixée à la main 0,5) plus 2 % de ce qui a circulé depuis |
| Rendement appris (diagnostic) | % | Mesuré sur les cycles ; attributs : le configuré, celui utilisé, les cycles comptés |
| Énergie entre les repères apprise (diagnostic) | kWh | Mesurée sur les cycles ; mêmes attributs |
| Dernier repère (diagnostic) | heure | Le dernier repère vu ; attributs : son type (pleine, vide) et l'écart du comptage à ce repère |

L'énergie stockée, l'état de charge, la place et l'incertitude deviennent indisponibles quand les flux n'ont pas pu
être lus pendant 15 minutes (la puissance, sauf si les deux compteurs comptent ; les compteurs, sans puissance).

## Services

- `smart_hass_battery.mark_full` (`config_entry_id`) : la batterie est pleine maintenant.
- `smart_hass_battery.mark_empty` (`config_entry_id`) : la batterie est à son seuil vide maintenant.
- `smart_hass_battery.set_energy` (`config_entry_id`, `energy_kwh`) : l'énergie qu'elle peut encore rendre au-dessus
  du seuil vide.

Un repère donné à la main n'apprend rien (l'apprentissage ne se fie qu'aux repères vus). Si l'état de charge s'en
écarte de plus de 3 kWh, la lecture suivante repart de l'état de charge.

## Mise à jour des données

Rien n'est interrogé. L'estimation suit **chaque changement d'état** des entités sources, et se rafraîchit chaque
minute entre deux (la puissance est comptée à sa dernière valeur). Elle est sauvegardée 30 s après un changement et
à l'arrêt de Home Assistant ; après un redémarrage, les compteurs d'énergie (s'il y en a) comptent la coupure, la
puissance n'est pas supposée tenue.

## Cas d'usage

- **Planifier la batterie** : un planificateur d'énergie (par exemple Smart Hass - Energy Optimizer) lit l'énergie
  stockée et la place au lieu de l'état de charge du BMS : la charge de nuit s'arrête à la bonne énergie, la soirée
  ne tombe pas à court plus tôt que prévu.
- **Des cibles de charge en énergie** : une automatisation qui charge jusqu'à une cible la compare à l'état de
  charge corrigé, qui ne tient pas 89 % pendant que 2 kWh entrent encore.
- **Suivre le vieillissement** : l'énergie entre les repères apprise baisse quand la batterie perd de la capacité.

## Exemples

Les identifiants ci-dessous sont ceux d'une batterie nommée *Battery*, avec Home Assistant en anglais ; les vôtres
suivent le nom donné et la langue de Home Assistant à sa création.

Arrêter une charge de nuit depuis le réseau une fois 12 kWh stockés (`switch.grid_charge` représente ce que
l'intégration de votre onduleur propose pour autoriser la charge réseau) :

```yaml
automation:
  - alias: Batterie - arrêt de la charge de nuit à 12 kWh
    triggers:
      - trigger: numeric_state
        entity_id: sensor.battery_stored_energy
        above: 12
    conditions:
      - condition: time
        after: "22:00:00"
        before: "06:00:00"
    actions:
      - action: switch.turn_off
        target:
          entity_id: switch.grid_charge
```

Une notification quand il reste moins de 2 kWh, avec la confiance qu'on peut y accorder :

```yaml
automation:
  - alias: Batterie - basse
    triggers:
      - trigger: numeric_state
        entity_id: sensor.battery_stored_energy
        below: 2
    actions:
      - action: notify.notify
        data:
          message: >-
            Il reste {{ states('sensor.battery_stored_energy') | float | round(1) }} kWh
            (± {{ state_attr('sensor.battery_stored_energy', 'uncertainty_kwh') | round(1) }} kWh).
```

Une charge complète au moins une fois par semaine, pour que le repère plein et l'apprentissage restent frais :

```yaml
automation:
  - alias: Batterie - charge complète hebdomadaire
    triggers:
      - trigger: time
        at: "22:00:00"
    conditions:
      - condition: template
        value_template: >-
          {{ state_attr('sensor.battery_stored_energy', 'last_full_at') is none
             or (now() - as_datetime(state_attr('sensor.battery_stored_energy', 'last_full_at'))).days >= 7 }}
    actions:
      - action: switch.turn_on
        target:
          entity_id: switch.grid_charge
```

Les attributs de l'énergie sont ce dont un planificateur a besoin : `full_energy_kwh` (l'énergie entre les repères
utilisée), `efficiency` (le rendement utilisé), `room_kwh`, `uncertainty_kwh`, `empty_soc_pct`, `last_full_at` et
`last_empty_at` (quand la batterie a été pleine et vide pour la dernière fois, gardés quand le comptage repart de l'état
de charge ou d'une énergie donnée), les entités sources.

## Limites connues

- **Comptage DC** : les pertes des onduleurs (côté AC) ne sont pas comptées ; le rendement est celui de la batterie.
- **Consommation au repos** : ce que la batterie alimente à vide (son BMS, l'onduleur au repos) est compté comme
  toute décharge ; il n'est pas appris à part.
- **Un seul seuil vide** : le repère vide est le passage de l'état de charge, aussi précis que le BMS près du vide
  (±0,8 kWh mesuré).
- **Il faut des repères** : une batterie qui n'atteint jamais pleine ni le seuil vide continue de compter depuis son
  dernier départ ; l'incertitude grandit avec ce qui a circulé. Chargez-la pleine de temps en temps.
- **Une batterie par entrée** : des packs sur des onduleurs séparés avec des mesures séparées ne font une batterie
  que si un état de charge et une puissance (ou une paire de compteurs) les couvrent tous.

## Dépannage

| Symptôme | À vérifier |
|----------|------------|
| L'énergie stockée est *indisponible* | La puissance (ou les compteurs) est indisponible depuis 15 minutes : le journal dit laquelle et pourquoi ; *Paramètres* > *Réparations* si l'entité n'existe plus |
| L'énergie bouge dans le mauvais sens | Le signe de la puissance : *Puissance positive en décharge* dans la reconfiguration |
| Le repère plein n'est jamais vu | Les tensions des cellules et la tension de cellule pleine : une cellule doit l'atteindre en haut de charge |
| Elle revient à l'état de charge | Le comptage s'en est écarté de plus de 3 kWh : un rendement, une capacité ou un signe de puissance faux, ou des flux manqués |
| Une valeur apprise est loin de la valeur configurée (*Réparations*) | La capacité nominale et le seuil vide, puis les sources (compteurs DC, signe de la puissance) ; si la valeur apprise est juste, donnez-la dans les options |

Pour signaler un problème, joignez les **diagnostics** (*Paramètres* > *Appareils et services* > *Smart Hass -
Battery* > la batterie > ⋮ > *Télécharger les diagnostics*) : les options, l'estimation, l'état du modèle et ce que
montre chaque entité source.

## Désinstallation

1. *Paramètres* > *Appareils et services* > *Smart Hass - Battery* > ⋮ sur chaque batterie > *Supprimer* : ses
   entités et son estimation sauvegardée sont supprimées.
2. Dans HACS, supprimer *Smart Hass - Battery*, puis redémarrer Home Assistant.

Mettez d'abord à jour ce qui lit ses entités (automatisations, tableaux de bord, planificateur d'énergie) : elles
deviennent indisponibles.
