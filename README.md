# Technicolor Homeware router – Home Assistant integráció

Egyedi Home Assistant integráció a Telekom által adott **Technicolor FGA2235 (Magenta Home Box)** és más, *Homeware* firmware-t futtató Technicolor routerekhez. Helyben, a router saját webes felületén keresztül olvas, felhő nélkül.

*Custom Home Assistant integration for Technicolor routers running Homeware firmware (tested on Telekom Hungary FGA2235 MAG, firmware 19.5). Local polling, no cloud.*

## Mit tud

| Entitás | Leírás |
|---|---|
| Jelenlét-követők (`device_tracker`) | Minden eszköz, amit a router lát (MAC alapján). A HA szokása szerint alapból kikapcsolva jönnek létre, a kívántakat kell engedélyezni. |
| Csatlakozott eszközök | Darabszám, attribútumban a listával (név, IP, MAC, kapcsolat típusa). |
| Internetkapcsolat, Szélessávú kapcsolat | Kapcsolat-állapot (`connectivity`). |
| WAN IP-cím | A nyilvános IP-cím. |
| Utolsó újraindítás | A router üzemidejéből számolva. |
| CPU-terhelés, Memóriahasználat, Szoftververzió | Ha a firmware kiírja. |
| Kapcsolók (`switch`) | Wi-Fi 2,4 / 5 GHz, vendég Wi-Fi 2,4 / 5 GHz, WPS, Samba fájlmegosztás, DLNA – lásd lent. |
| Újraindítás gomb | Csak akkor jön létre, ha a router felülete kínál újraindítást. |

## Kapcsolók (router-beállítások)

A kapcsolók listája a `custom_components/technicolor_homeware/switches.json` fájlban van; az alapértelmezett lista a Telekom FGA2235-ön (Homeware 19.5) kipróbált beállításokat tartalmazza. Egy kapcsoló csak akkor jön létre, ha a router oldalán tényleg megtalálható.

Biztonsági szabályok:

- **Oldal-ellenőrzés**: a Wi-Fi-kapcsolók csak akkor olvasnak és írnak, ha a router oldalán az adott hálózat füle az aktív (`expect_active`), így rossz oldalon soha nem kapcsolnak.
- **Csak a változás megy át** (`"post": "minimal"`, alapértelmezett): a mentés csak az átkapcsolt mezőt küldi, a Wi-Fi-jelszó és a hálózatnév nem hagyja el a Home Assistantot.
- **Teljes űrlap** (`"post": "form"`): ahol a router a teljes űrlapot várja (pl. megosztás), a friss űrlapot küldi vissza változatlanul, csak az egy mezőt átírva.
- A kártyán a kapcsoló a koppintás pillanatában átvált; az integráció a router válaszából (szükség esetén az oldal újraolvasásával) ellenőrzi a mentést, és ha a router nem alkalmazta, hibát jelez és visszaáll.
- A fájlmegosztás bekapcsolása a Samba általános kapcsolóját is bekapcsolja (`with_on`), mert a router enélkül nem engedi; a kikapcsolás a Sambát nem érinti.

Saját kapcsoló felvétele (pl. más firmware-hez): egy új sor a `switches.json`-ba, majd az integráció újratöltése (nem kell újraindítás).

| Mező | Jelentés |
|---|---|
| `key`, `name` | Egyedi azonosító és megjelenített név |
| `page` | A router oldala, pl. `modals/wireless-modal.lp?radio=radio_5G&iface=wl1` |
| `field` vagy `label` (+ `index`) | A kapcsoló mezőneve, vagy a címkéje az oldalon |
| `expect_active`, `expect_ids` | Oldal-ellenőrzés: aktív fül azonosítója / `{elem id: szöveg}` |
| `post` | `minimal` (alap) vagy `form` |
| `with_on` | Bekapcsoláskor ezeket a mezőket is beállítja, pl. `{"samba": "1"}` |
| `icon`, `enabled_default`, `config` | Ikon, alapból engedélyezve, beállítás-kategória |

A mezőneveket a diagnosztika `probe` része mutatja meg (a jelszavak kitakarva). Frissítéskor a `switches.json` felülíródik, a saját bővítéseket érdemes ide, a tárolóba is felvenni.

Wi-Fi-jelszót, belépési adatokat és a Wi-Fi QR-kódot tartalmazó oldalakat a felmérés nem tölt le, illetve kitakar.

## Telepítés

### Marketplace / HACS (ajánlott)

1. Home Assistant 2026.11-től: **Beállítások → Marketplace → egyéni tároló hozzáadása (Add from link)**. Régebbi verzión: **HACS → ⋮ → Custom repositories**.
2. Tároló: `https://github.com/sariistvanbenedek/ha-technicolor-homeware`, típus: **Integration**.
3. Telepítsd, majd indítsd újra a Home Assistantot.

### Kézzel

Másold a `custom_components/technicolor_homeware` mappát a Home Assistant `config/custom_components/` mappájába, majd indítsd újra a Home Assistantot.

## Beállítás

**Beállítások → Eszközök és szolgáltatások → Integráció hozzáadása → Technicolor Homeware router**

- Router címe: `192.168.1.1`
- Felhasználónév: `admin`
- Jelszó: a router alján lévő matricán az **Access Key**

Ha a router HTTPS-re irányít át, az integráció ezt magától követi.

## Hibakeresés

- **„Nem érhető el a router webes felülete”**: a pontos ok a Home Assistant naplójában van (`custom_components.technicolor_homeware`).
- **„Hibás felhasználónév vagy jelszó”**: ellenőrizd az Access Key-t. Több rossz próbálkozás után a router egy időre letilthatja a belépést. Ilyenkor a router bejelentkező oldala és szkriptjei a `custom_components/technicolor_homeware/debug/` mappába kerülnek (jelszó nélkül), hogy egy eltérő firmware-t ki lehessen elemezni.
- **Diagnosztika**: az integráció oldalán a „Diagnosztika letöltése” a firmware oldalainak csak olvasó felmérését is tartalmazza (MAC- és nyilvános IP-címek, jelszavak kitakarva), valamint az utolsó sikertelen mentés részleteit (az elküldött értékek nélkül).
- **Egy kapcsoló hibát jelez**: a napló és a diagnosztika `last_save_error` része megmutatja a router válaszát. Ha a router „Some parameters failed validation” üzenetet ad, próbáld a `"post": "form"` beállítást.

## Működés

A router webes felülete SRP-6 jelszavas belépést használ, így a jelszó nem megy át a hálózaton. Az integráció 30 másodpercenként lekéri az eszközlistát és a kezdőlapot, 5 percenként a rendszerinformációkat, és lejárt munkamenetnél automatikusan újra belép. Ha a jelszó megváltozik, a Home Assistant kéri az újat.

## Fejlesztés

```bash
pip install -r requirements_test.txt
pytest
```

A tesztek egy szimulált Homeware routerrel futnak (SRP-szerverrel együtt).

## Köszönet

- SRP-kliens: [cocagne/pysrp](https://github.com/cocagne/pysrp) (MIT) és [shaiu/techicolorgateway](https://github.com/shaiu/techicolorgateway) (MIT) alapján.
- A `tests/fixtures` minta-oldalai a [shaiu/techicolorgateway](https://github.com/shaiu/techicolorgateway) tárolóból származnak (MIT).

## Licenc

MIT – lásd a [LICENSE](LICENSE) fájlt.
