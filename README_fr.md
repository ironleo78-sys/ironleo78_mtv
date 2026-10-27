# IronLeo78 MTV (v0.01)

*[English version: README.md](README.md)*

**Transformez votre chanson en clip vidéo, un extrait à la fois, sans construire un workflow de 50 nodes.**

*Pré-alpha. Un pack de nodes ComfyUI pour MiniMax H3 : un chanteur ou un musicien interprète votre morceau, et chaque extrait est découpé sur votre propre enregistrement.*

## Le pitch

Faire un clip synchronisé dans ComfyUI, c'est normalement un graphe géant : chargeurs de modèles, LoRA, découpe audio, images de référence, conditionnement, images guides, samplers, décodeurs, sauvegarde, puis un deuxième graphe pour l'upscale. Et il faut le refaire ou le recâbler pour chaque segment de la chanson.

IronLeo78 MTV regroupe tout cela en **trois nodes** :

- **Choisissez une chanson, cliquez sur Run.** Le node découpe la tranche audio correspondante, la fige dans le latent vidéo et génère l'image qui suit la musique. MiniMax H3 n'invente jamais de son : ce que vous entendez, c'est votre enregistrement.
- **Un extrait par Run, et il retient où il en est.** Un panneau de segments sur le node indique combien de segments contient votre chanson, lequel est le prochain et votre progression. Sautez à n'importe quel segment, refaites un mauvais extrait, ou laissez-le parcourir toute la chanson.
- **Continuité intégrée.** *Guide* fait démarrer chaque extrait sur la dernière image du précédent, pour que la performance s'enchaîne.
- **Suivez un seul instrument.** *Audio Stem* sépare la chanson une fois (voix, guitares, batterie, basse) et permet à l'image de ne suivre que cette partie. Les stems sont mis en cache sur disque, jamais séparés deux fois.
- **Upscalez plus tard, seulement ce que vous aimez.** Activez *Save Latent* et chaque extrait laisse derrière lui son latent et son conditionnement. Envoyez ceux que vous voulez au Revitalizer pour une version raffinée en 2 MP.

### Combien de nodes économisés

Compté d'après ce que le code appelle, donc à prendre comme approximatif :

| Node du pack | Remplace environ | De quoi il s'agit |
|---|---|---|
| **IronLeo78 MTV** | **30+ nodes** | chargeurs de modèle, de 2 LoRA, du backend d'attention, de l'encodeur de texte et de 2 VAE, chargeurs audio / vidéo / 3 images, MiniMax H3 reference-to-video et guide, découpe + encodage audio, nodes de masque, AV concat / separate, bruit, guider, sélection du sampler, scheduler, sampler, 2 décodeurs, Create Video, Save Video, sauvegarde des latents |
| **IronLeo78 2in1 Revitalizer** | **20+ nodes** | chargeurs de latent et de conditionnement, UNET + interrupteur LoRA + backend d'attention, AV separate / concat, upscaler de latent H3, nodes de masque, bruit, guider, sélection du sampler, sampler, 2 chargeurs de VAE, 2 décodeurs, Create Video, Save Video |
| **IronLeo78 MTV Model Loader** | optionnel | un seul node pour changer modèles, LoRA, étapes et seed de plusieurs nodes MTV à la fois |

**Environ 50 nodes (et tout leur câblage) deviennent 2 nodes avec lesquels vous travaillez vraiment.** Le Model Loader est le troisième, optionnel.

## Les nodes

Tous sous **IronLeo78 > MTV**.

| Node | Id | Ce qu'il fait |
|---|---|---|
| **IronLeo78 MTV (v0.01)** | `IronLeo78_MTV` | Un extrait par Run, découpé et synchronisé sur votre chanson. |
| **IronLeo78 MTV Model Loader** | `IronLeo78_MTV_ModelLoader` | Optionnel. Modèle de diffusion, LoRA Turbo et personnalisée, encodeur de texte, VAE, nombre d'étapes, seed. |
| **IronLeo78 2in1 Revitalizer** | `IronLeo78_2in1_Revitalizer` | Upscale et raffine un extrait à partir de son latent + conditionnement sauvegardés, puis enregistre la vidéo. |

```
chanson -> MTV (Save Latent ON) -> extraits + .latent / .conditioning
                                      '-> Revitalizer -> extrait upscalé
```

## Installation

