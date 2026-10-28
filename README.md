# myNews

O singură pagină cu titlurile știrilor din ultimele **24 de ore** de la **HotNews, G4Media, Mediafax, Digi24, Descoperă, Biziday, Zona IT, Go4it și Playtech**, cu linkuri către articolele originale.

Interfață în română, cu listă compactă pe telefon, filtre pe surse, căutare fără diacritice, sortare și ore afișate în fusul `Europe/Bucharest`. La apăsarea cardului, titlului sau imaginii se deschide o previzualizare în pagină, cu sursa, data, imaginea disponibilă și un scurt extras RSS. Butonul „Citește la sursă” deschide direct articolul original.

## Afișare compactă și contrast

Fără introducere mare: pagina începe direct cu actualizarea, filtrele și știrile. Cardurile folosesc miniaturi laterale, cu o coloană pe telefon și până la patru pe desktop. Toate sursele sunt accesibile prin filtre derulabile orizontal pe ecrane mici.

Tema **noapte este implicită**, indiferent de tema sistemului. Butonul **Noapte / Zi** din antet schimbă paleta întregii pagini, inclusiv previzualizarea, câmpurile și avertismentele. Preferința este salvată în `localStorage` și aplicată înaintea stilurilor pentru a evita afișarea temporară a altei teme. Dacă stocarea este blocată, comutatorul funcționează în continuare în pagina curentă, iar problema este raportată în consolă.

## Imagini și previzualizare

- Agregatorul extrage referințe la imagini din `media:thumbnail`, `media:content`, enclosure-uri de tip imagine și imaginile HTML din RSS. Sunt acceptate doar URL-uri HTTPS, inclusiv de pe CDN-urile folosite de publicații. Nu descarcă paginile articolelor și nu salvează copii ale fotografiilor.
- Imaginile sunt încărcate direct de la gazda indicată în RSS, fără antet Referer; gazda poate vedea adresa IP a vizitatorului. Pe carduri se încarcă la nevoie (`loading="lazy"`). Dacă gazda blochează imaginea sau aceasta dispare, este afișat mesajul „Imagine indisponibilă”. Știrile fără imagine rămân accesibile.
- Previzualizarea afișează numai descrierea/rezumatul RSS, fără HTML, limitat la 45 de cuvinte și 280 de caractere (plus marcajul de trunchiere). Nu importă textul integral din `content:encoded` și nu ocolește abonamentele. Dacă lipsește extrasul, interfața indică explicit acest lucru.
- Numele publicației, linkul articolului original și creditul imaginii, când este oferit în RSS, apar în previzualizare. Imaginile și textele aparțin titularilor drepturilor; disponibilitatea în RSS nu transferă drepturile de republicare. Publicarea integrală sau reutilizarea materialelor necesită verificarea licenței/permisiunilor publicațiilor.
- Fereastra de previzualizare poate fi închisă cu butonul „Închide”, tasta Escape sau apăsarea fundalului. Filtrele și poziția în listă sunt păstrate.

## Publicare pe GitHub Pages

1. Pentru publicare gratuită, fă repository-ul public din **Settings → General → Danger Zone → Change repository visibility**. Verifică mai întâi că nu conține informații private. Un repository privat necesită un plan GitHub care permite Pages; pagina trebuie configurată cu acces public.
2. În **Settings → Pages → Build and deployment → Source**, selectează **GitHub Actions**.
3. Trimite aceste fișiere pe ramura `main`. Workflow-ul **Actualizează și publică știrile** rulează la push; îl poți porni și din **Actions → Actualizează și publică știrile → Run workflow**.
4. După publicare, pagina va fi disponibilă la **https://v-khdumi.github.io/myNews/**. Linkul efectiv apare și în rularea workflow-ului.

Activarea Pages și, dacă este cazul, schimbarea vizibilității necesită drepturi în setările repository-ului. Codul nu schimbă automat vizibilitatea.

## Actualizare și limite

- GitHub Actions preia RSS-urile la minutele **07 și 37** ale fiecărei ore. Rulările programate pot întârzia; nu este o actualizare în timp real. În repository-uri publice fără activitate timp de 60 de zile, GitHub poate dezactiva programarea; reactiveaz-o din Actions.
- Browserul reîncarcă ediția publicată la fiecare 5 minute și elimină știrile expirate în fiecare minut, chiar dacă pagina rămâne deschisă. „Reîncarcă” citește ediția publicată, nu declanșează preluarea RSS.
- Atât agregatorul, cât și pagina filtrează după **data publicării**, între momentul curent minus 24 de ore și momentul curent. Articolele fără dată validă sau cu dată în viitor nu sunt afișate.
- Sunt folosite fluxurile publicațiilor: HotNews `/feed` (alternativ `/rss`), G4Media `/feed`, Mediafax `/rss` (alternativ `/feed`), Digi24 `/rss`, Descoperă `/feed` (alternativ `/rss`), Biziday `/feed`, Zona IT `/feed`, Go4it `/feed` (alternativ `/rss`) și Playtech `/feed`. Pentru fluxurile WordPress se încearcă paginarea `?paged=N`; sunt urmate și linkurile RSS/Atom `rel="next"`. Există o limită de 40 de pagini pe sursă și rulare.
- Acoperirea depinde de fluxurile publicate, de suportul pentru paginare și de disponibilitatea publicațiilor; nu poate fi garantat că fiecare articol de pe site-uri apare în RSS. Interfața semnalează sursele indisponibile și fluxurile cu acoperire limitată.
- Ediția precedentă este păstrată în cache-ul Actions. Articolele încă recente sunt păstrate chiar dacă dispar din RSS sau o sursă nu răspunde. Cache-ul poate fi eliminat de GitHub, deci nu este o arhivă permanentă.
- Dacă toate sursele eșuează și nu există știri recente în cache, publicarea este oprită pentru a nu înlocui ediția existentă cu una goală. Interfața existentă avertizează când ediția este veche și nu afișează articole mai vechi de 24 de ore.
- Nu sunt necesare chei API, servicii CORS intermediare, baze de date sau dependențe Python/JavaScript externe. Preluarea RSS are loc pe serverele GitHub, nu direct din browser.

## Rulare locală

Necesită Python 3.12+; pentru testele JavaScript, Node.js 22+.

```sh
python -m unittest discover -s tests -p 'test_*.py'
node --test tests/*.test.mjs
python scripts/aggregate.py --previous data/news.json --output data/news.json
python -m http.server 8000
```

Deschide `http://localhost:8000`. Fără rularea agregatorului, pagina afișează explicit starea „Prima ediție este în pregătire”, nu știri fictive. Preluarea efectivă necesită acces la internet și DNS funcțional pentru cele nouă publicații. Edițiile anterioare cu mai puține surse rămân compatibile; noile surse apar ca fiind în așteptarea primei actualizări.