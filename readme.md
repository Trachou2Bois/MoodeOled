# MoodeOLED

Un ensemble de scripts Python pour contrôler un écran OLED SSD1306 et interagir avec Moode Audio sur Raspberry Pi.

**Interfaces disponibles :**

- `nowoled` : Affichage de la lecture en cours et contrôle multimédia.
- `navoled` : Navigation, recherche et gestion de la bibliothèque musicale.
- `queoled` : Gestion de la file de lecture (lecture, ajout, suppression, playlist).

---

⚠ **Attention projet en cours de développement. Faire une sauvegarde avant d'aller plus loin! Utilisation avec boutons GPIO non testé!**

## 📥 Installation rapide

1. **Installer Git**:
   
   ```bash
   sudo apt update
   sudo apt install git -y
   ```

2. **Cloner le dépôt** :
   
   ```bash
   git clone https://github.com/touf2/MoodeOled.git
   ```

3. **Lancer l'installateur** :
   
   ```bash
   python3 ~/MoodeOled/install/setup.py
   ```

L'installateur (`setup.py`) :

- Installe les dépendances Python et système requises.
- Vérifie la version de Moode (>9.3.7).
- Configure I²C, crée un environnement virtuel et installe les services.
- A la fin de l'installateur il vous sera proposer de lancer un script pour installer et configurer lirc si vous voulez utiliser une télécommande IR. Si vous choisissez "non" vous pourrez le relancer plus tard avec:
  `python3 ~/MoodeOled/install/lirc_setup.py --lang fr` (ou `--lang en`)
- Après avoir installer et configurer les prérequis lirc il est nécessaire de redémarrer et ensuite vous pourrez configurer une télécommande avec:
  `python3 ~/MoodeOled/install/install_lirc_remote.py`

---

⚠️ Important: Dans l'interface de Moode, il faut activer:

- Ready Script (Configure => System) (vous pouvez mettre à 0 seconds)
- LCD Updater (Configure => Peripherals)

⚠️ Si vous voulez tester via boutons GPIO il faut modifier les broches dans `config.ini` et changer `use_gpio = false` à `true` 

---

## 🎛 Configuration des touches

### 🔑 Touches indispensables

Ces touches sont **requises** pour naviguer et contrôler toutes les interfaces :

| Touche               | Rôle générique                                        | Usage spécifique dans `nowoled`                            |
| -------------------- | ----------------------------------------------------- | ---------------------------------------------------------- |
| **KEY\_UP**          | Déplacement vers le haut                              | Volume + si hors menu                                      |
| **KEY\_DOWN**        | Déplacement vers le bas                               | Volume - si hors menu                                      |
| **KEY\_LEFT**        | Déplacement gauche                                    | Précédent / Seek -10s (long press) si hors menu            |
| **KEY\_RIGHT**       | Déplacement droite                                    | Suivant / Seek +10s (long press) si hors menu              |
| **KEY\_OK**          | Ouvre menu / menu Outils (long press) / Validation    | idem                                                       |
| **KEY\_BACK**        | Basculer vers `navoled`/ `queoled`/`nowoled`          | Basculer vers `navoled` (court) / `queoled` (long)         |
| **KEY\_INFO**        | Afficher l’aide contextuelle                          | Idem                                                       |
| **KEY\_CHANNELUP**   | Action contextuelle                                   | Ajouter/Retirer des favoris,  Si radio: ajouter au songlog |
| **KEY\_CHANNELDOWN** | Action contextuelle                                   | Retirer de la file de lecture                              |
| **KEY\_PLAY**        | Si hors menu: Lecture/pause / Extinction (long press) | Si hors menu: Lecture/pause / Extinction (long press)      |

Ces touches sont à configurer soit via LIRC, soit via GPIO (section `[buttons]` du `config.ini`).

### 🎵 Touches multimédia (optionnelles)

Recommandées si disponibles sur votre télécommande, mais **non obligatoires** :

| Touche              | Action                             |
| ------------------- | ---------------------------------- |
| **KEY\_STOP**       | Arrêt de la lecture                |
| **KEY\_NEXT**       | Suivant / Seek +10s (long press)   |
| **KEY\_PREVIOUS**   | Précédent / Seek -10s (long press) |
| **KEY\_FORWARD**    | Seek +10s                          |
| **KEY\_REWIND**     | Seek -10s                          |
| **KEY\_VOLUMEUP**   | Volume +                           |
| **KEY\_VOLUMEDOWN** | Volume -                           |
| **KEY\_MUTE**       | Mute                               |
| **KEY\_POWER**      | Redémarrer / éteindre (long press) |

> **Remarque :** Dans `nowoled`, les touches de navigation (`UP`, `DOWN`, `LEFT`, `RIGHT`) peuvent remplacer les touches multimédia optionnelles si elles ne sont pas présentes. 
> Il est possible d'ajouter des touches et commandes personnalisées dans le script media_key_actions.py si vous voulez utiliser plus de touches de votre télécommande. 
