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
| Újraindítás gomb | Csak akkor jön létre, ha a router felülete kínál újraindítást. |

Csak olvas; az egyetlen írási művelet az újraindítás gomb. Wi-Fi-jelszót és belépési adatokat tartalmazó oldalakat nem tölt le.

## Telepítés

### Marketplace / HACS (ajánlott)

1. Home Assistant 2026.11-től: **Beállítások → Marketplace → egyéni tároló hozzáadása (Add from link)**. Régebbi verzión: **HACS → ⋮ → Custom repositories**.
2. Tároló: ennek a GitHub-tárolónak a címe, típus: **Integration**.
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
- **Diagnosztika**: az integráció oldalán a „Diagnosztika letöltése” a firmware oldalainak csak olvasó felmérését is tartalmazza (MAC- és nyilvános IP-címek kitakarva).

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
