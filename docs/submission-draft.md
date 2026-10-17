# Štafeta: podklad pro odevzdání na Rakathon 2026 (KONCEPT)

Stav: **koncept k doplnění a schválení** (Adam). Tvrzení vycházejí jen z repozitáře (`README.md`, `docs/`, ADR,
`docs/HANDOFF.md`, kód na `main`). Co z repozitáře nelze doložit, je označeno `TODO(Adam):`. Všechna data jsou
smyšlená (fiktivní pacientka Alena Procházková). Název zadání: VZP „Cesta pacienta bez ztráty informací“ a téma
InterSystems IRIS for Health / FHIR R4.

TODO(Adam): název týmu, členové a role (P1–P4), kontakt, odkaz na repozitář, odkaz na video nebo živou ukázku.

## 1. Problém

Zadání VZP (`docs/challenge-brief.md`) popisuje tři místa, kde se informace o onkologickém pacientovi ztrácejí:

- **Vstup:** dokumentace přichází roztříštěně a lékaři údaje přepisují.
- **Uvnitř KOC:** koordinátorka hledá dokumenty; chybí společný pohled na stav, termíny a odpovědnost; podklad pro MDT
  přijde pozdě nebo neúplný.
- **Výstup:** odesílající lékař nevidí, zda byl pacient přijat, co chybí a co MDT rozhodlo; zdržení se špatně měří.

Kontext ze zadání: koordinátora zavedlo MZ ČR a platí ho VZP; KOC léčí zhruba 65 % pacientů a jsou přetížená. Doba do
léčby se skládá z T1 (symptom → diagnostika), T2 (diagnostika → MDT) a T3 (MDT → léčba).

## 2. Řešení

Štafeta je **sdílený onkologický případ**, který propojuje odesílajícího praktického lékaře (PL), koordinátorku KOC,
lékaře KOC a MDT. Přijme klinické dokumenty, vytěží z nich strukturovaný handover **s doslovným zdrojem u každé
hodnoty**, hlídá úkoly, vlastníky a termíny, připraví podklad pro MDT a uzavře smyčku zpět k PL s důkazem o předání.
V každém okamžiku je vidět, kde případ je, kdo je na tahu a dokdy.

AI jen připravuje návrh; rozhoduje a potvrzuje lékař. Aplikace je prototyp ověřující princip, ne zdravotnický prostředek
pro klinické rozhodování (v aplikaci je vždy patička „Prototyp – fiktivní data, neurčeno pro klinické rozhodování“).

## 3. Šest kroků ukázky

Podrobný scénář po kliknutích: [demo-script.md](demo-script.md).

1. **Žádost bez formuláře.** PL přetáhne žádost (DOCX), Štafeta předvyplní pacientku a suspektní diagnózu, PL zvolí
   KOC 2 a potvrdí souhlas. Případ je **Odesláno**, na tahu je koordinátorka.
2. **Triage a chybějící podklady.** Koordinátorka případ převezme (**V triage**). Aplikace z žádosti vyjmenuje
   odkazované výsledky, které nejsou přiložené (zprávy 01–06), s citací; koordinátorka je jedním krokem vyžádá
   (**Čeká na podklady**).
3. **Handover s důkazy.** Z nahraných zpráv vznikne 15 sekcí handoveru (Handover_obsah). U hodnot je zdroj a citace.
   Označeno je, co **chybí** (stav výkonnosti, TNM, e-mail), co si **odporuje** (datum posledního apixabanu vůči
   datu výkonu, datum odběru histologie vůči datu vydání) a co je **zastaralé** (váha). Lékař sekce potvrdí, upraví nebo
   ponechá jako chybějící.
4. **Koordinace a „kdo je na tahu“.** Spuštění sady „Karcinom pankreatu – diagnostika“ vytvoří úkoly (CT v KOC 1,
   EUS-FNB, odběry, histologie, algeziolog, psycholog, MDT) s vlastníkem, místem, termínem a závislostmi (termíny jsou
   demo předpoklad). Histologie slíbená do tří pracovních dnů je k 16. 10. po termínu a vznikne eskalace.
