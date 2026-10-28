# myNews

O singură pagină cu titlurile știrilor din ultimele **24 de ore** de la **HotNews, G4Media, Mediafax și Digi24**, cu linkuri către articolele originale.

Interfață în română, adaptată pentru telefon, cu filtre pe surse, căutare fără diacritice, sortare și ore afișate în fusul `Europe/Bucharest`. Nu copiază articolele integrale, fotografiile sau conținutul cu abonament.

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
- Sunt folosite fluxurile publicațiilor: HotNews `/feed` (alternativ `/rss`), G4Media `/feed`, Mediafax `/rss` (alternativ `/feed`), Digi24 `/rss`. Pentru fluxurile WordPress se încearcă paginarea `?paged=N`; sunt urmate și linkurile RSS/Atom `rel="next"`. Există o limită de 40 de pagini pe sursă și rulare.
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

Deschide `http://localhost:8000`. Fără rularea agregatorului, pagina afișează explicit starea „Prima ediție este în pregătire”, nu știri fictive. Preluarea efectivă necesită acces la internet și DNS funcțional pentru cele patru publicații.