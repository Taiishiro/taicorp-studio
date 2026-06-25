---
name: caveman
description: Mode de communication ultra-compressé (~75% moins de tokens de sortie) pour rapports, verdicts et résumés. Préserve intacts le code, les commandes et les erreurs. Utilisé par les Reviewer / Test Engineer / Security Reviewer pour leurs verdicts, par le Context Manager pour ses résumés de fichiers, et par tout agent qui rapporte sans coder.
---

# Skill : caveman — compression de communication (–75% tokens)

> Référence : [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) — "why use many token when few do trick".

## Ce que caveman fait (et ne fait pas)

| Caveman touche | Caveman ne touche jamais |
|---------------|--------------------------|
| Prose, explications, justifications | Code source |
| Verdicts, rapports, résumés | Commandes shell |
| Listes à puces, tableaux | Messages d'erreur exacts |
| Justifications de design | Diff git |

> ✋ **C'est un mode de communication, pas un style de code.** Ne pas confondre avec [`ponytail`](../ponytail/SKILL.md) qui agit sur la *quantité de code écrit*.

## Quand l'utiliser dans le pipeline

| Agent | Usage caveman recommandé |
|-------|------------------------|
| **Reviewer** | Verdict + chaque commentaire (loc + problème + fix attendu) |
| **Test Engineer** | Rapport pass/fail + cause d'échec |
| **Security Reviewer** | Liste des failles + scénario d'attaque |
| **Context Manager** | Résumés de fichiers volumineux dans le bundle |
| **Git Integration** | Rapport CI / état de la branche |
| **Senior Coder** | UNIQUEMENT pour le commentaire autour du code, pas le code |

> ⛔ **Reporter PO** et **Architect Lead** ne passent pas en caveman par défaut — leurs livrables (spec, ADR) doivent rester lisibles pour l'utilisateur humain.

## Niveaux d'intensité

| Niveau | Exemple |
|--------|---------|
| `lite` | "Recommande `useMemo` ici." |
| `full` (défaut) | "Wrap in `useMemo`." |
| `ultra` | "useMemo." |

## Exemples avant/après

**Reviewer — verdict normal**
> Il y a un bug à la ligne 42 du fichier `src/auth.py` : la fonction ne gère pas le cas où l'utilisateur n'a pas de token. Cela peut crasher la requête. Le Senior Coder devrait ajouter un check `if not user.token: return None` avant l'appel.

**Reviewer — verdict caveman**
> `src/auth.py:42` BLOQUANT. `user.token` peut être None → crash. Fix : guard + return None avant appel.

**Test Engineer — rapport normal**
> J'ai exécuté la suite complète de tests. 47 tests passent, 2 échouent. Le premier échec est dans `tests/test_auth.py` à la ligne 88, où le test attend un code 200 mais reçoit un 401...

**Test Engineer — caveman**
> 47 PASS, 2 FAIL. `tests/test_auth.py:88` : attend 200, reçoit 401. Cause : token absent après refacto auth.

## Règles d'or

- 🪶 **Code/commandes/erreurs : intacts.** Caveman compresse les *mots autour*.
- 🌐 **Langue préservée.** Si l'agent écrit en français, le caveman reste français compressé.
- 🚫 **Pas appliqué aux livrables utilisateur** (spec, ADR, docs `README.md`).
- ⚖️ **Sévérité visible.** BLOQUANT/CRITIQUE/HAUTE/MOYENNE/BASSE restent en majuscules complètes même en caveman.
