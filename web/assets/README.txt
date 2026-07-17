VRAI PIXEL-ART (look "genre la capture") — 3 étapes
====================================================

1) PACK D'ASSETS (l'art, que je ne peux pas générer)
   LimeZu "Modern Interiors" : https://limezu.itch.io/moderninteriors
   (+ addon bureau : https://limezu.itch.io/modernoffice)
   Version gratuite dispo. LIS LA LICENCE de la page avant usage.
   Tu peux aussi prendre n'importe quel tileset 16px (Kenney, etc.).

2) PEINS LA CARTE DANS TILED  (https://www.mapeditor.org/ , gratuit)
   - Nouvelle carte ORTHOGONALE, 72 x 48 tuiles, taille de tuile 16 x 16 px.
     (72x48 @16 = 1152x768 = le monde actuel → la caméra/les agents collent direct.)
   - Importe le PNG du pack comme tileset (UN seul tileset).
   - Peins tes calques de tuiles : sol, murs, meubles, pièces.
   - Fichier > Exporter sous... > JSON.
       Format de calque = CSV (ou "non compressé"), PAS base64/zlib.

3) DÉPOSE ICI (web/assets/) :
   - office.json      (la carte exportée)
   - <ton_tileset>.png (le même PNG référencé dans office.json)
   Recharge la page → le bureau bascule sur le vrai tileset.
   Absent ou cassé → repli automatique sur le bureau procédural (rien ne casse).

Note : les sprites des 9 agents restent les persos actuels pour l'instant
(YAGNI). Persos pixel-art animés = étape suivante quand le décor te plaît.