5. **Podklad pro MDT k 21. 10. 2026 08:00.** Do podkladu vstoupí jen dokumenty vyhotovené i přijaté do tohoto okamžiku;
   zprávy 12 a 13 jsou označeny **Po MDT** a nezahrnuty. Server vyhodnotí připravenost; chybějící položku může lékař
   KOC prominout s důvodem. Zápis se stáhne jako DOCX v rozložení MDT_zapis.
6. **Uzavření smyčky.** Lékař KOC zapíše podepsaný závěr MDT, koordinátorka ho odešle PL (e-mail v Mailpitu bez
   klinického obsahu, jen odkaz do portálu). PL závěr otevře v portálu; otevření se zapíše do auditní stopy. Případ se
   uzavře a měří se zástupné hodnoty T1, T2, T3.

## 4. Architektura

Rozhodnutí: [ADR-0001](adr/0001-iris-fhir-system-of-record.md) (IRIS FHIR jako zdroj pravdy),
[ADR-0002](adr/0002-evidence-locked-extraction.md) (extrakce zamčená důkazem), podrobně [architecture.md](architecture.md).

- **InterSystems IRIS for Health 2026.1** je úložiště FHIR R4 (zdroj pravdy pro klinické i workflow zdroje), běží i
  jako lokální záložní varianta (`make up-local`). V IRIS leží také tabulka `Stafeta.DocChunk` pro **vektorové
  vyhledávání** (`VECTOR(DOUBLE,384)`, index HNSW, iFind), nad níž je hybridní hledání (kosinová podobnost + fulltext,
  sloučení pořadí RRF); viz [vector-search.md](vector-search.md) a ADR-0004.
- **Backend:** Python 3.12, FastAPI, Pydantic v2; vnitřní doménový model (`backend/app/domain`) je oddělen od FHIR
  (`backend/app/fhir`); chyby jako RFC 7807 `problem+json`, texty česky.
- **AI:** OpenAI-kompatibilní rozhraní přes Azure APIM (EU data zone); odpovědi LLM se pro ukázku čtou z mezipaměti
  (`STAFETA_LLM_CACHE=1`).
- **Frontend:** React + TypeScript (strict), Vite, Tailwind, TanStack Query; klient generovaný z
  `contracts/openapi.json`.
- **Mailpit** jako demo schránka pro důkaz předání. Ukázkové prostředí: IRIS na Azure Container Instance, backend na
  Container Apps, frontend na Static Web Apps. TODO(Adam): ověřit, co z cloudového nasazení je ve finální ukázce
  skutečně nasazeno (README popisuje jen IRIS na ACI).

Tok dat: dokument → `DocumentReference` → extrakce faktů s důkazem → sestavení handoveru k časovému bodu `as_of` →
konzistenční kontroly → potvrzení lékařem (`Provenance`) → závěr MDT a zpětná vazba (`Communication`, `AuditEvent`).

## 5. Použité zdroje FHIR R4

Úplná tabulka: [fhir-mapping.md](fhir-mapping.md). Mapování je jen v `backend/app/fhir/mappers/`.

| Oblast | Zdroje FHIR |
| --- | --- |
| Pacient a adresář | `Patient`, `RelatedPerson`, `Coverage`, `Organization`, `Practitioner`, `PractitionerRole` |
| Případ a úkoly | `EpisodeOfCare` + koordinační `Task` (`businessStatus` = stav případu); kroky jako `Task`; vyžádání zpráv jako `Task` + `CommunicationRequest` |
| Plán | `PlanDefinition` (šablona sady) → `CarePlan` + `ServiceRequest` na krok; žádost PL jako `ServiceRequest` |
| Dokumenty | `DocumentReference` (`date` = přijato, `attachment.creation` = vyhotoveno, obsah v base64) |
| Handover a MDT | `Composition` (handover o 15 sekcích, MDT zápis); odvozené `Condition`, `MedicationStatement`, `Observation` |
| Důkaz, potvrzení | `Provenance` (extrakce s citací, potvrzení / úprava / ponechání jako chybějící, prominutí připravenosti, potvrzení předvyplnění PL) |
| Souhlas a zprávy | `Consent`, `Communication` / `CommunicationRequest` |
| Audit | `AuditEvent` při každém zápisu a čtení případu |

