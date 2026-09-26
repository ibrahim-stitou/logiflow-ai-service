# Politique de sécurité

## Signaler une vulnérabilité

**Ne publiez pas de ticket public** pour une faille de sécurité.

Utilisez le **signalement privé** de GitHub : onglet *Security*, puis *Report a vulnerability*
([lien direct](https://github.com/ibrahim-stitou/logiflow-ai-service/security/advisories/new)). Indiquez :

- le composant et la version (ou le commit) concernés ;
- les étapes de reproduction et l'impact estimé ;
- si possible, une proposition de correction.

Un accusé de réception est envoyé sous 72 h. La correction est priorisée selon la gravité :
critique sous 7 jours, élevée sous 30 jours.

## Versions prises en charge

Seule la branche `main`, déployée en production, reçoit des correctifs de sécurité.

## Mesures en place

Ce dépôt fait partie de la chaîne DevSecOps de LogiFlow :

- détection de secrets (Gitleaks et *push protection*) ;
- analyse statique (CodeQL) ;
- analyse des dépendances et des images (Trivy, porte bloquante sur les CVE critiques
  corrigeables) ;
- mises à jour automatiques (Dependabot).

Documentation : [outils de sécurité](https://github.com/ibrahim-stitou/logiflow-infra/blob/main/docs/10-outils-securite.md)
et [référence détaillée](https://github.com/ibrahim-stitou/logiflow-infra/blob/main/docs/11-securite-reference.md).
