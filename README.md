# myNews

Portal de știri **România + worldwide**, cu interfață editorială responsive, teme zi/noapte și ediții în **română și engleză**. Extinde agregatorul RSS existent, păstrând fereastra mobilă de 24 de ore, deduplicarea și rezistența la indisponibilitatea surselor.

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fv-khdumi%2FmyNews%2Fmain%2Finfra%2Fazuredeploy.json)

## Ce include

- 12 surse configurate: HotNews, G4Media, Mediafax, Digi24, Descoperă, Biziday, Zona IT, Go4it, Știripesurse.ro, The Guardian, France 24 și Al Jazeera. „Local” înseamnă România în această versiune, nu selecție pe oraș.
- Filtre combinate pe regiune, categorie, publicație, căutare fără diacritice, sortare și opțiunea „doar sinteze bilingve”.
- Știre principală, carduri cu imagini RSS, flux „Pe radar”, cititor accesibil cu Escape și revenire la elementul care l-a deschis. Preferințele de temă și limbă se păstrează local.
- Sinteze factuale RO/EN generate server-side prin **Azure AI Foundry / Azure OpenAI**, cu titlu, rezumat scurt, categorie, model, data generării și link la articolul original.
- Mod RSS funcțional fără AI. Un extras în limba originală este etichetat ca atare: schimbarea limbii interfeței nu pretinde că a tradus un articol neprocesat.
- Publicare statică pe GitHub Pages sau server Flask/Gunicorn pe **Azure Web App Linux**, cu stocare persistentă, actualizare periodică și endpoint-uri de sănătate.

Nu sunt incluse conturi, comentarii, reclame, arhivă permanentă sau un CMS. Nu sunt publicate știri fictive ca și cum ar fi actuale.

## Arhitectură

```text
RSS-uri publice → aggregate.py → deduplicare / ultimele 24h
                             → synthesize.py → Azure OpenAI / Foundry
                             → ediție JSON atomică, cu proveniență
                             → portal RO/EN (Pages sau Web App)
```

`scripts/aggregate.py` păstrează articolele recente din ediția precedentă dacă dispar din RSS sau o sursă cade. Datele de publicare invalide, din viitor sau mai vechi de 24h sunt excluse. Dacă toate sursele cad și cache-ul nu mai conține știri recente, ediția publicată nu este înlocuită cu una goală.

Colectorul urmează paginarea RSS/Atom și, pentru sursele compatibile, paginarea WordPress, cu maximum 40 de pagini/sursă. Fluxurile internaționale nu presupun paginare WordPress. Acoperirea limitată și erorile sunt vizibile în portal; RSS nu garantează toate articolele unei publicații. Categoriile provin din metadatele RSS sau din sinteza AI; în lipsa lor se afișează „Actualitate”.

Browserul verifică ediția la fiecare 5 minute și elimină articolele expirate în fiecare minut. Butonul de actualizare citește ediția publicată, **nu** lansează apeluri AI sau colectare RSS.

## Rulare locală

