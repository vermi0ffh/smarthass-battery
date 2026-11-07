# Smart Hass - Battery

Smart Hass - Battery estime l'énergie réellement stockée dans une batterie domestique. Le BMS d'une batterie
publie un état de charge, mais sur beaucoup de batteries il se trompe de quelques kWh au milieu de la plage : il est
en avance pendant la charge, en retard pendant la décharge, et tient des paliers (par exemple à 89 % alors que 2 kWh
entrent encore). L'intégration compte l'énergie qui entre et sort de la batterie (sa puissance DC ou ses compteurs
d'énergie) depuis le dernier repère physique :

- **pleine** : une cellule atteint sa tension de pleine charge (3,50 V pour le LFP par défaut) ;
- **vide** : l'état de charge passe le seuil vide pendant une décharge.

À chaque cycle entre deux repères, elle apprend le rendement aller-retour de la batterie et l'énergie entre vide et
pleine.

Elle lit et estime seulement : elle ne pilote jamais l'onduleur ni la batterie.

**État** : en développement — le modèle est en cours d'écriture et de validation ; les entités Home Assistant et la
configuration viennent ensuite.