Použité kódové systémy: LOINC pro typy dokumentů a laboratoře, MKN-10 (ICD-10) pro diagnózy, ICD-O-3 pro morfologii;
vlastní systémy pod `https://stafeta.example/fhir/CodeSystem/<name>` jsou vypsané v dokumentu mapování. Profily CZ Core
a mCODE jsou cíl „kde je to praktické“, ne ověřená shoda: TODO(Adam): rozhodnout, zda se v odevzdání o shodě s profily
zmiňovat. Vlastní rozšíření nejsou nahrána do IRIS (viz poznámky v mapování).

## 6. Bezpečnost AI

Pravidla jsou závazná pro každý kód i text v repozitáři (`AGENTS.md`).

- **Důkaz u každé hodnoty.** Každá vytěžená hodnota nese `evidence: [{doc_id, quote}]`. Citace musí existovat
  v původním textu (po normalizaci mezer); jinak je hodnota **zamítnuta** (evidence lock, ADR-0002). Co zdroj neuvádí,
  má stav **chybí**; nic se nedomýšlí (například stav výkonnosti se z „soběstačná“ neodvozuje).
- **Lékař potvrzuje.** Výstup AI je návrh (**Návrh AI – čeká na potvrzení**), dokud ho lékař KOC nepotvrdí. Potvrzení,
  úprava i „ponecháno jako chybějící“ se zapisují jako `Provenance` (kdo, kdy, co se změnilo). Potvrzení je vázáno na
  otisk hodnoty, kterou lékař viděl; změněná sekce se znovu otevře. Chybějící položku připravenosti může prominout jen
  lékař KOC s důvodem.
- **Žádné klinické rady od AI.** AI cituje, strukturuje, shrnuje s citacemi a upozorňuje na nesoulady. Neodporučuje
  léčbu, dávky ani diagnózy. Texty jsou neutrální („v dokumentaci uvedeno…“, „nesoulad mezi…“, „chybí…“). Odpovědi na
  dotazy k případu (`POST /api/cases/{id}/ask`) jsou omezeny citací po větách.
- **Pravidlo `as_of`.** Handover obsahuje jen dokumenty vyhotovené i přijaté nejpozději k danému okamžiku (demo: začátek
  MDT 21. 10. 2026 08:00). Čas určuje server, frontend ho nepočítá.
- **Audit a soukromí.** Zápisy i čtení klinického obsahu vytvářejí `AuditEvent`; v logu nejsou osobní údaje; e-mail pro
  PL neobsahuje klinický text. Jen smyšlená data. Podrobně [security-privacy.md](security-privacy.md).

Měření extrakce na smyšlené sadě 13 zpráv (z `docs/extraction.md`, běh z mezipaměti): citace ověřitelné v 100 %
(476 citací), žádný fakt z dokumentů po MDT v podkladu, nalezeno 53 z 54 klíčových hodnot (98,2 %; v prvním živém běhu
před opravami zámku 51 z 54), stav polí handoveru shodný s očekávaným souborem u 15 z 15 polí. Jde o **jeden případ bez
nezávislé testovací sady**; pravidla byla laděna na týchž dokumentech, takže to není měření zobecnění.