Python 3.12+ și Node.js 22+ pentru teste. Rulează comenzile din rădăcina repository-ului:

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -p 'test_*.py'
node --test tests/*.test.mjs

# Fără Azure, funcționează ca agregator RSS.
python server.py
```

Deschide `http://localhost:8000`. Colectarea pornește în fundal fără să blocheze interfața. Prima ediție nu apare până când cel puțin o preluare reușește. Este necesar acces DNS/HTTPS către publicații.

Pentru o singură preluare sau găzduire statică:

```sh
python -m scripts.aggregate --previous data/news.json --output data/news.json
python -m http.server 8000
```

Pentru serverul de producție:

```sh
gunicorn --config gunicorn.conf.py server:app
```

## Configurarea Azure AI Foundry

1. Creează o resursă Azure OpenAI/Foundry și un **deployment de model chat care suportă JSON mode**; de exemplu un deployment `gpt-4.1-mini`. Numele deployment-ului, nu numele generic al modelului, se transmite în configurație.
2. Configurează cele trei variabile exclusiv pe server sau în GitHub Actions. `.env.example` este doar un exemplu; aplicația nu încarcă automat fișiere `.env`.
3. Folosește endpoint-ul resursei `https://NUME.openai.azure.com` sau `https://NUME.services.ai.azure.com/openai/v1`. Endpoint-urile de proiect `/api/projects/...` și API-urile de modele necompatibile OpenAI nu sunt acceptate.

| Variabilă | Rol / implicit |
|---|---|
| `AZURE_OPENAI_ENDPOINT` | Endpoint HTTPS al resursei; opțional împreună cu celelalte două setări AI |
| `AZURE_OPENAI_API_KEY` | Secret server-side; recomandat prin referință Key Vault în App Service |
| `AZURE_OPENAI_DEPLOYMENT` | Deployment-ul chat |
| `AI_MAX_ARTICLES_PER_RUN` | Maximum articole noi procesate/rulare: `20`, interval `0–200`; `0` suspendă generările |
| `NEWS_UPDATE_MINUTES` | Pauza dintre colectările Web App: `15`, interval `5–120` minute |
| `NEWS_AUTO_UPDATE` | `1`; `0` dezactivează colectarea serverului |
| `NEWS_DATA_PATH` | `/home/mynews/news.json` în Azure; `.cache/news.json` local |

O singură cerere AI generează ambele limbi. Sunt trimise **numai titlul, extrasul RSS scurt, publicația și URL-ul**, niciodată textul integral. Extrasul este limitat la 45 de cuvinte / 280 de caractere; fără extras nu se generează un articol pornind doar de la titlu. Modelului i se cere să păstreze incertitudinile, să nu inventeze fapte și să ignore instrucțiunile din RSS.

Rezultatul este validat ca JSON cu ambele limbi, categorie permisă, titluri de maximum 180 de caractere și rezumate de maximum 100 de cuvinte / 1200 de caractere. Nu se acceptă un răspuns trunchiat sau filtrat. Sintezele sunt memorate cu amprenta intrării și versiunea promptului; se regenerează numai la modificarea intrării, promptului sau deployment-ului. Schimbarea deployment-ului invalidează sintezele anterioare până la regenerare.

Procesarea favorizează știrile cele mai noi și este limitată per rulare și la cinci minute pentru începerea cererilor AI (ultima cerere poate adăuga până la 45 de secunde); limita **nu garantează** procesarea întregului flux dacă ritmul de intrare o depășește. Restul articolelor rămân accesibile în limba originală, cu etichetă explicită. La prima eroare de transport/model procesarea AI se oprește pentru acea rulare, păstrează rezultatele deja reușite și raportează starea degradată; următoarea rulare reîncearcă. Configurația AI parțială sau invalidă oprește publicarea și păstrează ediția precedentă.

**Costuri:** la intervalul implicit, limita de 20 înseamnă aproximativ cel mult 1.920 de cereri/zi pentru un singur colector permanent, înainte de a ține cont de durata rulărilor și de cache. Nu există un plafon financiar implementat în aplicație. Configurează bugete/alerte Azure, limite de cotă și o limită per rulare potrivită înainte de activare. Nu activa simultan colectorul Pages și Web App pentru aceeași publicație fără să accepți costurile duble.

## Deploy în Azure Web App

Repository-ul include `infra/main.bicep`, varianta ARM JSON `infra/azuredeploy.json` pentru butonul **Deploy to Azure** și workflow-ul manual `.github/workflows/azure.yml`. **Butonul creează numai infrastructura Web App; codul aplicației se publică separat, la pasul 2.** Nu creează resurse sau deployment-uri de modele AI. Planul App Service B1 și inferența AI sunt servicii cu costuri.

### 1. Infrastructură

Apasă **Deploy to Azure**, alege abonamentul, grupul de resurse și regiunea, apoi completează `appName` cu un nume disponibil global. Lasă setările AI goale pentru modul RSS-only.

Alternativ, cu Azure CLI autentificat în abonamentul potrivit:

```sh
az login
az account set --subscription YOUR_SUBSCRIPTION_ID
az group create --name mynews-rg --location westeurope
az deployment group create \
  --resource-group mynews-rg \
  --template-file infra/main.bicep \
  --parameters appName=YOUR_GLOBALLY_UNIQUE_APP_NAME
```

Implicit creează numai Web App Linux Python 3.12, plan B1, HTTPS obligatoriu, TLS minimum 1.2, Always On și identitate gestionată. AI rămâne dezactivat. Numele aplicației trebuie să fie disponibil global.

În **App Service → Settings → Environment variables**, adaugă endpoint-ul, deployment-ul și cheia AI împreună. Preferă o referință `@Microsoft.KeyVault(SecretUri=https://YOUR_VAULT.vault.azure.net/secrets/YOUR_SECRET/)` pentru cheie și acordă identității aplicației rolul **Key Vault Secrets User**, cu acces de rețea la vault. Identitatea gestionată din template este pentru integrarea cu Key Vault; clientul AI din această versiune folosește cheia rezolvată de App Service, nu autentificare Entra directă.

Nu pune cheia în Bicep, fișiere de parametri, HTML sau argumente CLI salvate în istoricul shell-ului. Parametrul Bicep `aiApiKey` este securizat și poate primi o referință Key Vault. Redeploy-ul template-ului reaplică setările AI: transmite aceleași valori/referințe securizate sau reconfigurează-le după deploy.

După modificarea `infra/main.bicep`, regenerează șablonul folosit de buton cu `az bicep build --file infra/main.bicep --outfile infra/azuredeploy.json` și include ambele fișiere în commit.

### 2. Autentificare GitHub → Azure

Creează un environment GitHub **`azure-production`**, cu aprobări dacă dorești, și o identitate Entra cu credential federat OIDC:

```text
Issuer:   https://token.actions.githubusercontent.com
Subject:  repo:v-khdumi/myNews:environment:azure-production
Audience: api://AzureADTokenExchange
```

Acordă identității de deploy rolul **Website Contributor** pe Web App și setează variabilele environment-ului GitHub:

```text
AZURE_CLIENT_ID
AZURE_TENANT_ID
AZURE_SUBSCRIPTION_ID
AZURE_WEBAPP_NAME
```

Rulează workflow-ul **Deploy Azure Web App** din Actions. Rulează testele, creează un pachet cu doar fișierele necesare și îl publică prin OIDC, fără publish profile în repository. App Service instalează `requirements.txt` prin Oryx și pornește Gunicorn.

Pentru publicare manuală, după configurarea infrastructurii:

```sh
zip -r app.zip index.html styles.css theme.js app.mjs news-core.mjs i18n.mjs \
  favicon.svg data/news.json scripts server.py gunicorn.conf.py requirements.txt \
  -x '*/__pycache__/*'
az webapp deploy --resource-group mynews-rg \
  --name YOUR_GLOBALLY_UNIQUE_APP_NAME --src-path app.zip --type zip
```

### 3. Operare

- **O singură instanță și un singur worker Gunicorn**, cu patru thread-uri HTTP. Colectorul este un thread de fundal care lansează câte un proces izolat, cu timeout de 15 minute și publicare JSON atomică. Nu activa autoscaling sau mai mulți workeri: ar dubla colectarea și costurile și ar introduce concurență la scriere. Pentru scalare, extrage colectorul într-un job unic și mută edițiile în Blob Storage/bază de date.
- `/home/mynews/news.json` persistă între restarturi și deploy-uri App Service; directorul aplicației nu este folosit pentru date persistente. Nu este arhivă sau backup permanent.
- `GET /healthz`: liveness HTTP 200. Este endpoint-ul configurat pentru health check Azure; o întrerupere a publicațiilor nu trebuie să scoată portalul din trafic.
- `GET /readyz`: 200 numai dacă ultima ediție este recentă (maximum 90 minute), are surse reușite și ultima actualizare nu a eșuat; altfel 503. Monitorizează-l separat pentru alerte editoriale.
- `GET /api/news` și `GET /data/news.json`: aceeași ediție publică, `Cache-Control: no-store`; niciun endpoint public nu declanșează inferențe.
- Erorile RSS/AI și ieșirile procesului sunt în **App Service → Log stream**. La prima pornire sau dacă rețeaua nu permite RSS, portalul afișează starea reală, nu date de demonstrație.

## GitHub Pages rămâne disponibil

Workflow-ul existent publică la push pe `main`, manual și la minutele **07 și 37** ale fiecărei ore. În Settings → Pages selectează GitHub Actions. Programările pot întârzia și pot fi dezactivate de GitHub în repository-uri publice inactive; nu reprezintă un SLA.

Pentru AI pe Pages, configurează variabilele repository-ului `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, opțional `AI_MAX_ARTICLES_PER_RUN`, și secretul Actions `AZURE_OPENAI_API_KEY`. Cheia există numai în jobul colectorului, niciodată în fișierele publicate. Fără acestea, publicarea rămâne RSS-only. Cache-ul Actions păstrează ediția precedentă și sintezele, dar poate fi evacuat; nu este o bază de date.

## Drepturi, imagini și limite editoriale

Sintezele sunt **rezumate proprii atribuite**, nu „articole originale” garantate juridic și nu reportaje independente. AI poate greși; verificarea editorială și drepturile de utilizare rămân responsabilitatea operatorului. Un link la sursă și reformularea automată nu înlocuiesc licența sau permisiunea. Înainte de lansare comercială, verifică termenii fiecărei publicații, politicile de utilizare RSS/AI și drepturile asupra imaginilor.

Imaginile sunt referințe HTTPS din RSS (media, enclosure sau HTML RSS), încărcate direct de la publicație/CDN fără Referer. Nu se descarcă paginile integrale, nu se ocolesc paywall-uri și nu se stochează copii ale fotografiilor. Gazda imaginii poate vedea IP-ul vizitatorului. Când imaginea lipsește, portalul afișează un card tipografic, nu o fotografie fără legătură cu știrea; erorile de încărcare sunt semnalate.

Conținutul RSS/AI este afișat ca text, nu HTML. Serverul expune explicit doar fișierele publice și ediția JSON; codul, configurările și secretele nu sunt accesibile prin serverul Web App. Găzduirea statică cu `python -m http.server` este destinată numai dezvoltării locale.