1. Placez le dossier `ironleo78_mtv` (avec `__init__.py` directement à l'intérieur) dans `ComfyUI/custom_nodes/`.
2. Redémarrez ComfyUI, puis rafraîchissez le navigateur à fond (Ctrl+F5).
3. Clic droit sur le canevas, **Add Node > IronLeo78 > MTV**.

**Il vous faut :**

- ComfyUI avec ses propres nodes **MiniMax H3**. PyAV, torchaudio et safetensors sont livrés avec ComfyUI. Aucun paquet pip supplémentaire.
- Les fichiers de modèles H3 dans les dossiers habituels : `diffusion_models`, `loras`, `text_encoders`, `vae`.
- **Seulement pour l'étape d'upscale du Revitalizer :** le node tiers *Comfyui_Minimax_h3_latent_Upscaler* et son modèle :
  `cd ComfyUI/custom_nodes && git clone https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler.git`
  puis placez `h3_upscaler_lms_v0.1.safetensors` dans `ComfyUI/models/latent_upscale_models/`. Le Revitalizer l'appelle par son nom et ne l'inclut pas (MIT, (c) LBH-123-AI). Sans lui, mettez Upscale sur OFF dans le Revitalizer.
- Les poids Hybrid Demucs (environ 320 Mo) se téléchargent tout seuls la première fois qu'un Audio Stem est utilisé.

```
ComfyUI/custom_nodes/ironleo78_mtv/
├── __init__.py
├── mtv.py                              (le node MTV)
├── model_loader.py                     (Model Loader)
├── revitalizer.py                      (2in1 Revitalizer)
├── conditioning_io.py                  (lecture / écriture des fichiers .conditioning)
├── stems.py                            (Audio Stem : Hybrid Demucs + cache disque)
├── requirements.txt
├── README.md
├── README_fr.md
├── tests/                              (optionnel)
└── web/
    ├── ironleo78_mtv.js                (panneau de segments, vignettes, boîte d'état)
    └── ironleo78_2in1_revitalizer.js   (bouton Upload)
```

## Instructions

### Faire un clip

1. Ajoutez **IronLeo78 MTV**. Au besoin, ajoutez le **Model Loader** et branchez sa sortie `models` à l'entrée `models` du MTV.
2. **Custom Audio File :** choisissez votre chanson. Son nom devient le dossier de sortie et le préfixe des fichiers.
3. **Bypassed Audio Latent = Custom Audio.** La chanson est découpée en morceaux de la longueur d'un extrait.
4. **Use Video = OFF** (image vers vidéo) est le cas normal. **Picture1** est le chanteur / musicien et fixe la taille et le format ; Picture2-3 sont des références supplémentaires (tenue, lieu). Use Video ON laisse plutôt une vidéo existante piloter les images.
5. Écrivez le **prompt** en vous référant à `<Picture 1>`, etc. Décrivez la performance (chante face caméra, joue de la guitare, éclairage de scène). Changez-le entre les Runs pour suivre les sections de la chanson.
6. Réglez **duration** (15 s par défaut), **Next Segment On Run = ON**, **Guide = ON**. Activez **Save Latent = ON** si vous voulez upscaler plus tard.
7. Regardez le **panneau de segments** en haut du node, puis cliquez sur Run une fois par segment (ou mettez-en plusieurs en file). Après le dernier segment, le node s'arrête sans bruit.
8. **Commencer au milieu :** tapez un numéro de segment dans la rangée de saut et appuyez sur **Go**. **Latest** revient au point le plus avancé. **Reset** recommence au début.
9. **Refaire un mauvais extrait :** sautez-y, lancez Run, puis appuyez sur Latest. Le nouvel extrait est enregistré à côté de l'ancien, et le script d'assemblage utilise le plus récent.

Où le découpage commence : le **compteur de segments** est la seule chose qui en décide. Le segment 1 commence à la seconde 0 ; chaque segment suivant commence une vraie durée d'extrait plus tard (`frames / 24 fps` ; durée 5 s = 124 images = 5,17 s). Sautez au segment N et le prochain Run commence à `(N - 1) x durée d'un extrait`, pour l'audio et la vidéo ensemble.

### Upscaler un extrait avec le Revitalizer

1. Faites l'extrait avec **Save Latent = ON**.
2. Ajoutez **IronLeo78 2in1 Revitalizer** et appuyez sur **R** pour rafraîchir ses listes. Le menu `latent` affiche tous les `*_video.latent` de `ComfyUI/output/`, du plus récent au plus ancien. Le `.conditioning` correspondant est choisi automatiquement.
3. Pour un raffinage fidèle, réglez `seed` sur la seed de l'extrait (le fichier `.json` associé l'indique comme `same_noise_seed`).
4. Lancez. La progression va dans la console sous la forme `[Revitalizer] ...`, et la vidéo terminée est enregistrée et prévisualisée.
5. Extraits venant d'une autre machine : cliquez sur **Upload latent / conditioning files...** et choisissez ensemble le `_video.latent`, le `_audio.latent` et le `.conditioning`. Ils sont copiés dans `ComfyUI/input/ironleo78_revitalizer/` et sélectionnés pour vous.


## Réglages du MTV

| Réglage | Ce qu'il fait |
|---|---|
| **Turbo** | ON = LoRA Turbo, 4 étapes. OFF = 25 étapes, sans LoRA Turbo. |
| **Use Video / Video File** | ON = la vidéo fournit les images et la taille. OFF = Picture1 fixe la taille. |
| **Custom Audio File** | Votre chanson. |
| **Audio Stem** | Song, Vocals, Guitars, Drums ou Bass : quelle partie de la chanson est utilisée. |
| **megapixels** | 0,1 à 1,0 (0,2 par défaut), côtés multiples de 32. |
| **duration** | Secondes par extrait (15 par défaut) ; la longueur réelle suit les règles d'images de MiniMax (frames % 17 == 5). |
| **Next Segment On Run** | ON = chaque Run passe au segment suivant. OFF = toujours le segment 1. |
| **Bypassed Audio Latent** | Audio From Video, ou Custom Audio (votre chanson, découpée). |
| **Save Latent** | OFF (défaut) = seulement l'extrait. ON = sauvegarde aussi le latent vidéo / audio et le conditionnement. |
| **Guide** | La dernière image de l'extrait précédent guide le suivant (nécessite Next Segment ON). |
| **Picture1-3** | Images de référence avec vignettes. |

Fixé dans le node : BasicGuider, `res_multistep`, scheduler `simple`, 24 fps, mp4 / h264.

### Audio Stem

- La première fois qu'un stem est choisi pour une chanson, Hybrid Demucs sépare **les quatre** d'un coup (environ 13 s pour une chanson de 2 minutes sur un GPU typique). Ensuite, chaque Run et chaque session lit simplement un fichier.
- Enregistrés dans `ComfyUI/output/<Song>/stems/` sous les noms `<Song>_Vocals.wav`, `_Guitars.wav` (le « other » de Demucs : guitares, claviers, synthés), `_Drums.wav`, `_Bass.wav`, plus `<Song>_stems.json` (écrit en dernier, pour qu'un travail interrompu ne soit jamais considéré comme valide).
- Réutilisés tant que la chanson sous ce nom a le même contenu (SHA-1). Pour forcer une nouvelle séparation, supprimez le dossier `stems`.
- Seul le **Custom Audio File** est séparé, pas la bande son d'un Video File.

### Save Latent = ON

```
output/MySong/MySong_seg004_A_00001_.mp4                  (l'extrait)
output/MySong/MySong_seg004_A_00001_video.latent
output/MySong/MySong_seg004_A_00001_audio.latent
output/MySong/MySong_seg004_A_00001.conditioning
output/MySong/MySong_seg004_A_00001_.json                 (fichier associé : prompt, réglages et les trois noms de fichiers)
```

Le numéro est celui de l'extrait, donc un refait n'écrase jamais rien. Le `.conditioning` contient votre prompt et vos images encodés par MiniMax H3, sans le guide. Tout ce qui n'a pas pu être stocké est listé dans le fichier associé sous `latent_details.conditioning_unsupported_items` (normalement rien). Si le latent ou le conditionnement ne peut pas être écrit, l'extrait est quand même produit et une note apparaît dans la boîte d'état.

### Model Loader

Aucune entrée, une sortie `models`. Change le modèle de diffusion, la LoRA personnalisée (interrupteur, fichier, force 0,65), la LoRA Turbo, l'encodeur de texte Qwen3-VL, les VAE vidéo / audio, le nombre d'étapes (4 / 25) et la seed (1978, fixe). Rien de branché = valeurs par défaut intégrées. Plusieurs nodes MTV peuvent partager un même loader.

### Réglages du Revitalizer

| Entrée | Défaut | Ce qu'elle fait |
| :--- | :--- | :--- |
| `latent` | extrait le plus récent | Tous les `*_video.latent` de `output/` plus ceux téléversés. Appuyez sur R après un nouveau run. |
| `conditioning` | `(match the latent)` | Charge `<extrait>.conditioning`. Choisissez-en un autre pour utiliser celui d'un autre extrait. |
| `freeze_audio` | ON | La passe de raffinage ne rebruite pas la chanson. |
| `unet_name`, `vae_video`, `vae_audio` | les fichiers H3 | Modèles. |
| `lora_on`, `lora_name`, `lora_strength` | OFF, turbo 4 étapes, 1.0 | LoRA sur le modèle seulement. |
| `attention_backend` | comfy kitchen attention | Retombe tout seul sur l'attention PyTorch. |
| `upscale_on` | ON | OFF = raffinage à la taille sauvegardée. |
| `upscale_model` | `h3_upscaler_lms_v0.1` | Depuis `latent_upscale_models`. |
| `megapixels` | 2.0 | Taille cible, 0,1 à 2,0. |
| `temporal_chunking`, `force_unload`, `upscale_device`, `upscale_precision` | ON, ON, cuda, fp16 | Comme le node d'upscale. |
| `seed`, `sampler_name` | 0 (aléatoire), euler | |
| `filename_prefix` | `video/MiniMax_H3` | Mêmes noms et même aperçu que Save Video. |

Fixé à l'intérieur : sigmas en 5 étapes `0.9231, 0.8780, 0.8000, 0.6316, 0.3158, 0.0000`, align 32, 8 bits, sRGB, 24 fps, décodage VAE normal, toujours enregistré. Sorties : `video`, `images`, `audio`, `latent` (le latent AV raffiné) et `status`.

## Sorties

`output/MySong/MySong_seg004_A_00001_.mp4`, un fichier `.json` avec le prompt complet et les réglages à côté de chaque extrait, et `MySong_manifest.csv` avec la seconde de début / fin de chaque extrait dans la chanson (plus `audio_stem`, `latent_file` et `conditioning_file`).

## Dépannage

| Problème | Que faire |
|---|---|
| **Nodes absents** | Le dossier doit se trouver directement dans `custom_nodes/`, avec `__init__.py` à l'intérieur. Redémarrez ComfyUI, appuyez sur Ctrl+F5, et cherchez dans la console une erreur d'import mentionnant `ironleo78_mtv`. |
| **Erreur d'import liée à MiniMax H3** | Mettez ComfyUI à jour : le MTV a besoin de ses nodes MiniMax H3 natifs. |
| **Le Revitalizer apparaît en double ou plante au démarrage** | Une autre copie du Revitalizer est installée dans `custom_nodes/`. N'en gardez qu'une. |
| **Le panneau affiche « Segments: unknown »** | Choisissez un Custom Audio File avec Bypassed Audio Latent = Custom Audio (ou un Video File avec Use Video ON). |
| **Un menu affiche « None » ou un modèle est « not found »** | Placez le fichier dans le bon dossier `ComfyUI/models/` et appuyez sur R. Utilisez le Model Loader si vos noms de fichiers diffèrent des valeurs par défaut. |
| **Le node s'arrête et ne fait rien** | Vous avez dépassé le dernier segment de la chanson. Utilisez Jump, Latest ou Reset dans le panneau. |
| **L'image ne suit pas la bonne partie de la chanson** | Vérifiez **Audio Stem** et que **Bypassed Audio Latent = Custom Audio**. |
| **La séparation des stems échoue : checkpoint corrompu** | Supprimez le fichier Hybrid Demucs dans `~/.cache/torch/hub/checkpoints/` et relancez. |
| **Mémoire insuffisante pendant la séparation ou l'échantillonnage** | Baissez megapixels, fermez les autres programmes GPU, ou réessayez (la séparation réessaie une fois après avoir déchargé les modèles). |
| **Aucun fichier `.latent` / `.conditioning`** | Ils ne sont sauvegardés qu'avec **Save Latent = ON**. Regardez dans `output/<Song>/`. Une note dans la boîte d'état indique si la sauvegarde a échoué (disque plein, par exemple). |
| **La liste du Revitalizer affiche « none found »** | Faites un extrait avec Save Latent ON, puis appuyez sur R, ou utilisez le bouton Upload. |
| **Revitalizer : « audio latent is missing » ou « conditioning not found »** | Les trois fichiers d'un extrait doivent partager le même nom et le même dossier. Téléversez-les tous les trois ensemble. |
| **Revitalizer : « node ... not found »** | Le node tiers Minimax H3 Latent Upscaler n'est pas installé. Installez-le, ou mettez Upscale sur OFF. |
| **Revitalizer : mémoire vidéo insuffisante** | Baissez `megapixels`, mettez Upscale sur OFF, ou fermez les autres programmes GPU. La console affiche l'étape en échec et un conseil. |

## Tests (optionnels, aucun GPU requis)

```
python tests/test_phased_run.py
python tests/test_conditioning_io.py
python tests/test_stems.py
python tests/test_revitalizer.py
node   tests/test_migration.mjs
node   tests/test_panel_jsdom.mjs      # nécessite : npm install jsdom
```

Ces tests s'exécutent contre des doublures de ComfyUI. Cette version pré-alpha n'a pas encore été lancée dans un ComfyUI réel : signalez tout comportement étrange que vous observez.

par IronLeo78