TODO(Adam): znovu spustit `make eval` na aktuálním `main` a čísla před odevzdáním přepsat. Metriku „0 halucinací“
neuvádět jako bezpečnostní záruku (správnost jistoty se kontroluje pravidly a auditem, ne metrikou; viz
`docs/extraction.md`). Epikríza se zatím nahrává jen jako záložní verze (#45).

## 7. Známá omezení

Otevřené problémy jsou jen v GitHub issues; tady je výběr, který je třeba v odevzdání přiznat.

| Issue | Omezení |
| --- | --- |
| #16 | `GET /api/cases` nefiltruje podle účastníka případu: praktický lékař vidí všechny případy |
| #104, #105 | Pro revizního lékaře ZP 211 není vymezené API: seznam případů mu dává celá jména a data narození, T1–T3 chybí; obrazovka revizního lékaře běží na provizorním koncovém bodu |
| #111 | Neexistuje „kdo jsem“ (`GET /api/me`); hlavička aplikace zrcadlí jména demo uživatelů ručně |
| #113 | API neříká, zda PL závěr otevřel (je jen v auditu); obrazovka koordinátorky proto neuvádí, zda byl závěr přečten |
| #115 | Chybové hlášky `422` mají v poli `errors[].msg` anglický text Pydantic; několik výchozích hlášek zůstává anglicky |
| #116 | Kontrakt (`openapi.json`) ukazuje anglický příklad `problem+json` |
| #117 | Duplicitní větev `FhirConflictError` v `_fhir_status` (kosmetická chyba kódu) |

Dále, bez úplného výčtu (viz [known-issues.md](known-issues.md), issues #4, #8, #35, #74, #98, #102):

- **Přihlášení je simulované** (hlavička `X-Demo-Role` jen v demo režimu), žádné skutečné OIDC/SMART; vlastnictví úkolu se
  kontroluje podle role, ne podle osoby.
- **HL7 v2 → FHIR není implementováno** (#126; v `iris/` je jen definice plánu sady). TODO(Adam): rozhodnout, zda se HL7 v2
  v odevzdání uvádí jako plán.
- **Revizní lékař není při odeslání zpětné vazby automaticky informován** (#74); přehled pro pojišťovnu je omezený.
- Brána připravenosti čte uložený snímek handoveru, který může zastarat (#98), a je volnější než pravidlo „člověk
  ve smyčce“ (#102).
- Frontend: záložky Audit, Časová osa a Komunikace běží na provizorních koncových bodech (#47); nahrání zprávy v UI
  nepřiřadí zprávu k otevřenému požadavku, takže případ nepřejde do stavu **Kompletní** (#120, obejití v
  [demo-script.md](demo-script.md)); potvrzení sekcí handoveru se nepřenášejí mezi časovými body `as_of` (#122).
- Transakce IRIS pro žádost a koordinaci byly ověřeny hlavně mocky a offline validací; živý běh `pytest -m iris` na
  lokálním IRIS je v known-issues K11 a #99.
- Demo hodiny a role jsou přepínatelné kýmkoli v demo režimu (#55).
- Hodnoty T1, T2, T3 jsou zástupné (T1 = první návštěva PL → žádost do KOC, T2 = žádost → MDT, T3 = MDT →
  onkologické konzilium).

## 8. Jak spustit

Předpoklady: Docker, `uv`, Node s `pnpm`; soubor `.env` se zadává ručně (není v repozitáři).

```bash
# Záložní lokální varianta jedním příkazem (IRIS + bootstrap + seed + backend + kontrola zdraví):
mkdir -p .iris && printf '%s' 'libovolné-heslo' > .iris/password.txt
make up-local                     # SCENARIO=demo-start (výchozí): žádný případ, ukázka začíná krokem 1
# SCENARIO=story pro hotový případ se 13 dokumenty

cd frontend && pnpm install && pnpm dev     # http://localhost:5173
# Mailpit: http://localhost:8025, backend: http://localhost:8000/api/health
make check                        # lint, typy, testy (backend i frontend)
make eval                         # extrakce a konzistence proti data/golden (z mezipaměti)
```

Sdílený IRIS na Azure: `make iris-bootstrap`, `make seed`, `make up` (postup v `README.md`). Reset ukázky:
`make demo-reset` jen správce sloučení.

TODO(Adam): doplnit adresu nasazené verze, přihlašovací údaje k demu a případné omezení pro porotu.

## 9. Co ještě doplnit před odevzdáním

- TODO(Adam): úvodní věta a „elevator pitch“ (30 s).
- TODO(Adam): přínos pro VZP a pacienta vyjádřený jen měřitelnými zástupnými hodnotami (T1, T2, T3); bez tvrzení o
  skutečném zkrácení doby do léčby.
- TODO(Adam): plán po hackathonu (VZP deck: „Rakathon ověřuje princip, produkční integrace je další krok“).
- TODO(Adam): zkontrolovat před odevzdáním textem `clinical-safety-reviewer` (formulace, MDR hranice).
