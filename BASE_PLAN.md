# Rakathon 2026 – Cesta pacienta bez ztráty informací: analýza a plán

Oct 16, 2026 · @Adam

## Shrnutí

Stavíme **Štafetu**: sdílený onkologický případ ve FHIR na InterSystems IRIS for Health. Připravený k pilotu, ne jako jednorázové demo. Odevzdání je v sobotu 17. 10. ve 14:00 (náš cíl 13:30), zmrazení kódu v 11:30.

1. **Proti čemu stavíme.** Pacientka v datech čeká od první návštěvy PL do onkologického konzilia 64 dní, z toho 31 dní před vstupem do KOC. Data obsahují 16 nesouladů a mezer, včetně záměrně vložených, a dvě zprávy vzniklé po MDT. Porota je bude hledat.
2. **Co postavíme.** Šest demo kroků VZP: referování bez formuláře → triáž a vyžádání podkladů → handover s citacemi → úkoly s vlastníkem a termínem → zápis MDT k 21. 10. → závěr PL s doručenkou.
3. **V čem jsme jiní:**
   - **Evidence lock:** údaj bez doslovné citace se do handoveru nedostane.
   - **Detektor nesouladů** napříč zprávami.
   - **Časový řez „stav k datu“:** MDT dostane jen to, co bylo známo.
   - **Hodiny T1/T2/T3** ukazují, kde se ztrácí dny.
   - **Důkaz doručení** a minimální souhrn pro revizního lékaře.
4. **InterSystems a HL7.** FHIR R4 server je systém záznamu, Vector Search hledá důkazy a odpovídá na „Zeptej se případu“, MCP server nabízí agentický přístup. Stretch cílem je HL7 v2 laboratoř přes produkci v IRIS. Datový model vědomě navazuje na CZ Core, mCODE a IHE MHD.
5. **Důvěra a právo.**
   - AI jen připravuje návrh s citací, rozhoduje a potvrzuje lékař.
   - AI nic neradí klinicky, takže nástroj zůstává mimo zdravotnický prostředek.
   - Audit každého kroku.
   - Klinická data zůstávají u poskytovatele, VZP vidí jen procesní metriky.
6. **Jak to postavíme za 22 hodin.**
   - 4 role ve vlastních složkách, každý s 2–3 AI agenty paralelně.
   - Kontrakt nejdřív.
   - 26 připravených promptů, z toho 10 v PLAN režimu.
   - Noc ve dvou směnách a cloudoví agenti na připravených issues.
7. **Starter kit je hotový.** Obsahuje AGENTS.md, CLAUDE.md, 7 subagentů, 9 skillů, hooky, CI, šablony a golden set s ověřenými citacemi.

## 1. Analýza podkladů

Zadání je úzké a měřitelné. Jde o jeden případ (Alena Procházková, karcinom hlavy pankreatu), 13 zpráv, handover k MDT 21. 10. 2026 a odeslání závěru praktikovi. Data obsahují záměrné nesrovnalosti a dvě zprávy vzniklé až po MDT. Porota bude testovat právě tohle.

### 1.1 Co který podklad říká a co z něj plyne

| Podklad | Klíčový obsah | Co z toho plyne pro nás |
| --- | --- | --- |
| VZP – Cesta pacienta bez ztráty informací (13 slidů) | 4 kroky Převzít → Vytěžit → Koordinovat → Zpětná vazba. 8 stavů případu: Odesláno → V triage → Čeká na podklady → Kompletní → Připraveno k MDT → Závěr KOC/MDT → Zpětná vazba odeslána → Uzavřeno. Fronta nový / aktivní / odložený, „kdo je na tahu“, sada úkolů pro diagnózu, revizní lékař dostane info automaticky. Čas do léčby = T1 + T2 + T3. V poznámkách: „komunikační uzel ve VZP“. | Stavový automat a frontu stavíme 1:1 podle slidů. Každý krok má vlastníka a termín. T1–T3 měříme. Šest kroků dema ze slidu 12 je náš akceptační test. |
| Zadání úlohy (ZIP) | Šest schopností: převzít, vyžádat a shromáždit, vytěžit, koordinovat, připravit podklad pro MDT 21. 10., uzavřít smyčku a doložit doručení. Odevzdává se demo, zpráva k MDT dle MDT\_zapis a ukázka odeslání závěru PL. | Hodnotí se celý průchod. „Doložit doručení“ znamená potvrzení o doručení, ne jen odeslání. „Bez domýšlení“ znamená, že LLM nic nedoplňuje. |
| Handover\_obsah | 15 skupin údajů od nacionále po jiná sdělení včetně přání pacienta. Formu navrhují týmy. | Pevné JSON schéma: každá položka má hodnotu, zdroj, citaci, datum a stav (OK / chybí / nesouhlasí / zastaralé). |
| MDT\_zapis | Šablona: datum MDT, pacient (jméno, pojišťovna, telefon + e-mail, adresa, váha + výška), referující lékař (telefon + e-mail), členové MDT, diagnóza s kódem MKN-10, komorbidity, tabulka vyšetření, závěr, doporučení. | Výstup generujeme přímo do této šablony (DOCX + PDF). E-mail pacientky ani PL v dokumentaci není, aplikace ho musí označit jako chybějící. |
| MDT závěr (vzor) | Hotový zápis z 21. 10.: C25.0, hraničně resekabilní nález, neoadjuvantní chemoterapie, 6 doporučení, kopie PL. | Slouží jako „závěr“ v demu a jako kontrolní vzor. Sám obsahuje drobné nesoulady (tabulka 1.3). |
| Pacient – 13 zpráv (DOCX) | Kardiologie, laboratoř, RTG, 2× epikríza PL, gastroenterologie, UZ, CT, EUS-FNB, laboratoř KOC, histologie, algeziologie, psycholog. Různé formy od plných zpráv po tabulky. | Parser musí zachovat tabulky (laboratoř). Zprávy 12 a 13 vznikly po MDT. |
| Analýza cesty onkologického pacienta (ČVUT FBMI) | Pojmy: suspekce, histologie a staging, MDT, KOC/ROC. Principy koordinace: úkol, vlastník a termín, potvrzení převzetí („odeslaná žádanka ≠ objednané vyšetření“), výjimka a eskalace. Zpoždění léčby o 4 týdny zvyšuje mortalitu (Hanna, BMJ 2020). U karcinomu plic čeká 58–64 % pacientů na léčbu přes 6 týdnů. Extrakce: oprávněný vstup → výběr údajů → kontrola (zdroj, datum, nejistota) → audit. Testovací scénáře: ztracený výsledek, chyba extrakce (negace, starý termín). | Hotové akceptační scénáře a argumenty dopadu. Úkol potřebuje stavy objednáno → potvrzeno → provedeno → výsledek doručen. |
| HL7 – úvod pro Rakathon | FHIR R4; HL7 v2 a CDA jsou stále v provozu. Evropský Cancer Common (ECCDM 1.0.0-ballot) a mCODE STU4 4.0.0. České profily CZ Core 1.0 na hl7.cz/fhir. Doporučení: malý soubor údajů a zachovaný původ každého tvrzení AI. | Diagnóza a stadium podle mCODE, pacient podle CZ Core, ke každému AI údaji zdroj FHIR Provenance. |
| České eHealth v kostce (M. Opatřil) | Čtyři vrstvy: EU, centrální služby, výměnná vrstva AAfD, poskytovatelé. Platné právo 372/2011, 444/2024, 325/2021 + 236/2025. eŽádanka je stavový automat. IHE MHD (ITI-65/67/68), PDQm, mCSD, DSUBm, ATNA. Vzor MVP: klinické UI → procesní jádro → FHIR adaptér → HIE/API stub. Záměr „Národní onkologický průvodce“: suspekce → epizoda → podklady → MDT → plán → follow-up. | Architekturu stavíme přesně podle jeho vzoru MVP. eŽádanka a MHD jsou simulované stuby, seznam KOC je adresář ve stylu mCSD. Výhra: vstup na Národní dialog pro digitalizaci 19. 10. |
| Beyond the hackathon (HL7 Europe, PHOENIX, XiA) | „We store JSON“ neznamená interoperabilitu. Šest voleb: začít workflow, FHIR kontrakty, standardní kódové systémy, důvěra od prvního dne, testovat mimo demo, sdílet artefakty. | Do repa patří mapovací tabulka, příklady, validace instancí a zdokumentované předpoklady. Cíl: „další nemocnice řekne ano“. |
| Microsoft – průvodce pro týmy | Týmová resource group, APIM kompatibilní s OpenAI (`/openai/v1/chat/completions`, hlavička `api-key`). Modely gpt-6.1-sol (deployment `gpt-6-1-sol-dz-eu`), gpt-6-astra, gpt-6-luna, grok-4.7, DeepSeek-V4-Pro, Kimi-K2.7-Code, MAI-Thinking-1. Data jen pro výzvu VZP. Hosting: Static Web Apps, Functions, Container Apps. Klíč jen na backendu, pozor na 429. | Runtime AI aplikace jde přes APIM v EU Data Zone. Embedding model v seznamu není – ověřit u organizátorů, jinak lokální embeddingy. |
| Pravidla Rakathonu | 16.–18. 10. 2026, Praha / Brno / Ostrava. Kritéria: relevance, inovativnost, technická proveditelnost, zdravotní dopad, kvalita prototypu, práce s daty, uživatelská přívětivost, implementační potenciál, prezentace. Pořadatel dostává licenci k výstupům. Data jen k účelu výzvy, po akci smazat. | Pitch stavíme podél kritérií. Repo soukromé, data po akci smažeme. Licence třetích stran evidujeme. |

### 1.2 Pacientka v datech: kde se ztrácí čas

Od první návštěvy PL (1. 9.) k onkologickému konziliu (4. 11.) uplyne 64 dní. Nejdelší je úsek před KOC: 31 dní do žádosti PL (2. 10.), přestože první podezření na malignitu přišlo 29. 9. Úsek KOC → MDT trvá 19 dní (T2), MDT → konzilium 14 dní (T3). Pro srovnání: vzorový pan Novák ze slidu VZP šel od žloutenky k operaci za 21 dní.

&#91;embedded content: cesta pacientky ze 13 zpráv · vzorový případ ze slidu 4 VZP\]

Tenhle obrázek se hodí jako první slide pitche: T1 je nejdelší úsek a Štafeta ho zkracuje už při referování.

### 1.3 Nesoulady a mezery, které musí aplikace zachytit

| # | Typ | Co přesně | Zdroj | Reakce aplikace |
| --- | --- | --- | --- | --- |
| 1 | Nesoulad dat | EUS-FNB proběhla 12. 10., ale „poslední dávka apixabanu 18. 10. večer“ a „apixaban znovu od 21. 10.“ | 09 | Označit „nesouhlasí“, nepřebírat, úkol ověřit u endoskopie |
| 2 | Nesoulad dat | Histologie vydána 19. 10., ale „odběr 20. 10. 2026“; biopsie byla 12. 10. | 11 vs 09 | Totéž; do handoveru datum dle protokolu výkonu s varováním |
| 3 | Překročená lhůta | Protokol slibuje histologii „do 3 pracovních dnů“ (≈ 15. 10.), vydána 19. 10. | 09, 11 | Hlídač termínů by eskaloval 16. 10. |
| 4 | Chybí | PS / ECOG / Karnofsky nikde, jen „soběstačná“ | 07 | CHYBÍ → úkol pro lékaře KOC |
| 5 | Chybí | TNM (cT, cN) neuvedeno, CT dává jen popis | 08 | CHYBÍ, popis z CT převzít |
| 6 | Chybí | E-mail pacientky a PL, které MDT\_zapis vyžaduje | – | CHYBÍ → žádost o doplnění |
| 7 | Zastaralé | Výška jen z 20. 7.; poslední váha 65 kg z 15. 9. | 01, 05 | Uvést s datem a stářím údaje |
| 8 | Chybějící dokument | Kontrolní odběr u PL po ATB plánován na 9. 9., výsledek nedodán | 04 | Navrhnout vyžádání |
| 9 | Chybějící dokumenty | PL přiložil jen epikrízu, výsledky jsou „na jednotlivých pracovištích“ | 07 | Úkoly „vyžádat zprávu“ pro 01–06 |
| 10 | Časový řez | Zprávy 12 (26. 10.) a 13 (27. 10.) vznikly po MDT | 12, 13 | Vyloučit z handoveru k 21. 10., v časové ose „po MDT“ |
| 11 | Metadata | CT i algeziologie uvádějí jako indikujícího gastroenterologa, objednával koordinátor | 08, 12 | Informativně; v produkci to řeší eŽádanka |
| 12 | Ztracená informace | Souhlas se sdílením s dcerou je v žádosti PL z 2. 10., MDT závěr přesto píše „po jejím souhlasu“ | 07 vs MDT závěr | Souhlas jako strukturovaný údaj viditelný všem |
| 13 | Role | Konzilium k chemoterapii u MUDr. Kalouse, v MDT vedeného jako radiační onkolog | MDT závěr | Upozornit na kontrolu role, klinicky nehodnotit |
| 14 | Pojišťovna | ZP 211 je Zdravotní pojišťovna ministerstva vnitra, ne VZP | všechny | Revizní lékař ZP 211; řešení musí umět víc pojišťoven |
| 15 | Upřesnit | Otázka na MDT je obecná („stanovení dalšího postupu“) | 07 | Lékař otázku upřesní (např. resekabilita) |
| 16 | Nedoloženo | Biliární drenáž v dokumentaci není | – | Informativně |

### 1.4 Očekávaný handover k 21. 10. 2026 (golden set pro testy)

| Položka | Očekávaná hodnota | Zdroj | Stav |
| --- | --- | --- | --- |
| Nacionále | Alena Procházková, žena, 63 let (nar. 22. 7. 1963, RČ 635722/1013 – kontrolní součet sedí), ZP 211 | 04, 07 | OK |
| Kontakty | +420 777 000 541; dcera Petra Horká +420 777 000 542; e-mail chybí | 07 | Částečně |
| Diagnóza | C25.0 duktální adenokarcinom hlavy pankreatu G2–G3, perineurální invaze, MKN-O 8500/3; TNM chybí | 11, 07 | Částečně |
| Epikríza | Souhrn z 07 doplněný o CT, EUS-FNB, laboratoř a histologii | 07–11 | Generovat s citacemi |
| Otázka na MDT | Stanovení dalšího postupu po dokončení diagnostiky, urgentně | 07 | Upřesnit |
| Komorbidity | pFS (CHA₂DS₂-VASc 2, HAS-BLED 1) na apixabanu, AH, hypercholesterolémie, st. p. hysterektomii 2010, přechodně depresivní ladění 2019; EF LK 60 % | 01, 07 | OK |
| Léková anamnéza | apixaban 5 mg 1-0-1, bisoprolol 5 mg 1-0-0, perindopril 4 mg 1-0-0, rosuvastatin 10 mg 0-0-1, paracetamol 500 mg p. p. max 4× denně | 07 | OK, pauza apixabanu nesouhlasí |
| Alergie | neguje | 07 | OK |
| PS / Karnofsky | nikde, jen „soběstačná“ | 07 | CHYBÍ |
| Váha a výška | 165 cm (20. 7.); 69 kg (20. 7.) → 65 kg (15. 9.) | 01, 05 | Zastaralé |
| Symptomy | Od poloviny srpna bolest epigastria a pravého podžebří s propagací do zad; teploty do 38,6 °C se zimnicí; tmavá moč, subikterus, světlejší stolice; nechutenství, −4 kg za měsíc; úzkost, nespavost | 04, 05, 07 | OK |
| Vyšetření | 9 vyšetření od 20. 7. do 19. 10.: kardiologie, laboratoř, RTG, gastroenterologie, UZ, CT, EUS-FNB, laboratoř KOC, histologie | 01–11 | OK |
| Laboratoř + TM | 1. 9. a 15. 10.; CA 19-9 312 kU/l, CEA 4,1 µg/l, CA 125 48 kU/l; bilirubin 38 → 23 µmol/l, CRP 86 → 18 mg/l | 02, 10 | OK |
| Histologie | B-2026/15921: CK7+, CK19+, CK20−, CDX2−, SMAD4 zachována | 11 | OK, datum odběru nesouhlasí |
| Jiná sdělení | Informována o podezření; souhlas se sdílením s dcerou; výrazná úzkost (PL žádá psychologickou podporu); apixaban vysadit 48 h před invazivním výkonem; žije sama | 01, 07 | OK |

## 2. Koncept řešení: Štafeta

Stavíme „Štafetu“ (pracovní název): jeden sdílený onkologický případ ve FHIR, ve kterém má každý údaj zdroj a každý krok vlastníka a termín. AI připraví handover s citacemi, hlídá chybějící a nesouhlasící údaje i časový řez k datu MDT. Člověk vše potvrzuje. Název nese pointu: štafeta (případ) nesmí spadnout při předání a vždy je jasné, kdo ji drží.

### 2.1 Role a co v aplikaci dělají

| Role | Co dělá | Hlavní obrazovka |
| --- | --- | --- |
| Praktický lékař (referující) | Odešle pacienta jedním krokem: vybere KOC, nahraje epikrízu a zprávy, potvrdí souhlas. Vidí, zda byl pacient přijat, co chybí a jak MDT rozhodlo. Potvrdí převzetí závěru. | Portál PL „Moji pacienti v KOC“ |
| Koordinátor KOC | Triáž, vyžádání podkladů, plán kroků (CT v KOC 1, biopsie, odběry, algeziolog, psycholog), hlídání termínů, příprava MDT, odeslání závěru. | Pracovní fronta + detail případu |
| Lékař KOC | Validuje AI handover po sekcích, doplní ECOG, upřesní otázku na MDT, podepíše. | Validace handoveru |
| MDT (předsedající, členové) | Agenda jednání s připraveností případů, zápis závěru do šablony MDT\_zapis. | Režim MDT |
| Revizní lékař pojišťovny | Automaticky dostane strukturovaný minimální souhrn, může si vyžádat doplnění. | Souhrn jen pro čtení |
| Pacient (rozšíření) | Srozumitelný „další krok“, kontakt na koordinátora, s jeho souhlasem i pro dceru. | SMS nebo jednoduchá stránka |

### 2.2 Průchod demem (šest kroků ze slidu 12)

1. **Referování bez formuláře.** PL přetáhne epikrízu (zpráva 07). Aplikace předvyplní nacionále, suspektní diagnózu, kontakty a souhlas. PL jen vybere KOC 2 z adresáře a odešle. Stav: Odesláno.
2. **Triáž a vyžádání.** Koordinátor převezme případ (V triage). AI pozná, že výsledky 01–06 nejsou přiloženy, a navrhne úkoly „vyžádat zprávu“ s adresáty. Po nahrání: Čeká na podklady → Kompletní.
3. **Vytěžení s kontrolou úplnosti.** Handover má 15 položek a každá citaci. Červeně CHYBÍ (ECOG, TNM, e-mail), oranžově NESOUHLASÍ (data apixabanu, datum odběru), šedě ZASTARALÉ (váha). Lékař potvrzuje po sekcích, části jdou zkopírovat.
4. **Koordinace.** Koordinátor spustí sadu „Karcinom pankreatu – diagnostika“. Vzniknou úkoly CT (KOC 1), EUS-FNB, odběry s TM, histologie, algeziolog a psycholog s termínem, místem, vlastníkem a závislostmi. Tabule ukazuje, kdo je na tahu.
5. **Podklad pro MDT 21. 10.** Časový řez k 21. 10. sám vyloučí zprávy 12–13. Brána připravenosti pustí případ na MDT, až jsou povinné položky hotové nebo vědomě odpuštěné. Zápis se vygeneruje do šablony MDT\_zapis.
6. **Uzavření smyčky.** Závěr MDT odejde PL jako strukturovaná zpráva s původním kontextem a reviznímu lékaři ZP 211 jako minimální souhrn. Doručenka a potvrzení přečtení se zapíšou do auditní stopy. Stav: Uzavřeno.

### 2.3 Inovace: v čem je Štafeta jiná než očekávatelné řešení

| Očekávatelný přístup | Štafeta | Proč to porota ocení |
| --- | --- | --- |
| LLM shrne dokumenty do textu | Každý údaj = hodnota + doslovná citace + dokument + datum. Deterministický ověřovač odmítne údaj, jehož citace ve zdroji doslova není („evidence lock“). | „Bez domýšlení“ je měřitelné: 0 halucinací na golden setu. |
| Checklist chybějících polí | Detektor nesouladů napříč dokumenty: datumová logika, lhůty, metadata, ztracený souhlas, role. | Zachytí 16 nálezů z tabulky 1.3, včetně záměrně vložených. |
| V handoveru je vše, co systém zná | Časový řez „stav k datu“ (bitemporálně: kdy se to stalo × kdy jsme se to dozvěděli). | MDT dostane přesně to, co bylo známo. Audit jde zpětně zopakovat. |
| Seznam úkolů | Úkol = FHIR Task s vlastníkem, termínem, závislostmi a stavy objednáno → potvrzeno → provedeno → výsledek doručen. Při prodlení eskalace. | „Odeslaná žádanka ≠ objednané vyšetření“ (FBMI). |
| Statický dashboard | Hodiny T1 / T2 / T3 u každého případu a rozpad, kde se ztrácejí dny (organizační vs. klinické čekání). | Měřitelný dopad pro VZP; navazuje na důkaz o mortalitě. |
| Stav „odesláno“ | Doručenka, potvrzení přečtení referujícím lékařem, revizní lékař automaticky. | Smyčka je uzavřená s důkazem. |
| Vlastní JSON | FHIR R4 s profily mCODE a CZ Core, vstup HL7 v2 přes IRIS, API ve tvaru IHE MHD. | Další nemocnice se napojí bez přestavby. |
| Centrální databáze u pojišťovny | Klinická data zůstávají u poskytovatele, VZP vidí jen procesní metadata (časy a stavy) bez klinického obsahu. | Minimalizace dat, právně průchodnější cesta k pilotu. |

### 2.4 Mimo rozsah (vědomě)

- Klinická doporučení od AI (léčba, dávky). AI jen cituje dokumentaci a upozorňuje na nesoulad, což drží nástroj mimo zdravotnický prostředek.
- Skutečné napojení na eŽádanku, NIS nemocnic a SMS bránu. Místo nich stuby se stejným tvarem rozhraní.
- OCR naskenovaných zpráv. Podklady jsou DOCX, textové PDF zvládneme.

## 3. Architektura a tech stack

Páteří je InterSystems IRIS for Health. FHIR R4 server je zdroj pravdy, vektorové vyhledávání běží nad úseky dokumentů a HL7 v2 vstupuje přes produkci. Kolem něj je tenký Python backend s doménovou logikou a AI vrstvou a React frontend. Vrstvy kopírují doporučený vzor MVP z „České eHealth v kostce“. Stejný stack běží lokálně v Dockeru i v Azure.

&#91;embedded content: architektura Štafety · vrstvy a toky dat\]

Uživatelé pracují jen ve frontendu. Backend zapisuje vše přes FHIR adaptér do IRIS, AI vrstva volá model přes APIM a důkazy hledá ve Vector Search.

### 3.1 Vrstvy a technologie

| Vrstva | Co dělá | Technologie |
| --- | --- | --- |
| Klinické UI | Portál PL, fronta koordinátora, detail případu, handover, MDT, revizní lékař | React + TypeScript, Vite, Tailwind, shadcn/ui, TanStack Query, klient generovaný z OpenAPI |
| Procesní jádro | Stavové automaty případu a úkolů, sada kroků (pathway), brána připravenosti k MDT, časový řez, T1–T3 | Python 3.12, FastAPI, Pydantic v2 (`backend/app/domain`) |
| AI vrstva | Normalizace DOCX/PDF, extrakce faktů s evidence lock, sestavení handoveru, detektor nesouladů, „Zeptej se případu“ | APIM gpt-6.1-sol v EU Data Zone, structured outputs, cache odpovědí; embeddingy z APIM, nebo lokálně (fastembed, multilinguální MiniLM, 384 dimenzí) |
| FHIR adaptér | Mapování doména ↔ FHIR, transakční bundly, Provenance, AuditEvent | httpx, fhir.resources 8.x, inspirace CZ Core a mCODE |
| IRIS for Health | FHIR R4 server (JsonAdvSQL) jako zdroj pravdy; Vector Search (VECTOR + HNSW) nad úseky dokumentů; produkce HL7 v2 → SDA3 → FHIR; SQL analýzy času do léčby | irishealth-community v ACI (2 vCPU, 2 GB), lokálně stejný image |
| Výměna a stuby | Doručenky e-mailem, adresář KOC, eŽádanka a IHE MHD jako stuby, MCP server pro AI agenty | Mailpit, Organization/Endpoint ve stylu mCSD, FastMCP |

### 3.2 Případ ve FHIR

| Pojem | FHIR R4 | Klíčové prvky |
| --- | --- | --- |
| Pacient | Patient + RelatedPerson (dcera) + Coverage (ZP 211) | RČ jako identifikátor, kontakty |
| Žádost PL | ServiceRequest (urgent) | žadatel PL, cíl KOC 2, suspektní C25.0, přílohy |
| Případ | EpisodeOfCare + koordinační Task | `businessStatus` = jeden z 8 stavů, `owner` = kdo je na tahu |
| Krok cesty | Task (partOf případu) | vlastník, termín, místo, závislosti, stavy objednáno → potvrzeno → provedeno → výsledek doručen |
| Sada kroků | PlanDefinition → CarePlan | „Karcinom pankreatu – diagnostika“ s pořadím akcí |
| Zpráva | DocumentReference | `date` = přijato, `attachment.creation` = vytvořeno (bitemporálně bez vlastních tabulek) |
| Výsledky | Observation (LOINC), DiagnosticReport, Procedure, Condition (MKN-10, MKN-O) |  |
| Handover a zápis MDT | Composition | sekce dle Handover\_obsah a MDT\_zapis, `attester` = potvrzující lékař |
| Důkaz AI | Provenance | zdrojový dokument, doslovná citace, model, potvrzující lékař |
| Nesoulad | DetectedIssue | evidence → dokumenty, řešení |
| Souhlas | Consent | sdílení s dcerou |
| Komunikace | CommunicationRequest, Communication | žádosti o zprávy, závěr pro PL, `received` = doručenka |
| Audit | AuditEvent | každý zápis, čtení klinického obsahu, doručení a přečtení |

### 3.3 Proč právě takhle

- **Python v backendu.** Kit InterSystems, ovladač `intersystems-irispython`, LLM SDK i práce s DOCX jsou v Pythonu.
- **FHIR jako záznam, doména jako logika.** Splňuje doporučení „FHIR na okraji, oddělený interní model“ i kritérium InterSystems „technical coherence“.
- **Embeddingy mimo IRIS.** Kontejner má 2 GB RAM, kdyžto sentence-transformers uvnitř IRIS potřebuje víc. Do IRIS se ukládá jen vektor.
- **Cache LLM odpovědí.** Demo běží i bez sítě a při 429, CI je deterministické a šetří se rozpočet APIM.
- **Bez Next.js a Durable Functions.** Méně pohyblivých částí za 22 hodin.

### 3.4 Jak skórujeme u InterSystems

Ve výzvě „Best Use of InterSystems Technology for AI and Interoperability“ (1 500 EUR) se hodnotí Innovation, Real-world impact, Use of InterSystems technology a Technical coherence. Podívají se na FHIR Server, Vector Search a agentické komponenty. Pokrýváme všechny tři:

- **FHIR Server** je systém záznamu celého případu, nejen úložiště JSON.
- **Vector Search** slouží k vyhledání důkazů a k funkci „Zeptej se případu“ s citacemi.
- **Agentická vrstva** je MCP server, přes který „asistent přípravy MDT“ čte případ.
- **Interoperabilitu** přidává HL7 v2 produkce v IRIS (stretch cíl).

### 3.5 Klíčové balíčky

| Oblast | Balíčky (verze připnout ve F1) |
| --- | --- |
| Backend | fastapi, uvicorn, pydantic 2, pydantic-settings, httpx, intersystems-irispython 5.4.1, fhir.resources 8.x, python-docx, docxtpl, weasyprint, openai, tenacity, structlog, fastembed; stretch: hl7, fastmcp |
| Backend dev | uv, ruff, mypy, pytest, pytest-asyncio, respx |
| Frontend | react, typescript, vite, tailwindcss, shadcn/ui, @tanstack/react-query, router, zod, date-fns, openapi-typescript, openapi-fetch |
| Frontend testy | vitest, @testing-library/react, msw, @playwright/test, eslint, prettier |
| Nástroje | Docker Compose, pnpm, az CLI, gh CLI, Playwright MCP, Mailpit |

### 3.6 Omezení IRIS, na která narážel kit InterSystems

- Community edice má maximálně 8 spojení. Backend proto používá pool se 3 spojeními a vždy zavírá kurzor před spojením.
- Úložiště v ACI není trvalé. Po restartu spusťte `make iris-bootstrap && make seed`. Start a instalace FHIR trvají minuty, takže ACI spusťte hned.
- IRIS heslo z password file po načtení přejmenuje. Na read-only secret mountu v ACI to může selhat – ověřte hned ve F0, zálohou je lokální Docker.
- Kit ukládá text poznámek v DocumentReference jako hex, ne base64. Nekopírovat.
- Dotaz `Patient?name=Jméno Příjmení` vrátí 0 výsledků a neznámé parametry se tiše ignorují. Používejte `family` a `given`.
- FHIR Subscriptions v IRIS nejsou potvrzené. Nová data proto backend hlídá pollingem přes `_lastUpdated`.
- SMART on FHIR a OAuth2 vyžadují TLS. V PoC proto používáme mock role s JWT, v produkci OAuth2 se scopes.
- InterSystems AI Hub s nativním MCP je jen v EAP image. MCP server si proto děláme sami.

## 4. Bezpečnost, data a regulace

PoC běží jen na fiktivních datech a nesmí sloužit ke klinickému rozhodování. Produkční cesta má čtyři pilíře:

- **správce dat** je poskytovatel,
- **dodavatel** je zpracovatel se smlouvou podle čl. 28 GDPR,
- **DPIA** se zpracuje před pilotem,
- **AI zůstává mimo zdravotnický prostředek**, protože jen cituje a strukturuje.

Právní východiska vycházejí z přednášky FBMI (ověřeno 15. 10. 2026) a z „České eHealth v kostce“. Nejsme právníci; konkrétní model musí schválit poskytovatel s právníkem a pověřencem pro ochranu údajů.

### 4.1 Hackathon: pravidla teď

- **Jen fiktivní data.** IRIS v ACI má veřejné porty a běží přes HTTP bez TLS. Data jsou jen pro výzvu VZP a po akci se mažou.
- **Klíč k APIM** je jen na backendu v `.env`. Hook i deny pravidla zakazují AI agentům ho číst.
- **Patička v UI:** „Prototyp – fiktivní data, neurčeno pro klinické rozhodování“. Pravidla Rakathonu to výslovně říkají.
- **Licence:** pořadatel dostává licenci k výstupům. Komponenty třetích stran (např. MIT skilly z kitu InterSystems) evidujeme v README.

### 4.2 Právní rámec pro produkci

| Předpis | Co znamená pro Štafetu | Jak to řeší návrh |
| --- | --- | --- |
| Zákon 372/2011 Sb. (§ 45, 51, 65–66) | Dokumentace se předává pro návaznost péče ověřenému příjemci, v nutném rozsahu. Označení „koordinátor“ samo oprávnění nevytváří. | Matice rolí, účelů a oprávnění (4.4), každý přístup v AuditEvent |
| Vyhláška 444/2024 Sb. | Handover a zápis MDT jsou součástí zdravotnické dokumentace poskytovatele. | Composition s autorem a potvrzujícím lékařem, archivace u poskytovatele |
| GDPR čl. 5, 6, 9 odst. 2 h) a 3, 25, 28, 32, 35 | Zdravotní údaje pro péči zdravotníkem s mlčenlivostí; dodavatel je zpracovatel; DPIA bude pravděpodobně nutná. | Minimalizace (revizní lékař a VZP jen minimum), privacy by design, šifrování, retence, zpracovatelská smlouva, návrh DPIA |
| Zákon 325/2021 Sb. ve znění 236/2025 Sb., národní standardy (§ 38) | Budoucí napojení na eŽádanky, identifikaci a kmenové registry. Novela z roku 2026 je zatím jen návrh (elektronická dokumentace 2029, eŽádanky 2027/2028). | Stuby eŽádanky a MHD se stejným tvarem rozhraní, FHIR R4 podle NCEZ |
| EHDS, nařízení (EU) 2025/327 | V roce 2029 pacientský souhrn a eRecept, v roce 2031 laboratoř, obrazová vyšetření a propouštěcí zprávy. Sekundární využití jde přes HDAB. | Model kompatibilní s FHIR a EEHRxF; primární a sekundární data oddělená |
| MDR 2017/745, pravidlo 11 | Software s medicínským účelem (diagnóza, léčba) je zdravotnický prostředek. | AI jen cituje a strukturuje, žádná doporučení. Nesoulady jsou kontrola kvality dat, ne klinický úsudek. Rozhoduje člověk. |
| AI Act, nařízení (EU) 2024/1689 | Transparentnost: uživatel ví, že jde o AI. Režim vysoce rizikového systému by nastal jen s klinickým účelem. | Štítek „Návrh AI“, logování, dokumentace modelu a evalu, verze promptů |
| Zákon 48/1997 Sb. o veřejném zdravotním pojištění | Pojišťovna má přístup k údajům pro úhrady a revizní činnost, ne pro samotnou koordinaci. | VZP vidí procesní metriky, revizní lékař minimální souhrn |
| NIS2 a český zákon o kybernetické bezpečnosti | Nemocnice a pojišťovny mohou být regulované subjekty, dodavatel je částí dodavatelského řetězce. | Řízení přístupů, logování, šifrování, provoz v EU regionu, dodavatelská bezpečnost |

### 4.3 Bezpečnost: PoC vs. produkce

| Oblast | PoC (teď) | Produkce |
| --- | --- | --- |
| Identita | Mock login s rolemi, JWT | OIDC (Entra ID nebo národní identita), SMART on FHIR scopes v IRIS |
| Autorizace | RBAC v API, členství v případu | ABAC podle role, účelu a vztahu k pacientovi |
| Přenos | HTTP v ACI, jen fiktivní data | TLS všude, privátní síť, Web Gateway |
| Tajemství | `.env`, Container Apps secrets | Key Vault, rotace klíčů |
| Data | Neperzistentní IRIS | Licencovaný IRIS for Health, šifrování, zálohy, mirroring |
| AI | APIM v EU Data Zone, citace, ochrana proti prompt injection, cache | Smlouva zakazující trénink na datech, monitoring kvality, regresní eval v CI |
| Audit | AuditEvent pro zápisy, čtení a doručení | Export do SIEM, retence podle práva |

### 4.4 Kdo vidí co

| Role | Vidí | Nevidí |
| --- | --- | --- |
| Praktický lékař | Své referované pacienty, stav, co chybí, závěr MDT | Cizí pacienty |
| Koordinátor KOC | Případy svého KOC včetně dokumentů | Případy jiných KOC |
| Lékař KOC a MDT | Případy KOC, potvrzuje handover | – |
| Revizní lékař pojišťovny | Minimální souhrn: kód diagnózy, datum MDT, typ doporučené léčby, další termín | Volné texty, psychologii, bolest |
| VZP (analýzy) | Agregované časy a stavy | Klinický obsah a identitu |
| AI agent přes MCP | Čtení v rozsahu role uživatele | Zápis a odesílání |

## 5. Struktura projektu

Jedno monorepo, rozdělené tak, aby každý člen týmu (a jeho AI agent) vlastnil jinou složku. Konflikty pak vznikají jen ve sdílených kontraktech, které mění jeden člověk. Hvězdičkou jsou označeny soubory, které už jsou ve starter kitu.

```text
stafeta/
├─ AGENTS.md *                  # jediný zdroj pravidel pro všechny AI (Claude, Copilot, GPT)
├─ CLAUDE.md *                  # @AGENTS.md + specifika Claude Code
├─ README.md                    # jak spustit za 5 minut, demo scénář
├─ Makefile                     # make up / seed / test / eval / e2e / demo-reset
├─ docker-compose.yml *         # iris + backend + frontend + mailpit
├─ .env.example *               # APIM_*, IRIS_*, žádné skutečné klíče
├─ .mcp.json *                  # Playwright MCP
├─ .claude/
│  ├─ settings.json *            # oprávnění, hooky (formátování, ochrana souborů)
│  ├─ hooks/ *                   # protect-files.sh, format.sh
│  ├─ agents/ *                  # 7 subagentů (kapitola 9)
│  ├─ skills/ *                  # 5 projektových skillů (kapitola 9)
│  └─ rules/ *                   # pravidla s paths: backend, frontend, fhir
├─ .github/
│  ├─ copilot-instructions.md *  # odkaz na AGENTS.md + specifika Copilota
│  ├─ instructions/ *            # *.instructions.md s applyTo pro backend/frontend/iris
│  ├─ prompts/ *                 # opakované prompty (nový endpoint, FHIR mapování, E2E test)
│  ├─ workflows/ci.yml *         # lint, typy, testy, kontrakt, eval
│  ├─ pull_request_template.md *
│  └─ CODEOWNERS *
├─ contracts/                   # SDÍLENÉ, mění jen vlastník architektury
│  ├─ openapi.json               # generuje backend, frontend z něj generuje typy
│  ├─ handover.schema.json       # JSON Schema handoveru (15 položek + evidence)
│  └─ case-states.md             # stavový automat případu a úkolu
├─ data/
│  ├─ raw/                       # 13 zpráv + šablony (fiktivní, jen pro výzvu VZP)
│  └─ golden/ *                  # očekávaný handover a nálezy pro eval
├─ iris/
│  ├─ src/Stafeta/               # ObjectScript: Setup, produkce HL7 v2 → FHIR, DTL
│  ├─ fhir/                      # PlanDefinition (sada kroků), CodeSystem stavů, adresář KOC
│  └─ hl7v2/samples/             # ORU^R01 (laboratoř), MDM^T02 (dokument)
├─ backend/
│  ├─ pyproject.toml             # uv, ruff, mypy, pytest
│  ├─ app/
│  │  ├─ api/                    # FastAPI routery: referrals, cases, tasks, handover, mdt, feedback, audit
│  │  ├─ domain/                 # interní model (Pydantic), stavové automaty, pravidla
│  │  ├─ documents/              # DOCX/PDF → text se zachovanými tabulkami, chunking
│  │  ├─ extraction/             # LLM extrakce, evidence lock, schémata, prompty modelu
│  │  ├─ consistency/            # detektor nesouladů a mezer (pravidla + LLM)
│  │  ├─ timeline/               # časový řez as-of, T1/T2/T3
│  │  ├─ fhir/                   # adaptér: mapování doména ↔ FHIR, klient IRIS, validace
│  │  ├─ iris/                   # vector search, SQL analýzy (intersystems-irispython)
│  │  ├─ outputs/                # MDT zápis DOCX/PDF, zpráva pro PL a revizního lékaře
│  │  ├─ notify/                 # e-mail (Mailpit), doručenky, Communication
│  │  └─ security/               # role, JWT, audit (AuditEvent)
│  └─ tests/                     # unit, integrační (IRIS v Dockeru), eval
├─ frontend/
│  ├─ src/
│  │  ├─ features/               # referral, inbox, case, handover, coordination, mdt, feedback, timeline
│  │  ├─ components/ui/          # shadcn/ui
│  │  ├─ lib/api/                # generovaný klient z openapi.json
│  │  └─ mocks/                  # MSW, aby frontend běžel bez backendu
│  └─ e2e/                       # Playwright: celý demo průchod + video
├─ scripts/
│  ├─ aci_up.sh * / aci_down.sh *  # IRIS v Azure Container Instances
│  ├─ bootstrap_iris.py          # idempotentní: namespace, FHIR server, tabulky
│  └─ seed_case.py               # nahraje případ, úkoly, adresář KOC
├─ prompts/ *                   # fázové prompty z tohoto dokumentu (F0–F5)
└─ docs/
   ├─ architecture.md, fhir-mapping.md, data-dictionary.md
   ├─ adr/                       # krátké záznamy rozhodnutí (ADR-001 …)
   ├─ security-privacy.md        # matice rolí, účelů, oprávnění, DPIA návrh
   └─ demo-script.md, pitch/
```

**Konvence, které šetří čas:**

- **Kontrakt nejdřív.** Backend publikuje `contracts/openapi.json`, frontend z něj generuje typy a do té doby jede na MSW mockech. CI hlásí, když kontrakt neodpovídá kódu.
- **Vlastnictví složek** je v `CODEOWNERS`. Do cizí složky se sahá jen přes PR s review vlastníka.
- **Kód a identifikátory anglicky, UI a klinické pojmy česky.** Všechny texty UI v jednom souboru `frontend/src/i18n/cs.ts`.
- **Data:** repo zůstává soukromé, `data/raw` smažeme po akci dle pravidel. Do Azure jdou jen fiktivní data.
- **Žádné klíče v repu.** `.env` je v `.gitignore` a hook zakáže AI agentům ho upravovat.

## 6. Plán fází a prompty

Od pátku 16:00 do soboty 14:00 zbývá 22 hodin. Dělíme je do šesti fází se čtyřmi branami. Funkce se zmrazí v 8:00 a kód v 11:30, odevzdáváme nejpozději ve 13:30. Plné znění všech promptů je v záložce „Prompty“ a ve složce `prompts/` starter kitu. Prompty jsou anglicky, hlavička každého říká kdo, kdy, který model a režim.

Všechny prompty v plném znění: Prompty

&#91;embedded content: plán týmu · pá 16. 10. 16:00 – so 17. 10. 14:00\]

P1 a P2 tvoří noční směnu „sova“ a spí od 4:00 do 8:00. P3 a P4 jsou „skřivan“ a spí od půlnoci do 4:00. Cloudoví agenti mezitím pracují na připravených issues.

### 6.1 Fáze, brány a prompty

| Fáze | Čas | Kdo | Prompt | Režim | Model |
| --- | --- | --- | --- | --- | --- |
| F0 Setup | pá 16:00–16:45 | P1 | F0-environment-check | normální | jakýkoli |
| F1 Základ backendu | 16:45–20:00 | P1 | F1-1-foundation-backend | **PLAN** | Opus 5.5 xhigh + advisor Fable |
| F1 Frontend shell | 16:45–20:00 | P3 | F1-2-frontend-shell | **PLAN** | Sonnet 5.5 + frontend-design |
| F1 Jádro extrakce | 16:45–20:00 | P2 | F1-3-extraction-core | **PLAN** | Opus, pokud je, jinak Sonnet |
| F1 Doména a workflow | 16:45–20:00 | P4 | F1-4-workflow-domain | **PLAN** | Sonnet / GPT-6.1 Sol |
| **Brána G1** | **20:00** |  | `make up && make iris-bootstrap && make seed` běží, GET /api/cases vrací případ, frontend shell běží na mocích |  |  |
| F2 Referování a triáž | 20:00–24:00 | P4 | F2-1-referral-triage | normální | Sonnet / Sol |
| F2 Sestavení handoveru | 20:00–24:00 | P2 | F2-2-handover-assembly | **PLAN** | Opus / Sonnet |
| F2 UI kroky 1–4 | 20:00–24:00 | P3 | F2-3-ui-wiring | normální | Sonnet / Sol |
| F2 Koordinace a úkoly | 20:00–24:00 | P4 nebo cloud agent | F2-4-coordination | normální | Sonnet / Sol |
| F2 Vector search | 20:00–24:00 | P1 | F2-5-vector-search | **PLAN** | Opus |
| **Brána G2** | **24:00** |  | Kroky dema 1–4 projdou end-to-end, bez lesku |  |  |
| F3 Detektor nesouladů | 00:00–04:00 | P2 | F3-1-consistency-detector | **PLAN** | Opus |
| F3 Časový řez a T1–T3 | 00:00–08:00 | P1 (BE), P3 (UI) | F3-2-asof-timeline | normální | Sonnet |
| F3 Výstupy MDT | 04:00–08:00 | P4 | F3-3-mdt-outputs | normální | Sonnet / Sol |
| F3 Uzavření smyčky | 04:00–08:00 | P4 + P3 | F3-4-closed-loop | normální | Sonnet |
| F3 HL7 v2 v IRIS (stretch, 2 h) | 00:00–04:00 | P1 | F3-5-hl7v2-iris-production | **PLAN** | Opus + subagent iris-integration |
| F3 MCP agent (stretch, 90 min) | 00:00–04:00 | P1 nebo P2 | F3-6-mcp-agent | normální | Sonnet |
| **Brána G3** | **08:00** |  | Zmrazení funkcí: kroky 5–6, nesoulady, časový řez, T1–T3 |  |  |
| F4 E2E test a video | 08:00–10:30 | P4 | F4-1-e2e-demo | normální | Sonnet + test-engineer |
| F4 Revizní sweep | 08:00–09:30 | P1 | F4-2-review-sweep | normální | Opus (řídí subagenty) |
| F4 Nasazení | 08:00–10:30 | P1 | F4-3-deploy | **PLAN** | Opus |
| F4 UX polish | 08:00–11:00 | P3 | F4-4-ux-polish | normální | Sonnet + frontend-design |
| **Zmrazení kódu** | **11:30** |  | Jen opravy blokující demo (X-4) |  |  |
| F5 Pitch | 10:30–13:00 | P4 + všichni | F5-1-pitch | normální | Claude |
| F5 Dokumentace k odevzdání | 11:30–13:00 | P1 nebo P2 | F5-2-submission-docs | normální | Sonnet / GPT-6 Luna |
| **Odevzdání** | **so 13:30** |  | Rezerva 30 minut před deadlinem 14:00 |  |  |

Kdykoli během noci použijte X-1 (issue pro cloud agenta) a X-2 (merge konflikt). Při střídání směn je X-3 (převzetí směny), po zmrazení kódu X-4 (oprava, která blokuje demo).

### 6.2 Co jde do PLAN režimu

PLAN použijte, když změna překračuje jeden modul, sahá na kontrakt nebo datový model, nebo když není jasný postup. To jsou F1-1 až F1-4, F2-2, F2-5, F3-1, F3-5, F4-3 a X-3. Ostatní prompty jsou ohraničené a mají akceptační kritéria, takže běží v normálním režimu.

1. Vložte prompt v plánovacím režimu (`Shift+Tab` dvakrát, nebo `/plan`).
2. Zkontrolujte, že plán vyjmenovává soubory, dotčené kontrakty a testy. Přes `Ctrl+G` ho můžete upravit v editoru.
3. Schvalte variantou „Yes, manually approve edits“ u rizikových změn, nebo „Yes, and use auto mode“ u ohraničených.

### 6.3 Rozsah: co musí být, co zapůsobí, co se škrtá

- **Musí být (demo krok 1–6):** referování bez formuláře, triáž s vyžádáním podkladů, handover s citacemi, úkoly s vlastníkem a termínem, zápis MDT k 21. 10., odeslání PL s doručenkou.
- **Zapůsobí (bez toho nevyhrajeme):** evidence lock, zachycení nesouladů včetně záměrně vložených, časový řez, hodiny T1–T3, důkaz doručení, vector search v IRIS.
- **Stretch:** HL7 v2 produkce v IRIS, MCP agent, UI pro „Zeptej se případu“, nasazení backendu a frontendu do Azure, analýzy přes FHIR SQL Builder, hybridní vyhledávání.
- **Pořadí škrtání při skluzu:**
  1. MCP agent.
  2. HL7 produkce nahrazená Python fallbackem.
  3. Nasazení do Azure nahrazené laptopem proti ACI.
  4. UI „Zeptej se případu“.
  5. Pohled revizního lékaře – zbude jen e-mail.

## 7. Workflow týmu 4 lidí

Základ řídí jeden člověk, ale jen do 18:30. Už od 16:45 běží čtyři paralelní proudy v oddělených složkách. Každý člověk má jednoho interaktivního agenta a jednoho až dva agenty na pozadí. Noc pokrývají dvě směny po dvou lidech a cloudoví agenti, kteří během spánku otevírají PR podle připravených issues.

### 7.1 Role

| Role | Vlastní složky | Hlavní AI nástroj | Náplň |
| --- | --- | --- | --- |
| P1 Architekt a platforma | `contracts/`, `iris/`, `scripts/`, `backend/app/fhir` a `iris`, infra | Claude Code Opus 5.5 (xhigh) + advisor Fable | Základ, IRIS a FHIR, vector search, HL7 v2, nasazení, merge captain, schvaluje kontrakty |
| P2 AI a data | `documents`, `extraction`, `consistency`, `timeline`, `data/golden` | Claude Code (Opus, když je k dispozici, jinak Sonnet) + Copilot GPT-6.1 Sol | Extrakce s evidence lock, handover, detektor nesouladů, eval |
| P3 Frontend a UX | `frontend/` kromě `e2e/` | Claude Code Sonnet + frontend-design, Copilot Sol ve VS Code | Obrazovky, design systém, čeština, přístupnost |
| P4 Workflow, QA a pitch | `domain`, `api`, `outputs`, `notify`, `security`, `frontend/e2e` | Claude Code Sonnet + Copilot, Playwright | Stavové automaty, úkoly, výstupy MDT, doručenky, E2E test, demo, pitch |

Adam s praxí ve webu a v Playwright testech se hodí na P4, případně na P3. P4 zároveň prezentuje, proto spí v první směně.

### 7.2 Jeden člověk, tři agenti

1. **Popředí:** interaktivní Claude Code nebo Copilot agent mode na hlavním úkolu. Začíná v PLAN režimu, vy schvalujete.
2. **Pozadí lokálně:** druhý agent ve vlastním worktree (`claude -w <nazev>` nebo VS Code Agents → New Worktree) na menším úkolu, třeba testy, mapper nebo komponentu.
3. **Cloud:** Copilot cloud agent přes issue (jeden úkol, jeden PR, maximálně 59 minut) nebo subagent s `isolation: worktree`.
4. **Pravidla:** nikdy dva agenti ve stejné složce najednou. Každý úkol má issue s polem „Allowed files“. PR od Copilota schvaluje jiný člověk, protože schválení toho, kdo úkol zadal, se nepočítá.
5. **Hlídání kontextu:** jedna úloha na jednu relaci, mezi úlohami `/clear`. Na konci relace přibude zápis do `docs/HANDOFF.md`, který si další relace načte hookem.

### 7.3 Rytmus

- **Stand-up 10 minut** v 18:30, 20:00, 24:00, 04:00, 08:00 a 11:30. Agenda: co je v `main`, co blokuje, změny kontraktů, rizika pro demo.
- **Na každé bráně** se spouští `make e2e` (smoke). Kdo rozbije `main`, opraví ho přednostně.
- **Kontrakty** (`contracts/`) mění jen P1 s ADR a oznámením v týmovém chatu. Ostatní to hook blokuje.
- **Merge captain** merguje do `main` postupně, aby se rebase dělal po jednom. Ve dne je to P1, v noci ten, kdo je vzhůru.
- **Chat** má tři vlákna: #merge (kdo merguje co), #blokery, #demo.

### 7.4 Noc: dvě směny a cloudoví agenti

| Čas | P1 | P2 | P3 | P4 | Cloud agenti |
| --- | --- | --- | --- | --- | --- |
| 20:00–24:00 | práce | práce | práce | práce | dle potřeby |
| 24:00–04:00 | práce („sova“) | práce („sova“) | spánek | spánek | issues od P3 a P4: UI komponenty na moccích, E2E kroky, testy |
| 04:00–08:00 | spánek | spánek | práce („skřivan“) | práce („skřivan“) | issues od P1 a P2: testy pravidel, eval fixtures, dokumentace, ukázky FHIR |
| 08:00–14:00 | práce | práce | práce | práce, prezentuje | – |

Před spánkem má každý 20 minut na přípravu:

1. Napíše 3–5 issues podle šablony X-1 a přiřadí je Copilot cloud agentovi. Na delší samostatné úkoly volte GPT-6 Astra, na běžné GPT-6.1 Sol.
2. Zapíše handoff do `docs/HANDOFF.md`.
3. Předá „merge captain“ tomu, kdo zůstává vzhůru.

Ranní směna začíná promptem X-3 a pak projde noční PR (Copilot code review + člověk).

### 7.5 Rozpočty a limity

- **Claude Pro** má limity: rutinu dělejte v Copilotu, Sonnet nechte na cílené úkoly a Opus jen na F1 a těžké části. Kdo narazí na limit, přepne na Copilot GPT-6.1 Sol.
- **Copilot** používá kredity. GPT-6.1 Sol stojí 2 / 10 USD za 1 M tokenů (vstup / výstup), GPT-6 Astra 10 / 50 USD, GPT-6 Luna 0,10 / 0,50 USD. Astra jen na noční dlouhé úkoly, Luna na drobnosti.
- **APIM** (běh aplikace): krátké prompty, cache odpovědí a žádné smyčky opakování při chybě 429.
- **ACI s IRIS** běží celý hackathon, po pitchi ho smažte (`./scripts/aci_down.sh delete`).

## 8. Git: větve, commity, PR a konflikty

Používáme trunk-based vývoj s krátkými větvemi, squash merge, malé PR a jednoho merge captaina. Konfliktům předcházíme vlastnictvím složek a kontraktem, ne jejich řešením. Merge queue pro privátní repo mimo GitHub Enterprise Cloud není, její roli proto hraje merge captain.

### 8.1 Pravidla

| Oblast | Pravidlo |
| --- | --- |
| `main` | Ruleset: PR povinný, CI zelené (backend + frontend), blokace force push, lineární historie, jen squash merge, „Automatically request Copilot code review“. Auto-merge povolit. |
| Větve | `<oblast>/<popis>`, oblasti `be`, `fe`, `ai`, `wf`, `iris`, `qa`, `infra`, `docs`. Claude worktrees vytvářejí `worktree-<nazev>`, Copilot `copilot/*`. |
| Commity | Conventional Commits, např. `feat(extraction): add evidence lock`. Claude Code přidá trailer `Co-Authored-By`. |
| PR | Pod 400 změněných řádků bez generovaných souborů, vyplněná šablona, u UI screenshot. Před otevřením lokálně `/code-review`. |
| Review | Automaticky Copilot code review, pak člověk podle CODEOWNERS. PR od Copilota schvaluje někdo jiný než zadavatel. |
| Životnost větve | Merge do 2–3 hodin od začátku. Dlouhé větve jsou zakázané. |
| Push | `git push --force-with-lease` jen na vlastní větev, dělá ho člověk. Agentům je force push a push do `main` zakázaný v `.claude/settings.json`. |

### 8.2 Jak konfliktům předcházíme

1. **Vlastnictví složek.** CODEOWNERS plus pole „Allowed files“ v každém issue. Dva agenti nikdy nepracují ve stejné složce najednou.
2. **Kontrakt nejdřív.** `contracts/openapi.json` a `handover.schema.json` vlastní P1. Frontend do té doby jede na MSW mocích a typy si generuje.
3. **Generované soubory se neslučují ručně.** Platí pro `openapi.json`, `schema.d.ts`, `uv.lock` a `pnpm-lock.yaml`: vezme se verze z `main` a přegeneruje se.
4. **Žádné sdílené seznamy.** Routery v backendu, routy ve frontendu a české texty se registrují po featurách (auto-discovery, `i18n/cs/<feature>.ts`). Nová funkce tak přidá soubor, místo aby editovala centrální seznam.
5. **Častý rebase.** Před PR i během dlouhé práce `git fetch && git rebase origin/main`.
6. **Po každém merge** běží na `main` CI a smoke E2E.

### 8.3 Když konflikt přece nastane

```bash
git fetch origin && git rebase origin/main
# konflikt → nechte Claude Code postupovat podle prompts/X-2-merge-conflict.md
claude "Resolve the current rebase conflicts following prompts/X-2-merge-conflict.md"
git rebase --continue
make check
git push --force-with-lease
```

Pozor na přehození významu při rebase: „ours“ je `main` a „theirs“ je váš commit. Prompt X-2 to řeší a před `git add` ukáže tabulku soubor · typ · řešení.

## 9. Instrukce pro AI: CLAUDE.md, AGENTS.md, skilly, subagenti, hooky

Všechny modely sdílejí jednu sadu pravidel v `AGENTS.md`. Claude ji importuje z `CLAUDE.md`, Copilot ji čte přímo. Skilly ve složce `.claude/skills/` čte Claude Code i Copilot. Tvrdá pravidla vynucují hooky a oprávnění, ne text. Všechno níže je hotové ve starter kitu.

### 9.1 Soubory a kdo je čte

| Soubor | Čte | Obsah |
| --- | --- | --- |
| `AGENTS.md` | Claude (přes import), Copilot ve VS Code, cloud agent i CLI | Mise, 7 nepřekročitelných pravidel, architektura, příkazy, vlastnictví, konvence, FHIR, definice hotovo, git |
| `CLAUDE.md` | Claude Code | `@AGENTS.md`, plan mode, worktrees, tabulka subagentů, skilly, styl výstupu, handoff |
| `.claude/rules/*.md` | Claude Code | Pravidla pro backend, frontend a FHIR, načtená jen při práci v dané složce (`paths`) |
| `.github/copilot-instructions.md`, `.github/instructions/*.instructions.md` | Copilot | Odkaz na AGENTS.md a zkrácená pravidla podle cest (`applyTo`) |
| `.claude/skills/*/SKILL.md` | Claude Code i Copilot | 5 vlastních skillů a 4 z kitu InterSystems |
| `.claude/agents/*.md` | Claude Code; VS Code je umí načíst taky | 7 subagentů |
| `.claude/settings.json` + `.claude/hooks/` | Claude Code | Oprávnění, ochrana souborů, formátování, handoff při startu |
| `.vscode/settings.json`, `.vscode/mcp.json` | Copilot ve VS Code | Čte AGENTS.md, CLAUDE.md ne (pravidla se tak nenačtou dvakrát); auto-approve bezpečných příkazů; Playwright MCP |
| `.mcp.json` | Claude Code | Playwright MCP |
| `.github/workflows/copilot-setup-steps.yml` | Copilot cloud agent | Připraví uv, pnpm a Playwright před nočními úkoly |

### 9.2 Subagenti

| Subagent | Model | Kdy ho volat |
| --- | --- | --- |
| `fhir-architect` | opus | Návrh a review FHIR mapování, profily, bundly, selhání validace |
| `iris-integration` | opus | Bootstrap IRIS, ObjectScript, HL7 v2 produkce, vektorové SQL, problémy s pamětí |
| `extraction-auditor` | opus | Po každé změně extrakce. Nezávisle kontroluje halucinace, negace, data a jednotky. |
| `clinical-safety-reviewer` | opus | Před merge PR s prompty, AI texty nebo klinickými texty v UI. Hlídá hranici MDR, as-of a člověka ve smyčce. |
| `security-privacy-reviewer` | sonnet | Auth, API, logy, upload, infra; jednou před demem |
| `test-engineer` | sonnet | pytest, vitest a Playwright testy hotových funkcí |
| `ux-reviewer` | sonnet + Playwright MCP | Screenshoty obrazovek a top 5 problémů pro klinické uživatele |

Kdo má Pro účet bez Opusu, přepne si u sebe `model: opus` na `sonnet`. Nejvíc ušetří paralelní revizní sweep (F4-2). Pomáhá i to, že auditor kód nepsal, a tedy nehodnotí sám sebe. Výchozí limit je 20 současně běžících subagentů, pro testy na pozadí se hodí `isolation: worktree`.

### 9.3 Skilly

| Skill | K čemu |
| --- | --- |
| `fhir-iris` | Endpointy, autentizace, mapování případu, vzory dotazů a omezení IRIS |
| `czech-clinical-docs` | Zkratky OA/FA/AA, RČ a jeho kontrola, kódy pojišťoven, česká data a jednotky, negace, LOINC typy zpráv |
| `extraction-eval` | Golden set, metriky a tvrdé brány (100 % platných citací, 0 halucinací) |
| `demo-flow` | 6 kroků dema, reset, záložní plány |
| `hl7v2-iris` | HL7 v2 → FHIR v IRIS, ukázková zpráva ORU^R01 |
| `kit-iris-fhir`, `kit-iris-sql-python`, `kit-iris-vector-search`, `kit-iris-environment` | Obecné návody z kitu InterSystems (MIT) |

Dál si každý nainstaluje oficiální plugin `frontend-design` z `claude-plugins-official` a skill `webapp-testing` z `anthropics/skills`. Příkazy jsou v README.

### 9.4 Hooky a oprávnění

- **SessionStart:** vloží do kontextu větev a posledních 12 řádků `docs/HANDOFF.md`, takže nová relace ví, kde se skončilo.
- **PreToolUse (Edit, Write):** zablokuje `.env`, lockfily a `data/raw`. Zablokuje i `contracts/` a `data/golden/`, pokud není nastaveno `STAFETA_ALLOW_SHARED=1` (tak P1 spouští F1-1). Když vstup nejde přečíst, edit zablokuje.
  - **PreToolUse (Bash):** zablokuje příkazy, které čtou `.env` nebo `.iris/`, vypisují prostředí (`env`, `printenv`) nebo databázi make (`make -p`). Výjimkou je `--env-file` pro uv. Jde o pojistku, ne o bezpečnostní hranici.
- **PostToolUse:** spustí `ruff format`, `ruff check --fix` a `prettier` na upravený soubor.
- **Oprávnění:**
  - povoleno: `make`, `uv`, `pnpm`, `docker compose` a čtecí git příkazy;
  - na dotaz: push, vytvoření a merge PR, `az` a přidání závislostí;
  - zakázáno: čtení `.env`, force push, push do `main`, `reset --hard` a mazání dat.

### 9.5 Jak instrukce vylepšovat za běhu

1. **Opakovaná chyba → jedna věta v AGENTS.md.** Když agent udělá stejnou chybu podruhé, P1 přidá pravidlo krátkým PR. Soubor držte pod 200 řádky.
2. **Opakovaný postup → skill.** Příkladem je „přidej FHIR mapper“ nebo „přidej endpoint“. Skill nechte napsat Claude podle dvou už hotových příkladů.
3. **Tvrdé pravidlo → hook nebo deny.** Text v CLAUDE.md je jen kontext, hook je vynucení.
4. **Retro na každé bráně, 5 minut:** kde agenti selhali a jakou větu pravidel to vyžaduje.
5. **Hlídání kontextu:** `/context`, `/skill-doctor` (cena skillů) a `/doctor prompt-audit` (kontrola instrukcí).

### 9.6 Balíčky, skilly a subagenti podle fází

| Fáze | Instalovat | Skilly | Subagenti |
| --- | --- | --- | --- |
| F0 | Docker, uv, pnpm, Node 22, az CLI, gh CLI, Claude Code, Copilot CLI (`npm i -g @github/copilot`), plugin `frontend-design`, skill `webapp-testing`, Playwright MCP | – | – |
| F1 | Backend: fastapi, uvicorn, pydantic 2, pydantic-settings, httpx, intersystems-irispython 5.4.1, python-docx, openai, tenacity, structlog. Frontend: vite, react, tailwind, shadcn/ui, TanStack Query, zod, msw, vitest. `pnpm exec playwright install chromium`. | fhir-iris, kit-iris-\*, czech-clinical-docs, extraction-eval, demo-flow, frontend-design | fhir-architect, iris-integration |
| F2 | fastembed, fhir.resources 8.x, openapi-typescript, openapi-fetch, date-fns | fhir-iris, kit-iris-vector-search, extraction-eval | extraction-auditor, ux-reviewer |
| F3 | docxtpl, weasyprint (+ systémové knihovny pango), hl7, fastmcp | hl7v2-iris, demo-flow | clinical-safety-reviewer, iris-integration |
| F4 | @playwright/test (video, trace), az containerapp | webapp-testing, demo-flow, frontend-design | test-engineer, security-privacy-reviewer, všichni v paralelním sweepu |
| F5 | – | demo-flow, extraction-eval (čísla pro pitch) | clinical-safety-reviewer (texty pitche) |

## 10. Škálovatelnost a rozvoj po hackathonu

Štafeta roste přidáním šablony diagnózy, konektoru nebo role, ne přepisem. Realistická cesta vede přes 90denní pilot v jednom KOC s jednou diagnózou. Pak následuje síť KOC a ROC a napojení na národní služby podle EHDS.

### 10.1 Funkce navíc z vytěžených dat

| Funkce | Co dělá | Z čeho | Proč je praktická |
| --- | --- | --- | --- |
| Fronta podle rizika zpoždění | Řadí případy podle běžícího T1/T2 a otevřených nálezů | úkoly, nálezy, časová osa | Koordinátor ví, koho řešit prvního |
| Agenda MDT jedním klikem | Seznam případů na dané MDT s připraveností a chybějícími položkami | brána připravenosti | MDT nedostane neúplné podklady |
| Žádosti o chybějící podklady | Hotový text žádosti s přesným seznamem položek a adresátem z adresáře | nálezy typu chybí a chybějící dokument | Méně telefonátů a dohledávání |
| Předání do ROC (koordinátor K2) | Balíček pro regionální centrum s potvrzením převzetí a spouštěi návratu do KOC | handover, úkoly | Bezpečné předání podle FBMI; VZP hradí centrovou léčbu v ROC |
| Karta „další krok“ pro pacienta | Srozumitelně, co ho čeká, kdy, kde a koho volat; se souhlasem i pro rodinu | úkoly, souhlas | Méně stresu a nejistoty |
| Upozornění převzatá z dokumentace | Např. „před invazivním výkonem vysadit apixaban 48 h“ s citací, připnuté k úkolu biopsie | fakta | Koordinátor nezapomene; AI nic neradí, jen cituje |
| Metriky pro VZP a KOC | T1/T2/T3, podíl kompletních handoverů, doba do MDT, dodržení SLA patologie, bez klinického obsahu | časová osa, úkoly | Plátce řídí síť podle dat |
| Sekundární využití | Strukturovaná diagnóza a stadium podle mCODE / Cancer Common pro NOR a výzkum | Condition, Observation | Jednou zapsat, víckrát použít; v EHDS jde o oddělenou „řeku“ |
| Doprava pacienta | Úkol dopravy s funkčními potřebami bez diagnózy | úkoly | Navazuje na výzvu 3 z přednášky FBMI |
| Šablony dalších diagnóz | PlanDefinition pro prs, plíce, kolorektum | PlanDefinition | Škálování bez programování |

### 10.2 Roadmapa

| Horizont | Cíl | Co postavit | Závislosti |
| --- | --- | --- | --- |
| 0–30 dní | Zpevnit PoC | Validace proti CZ Core, threat model, návrh DPIA, regresní golden sety, licence třetích stran | Klinický garant (mentoři VZP) |
| 30–90 dní | Pilot: 1 KOC, 1 diagnóza | SSO, napojení na NIS přes HL7 v2 a FHIR, e-mail a SMS brána, provoz v EU regionu s TLS a privátní sítí, licence IRIS for Health | Smlouva s KOC, zpracovatelská smlouva (GDPR čl. 28), úhrada koordinátora |
| 3–12 měsíců | Síť KOC a ROC, víc diagnóz | Federace přes IHE MHD a AAfD, eŽádanka, identita přes kmenové registry, víc pojišťoven | Standardy NCEZ, novela zákona 325/2021 |
| 12+ měsíců | Národní onkologický průvodce | Výměna ve formátu EEHRxF (pacientský souhrn, laboratoř, propouštěcí zprávy), sekundární data přes HDAB | Harmonogram EHDS (2029 a 2031) |

### 10.3 Provozní a obchodní model (návrh)

- **Kdo za co odpovídá.** Poskytovatel (KOC) je správce dat, dodavatel zpracovatel. VZP je zadavatel a plátce koordinace a dostává procesní metriky bez klinického obsahu.
- **Model provozu.** Klinická data zůstávají u poskytovatele a hub jen směruje a indexuje, což odpovídá modelu AAfD. Tenantem je poskytovatel a víc pojišťoven je podporováno od začátku (pacientka má ZP 211).
- **Financování.** Licence za KOC nebo za koordinátora, případně program Národního onkologického plánu. Pro start se hodí InterSystems Startup program.

### 10.4 Technická škálovatelnost

- Backend je bezstavový a škáluje automaticky v Container Apps. IRIS for Health běží v produkční edici s mirroringem, TLS a Web Gateway, s instancí na poskytovatele nebo region.
- Dokumenty se zpracovávají asynchronně přes frontu, s back-pressure vůič LLM a cache.
- Sady kroků i pravidla nesouladů jsou data, ne kód. Verze promptů a modelů hlídá eval v CI s golden setem pro každou diagnózu.
- Observabilitu zajišťuje OpenTelemetry, auditní stopa jde exportovat.

## 11. Otevřené otázky

Tyto věci plán neumí rozhodnout sám. První tři zjistěte do 17:00.

- [ ] **Embedding model v APIM.** Pokud není, zůstává lokální fastembed (384 dimenzí).
- [ ] **Naběhne IRIS v ACI s password file?** Riziko je přejmenování souboru na read-only mountu. Pokud ne, vyvíjejte lokálně v Dockeru a ACI řešte s mentorem InterSystems.
- [ ] **Verze IRIS v připnutém image** (`$zv`, vypíše bootstrap). HNSW index potřebuje 2025.1 a novější.
- [ ] **Formát odevzdání.** Repo, video, prezentace? Jak dlouhý je pitch? Není to na webu ani v pravidlech.
- [ ] **Copilot plán účastníků.** Free a Student plány nemají ruční výběr modelu; GPT-6.1 Sol a Astra jsou od Pro+ výš. Ověřte, co dává workshop organizace.
- [ ] **Kdo má Opus a Fable.** Advisor Fable vyžaduje přístup k Fable a funguje jen přes Anthropic API, ne přes Foundry.
- [ ] **Hostování „komunikačního uzlu“.** Je pro VZP přijatelné, že uzel provozuje poskytovatel a VZP vidí jen procesní metriky? Zeptejte se mentora RNDr. Rybáře (kapitola 4).
- [ ] **Kdo prezentuje.** Předpoklad je P4, který spí v první směně.

## Zdroje

Podklady od pořadatelů: prezentace VZP, HL7 úvod, analýza FBMI, Microsoft, PHOENIX/XiA a České eHealth v kostce. Dál ZIP s 13 zprávami, zadáním a šablonami.

- [Rakathon – program a termíny](https://www.rakathon.cz/eng)
- [Rakathon 2026 – pravidla a podmínky účasti (PDF)](https://bqcunktidwhqgkjnisbp.supabase.co/storage/v1/object/public/terms/terms/1782206443390-Rakathon_2026_pravidla_a_podminky_ucasti_2_.pdf)
- [InterSystems Challenge at Rakathon 2026](https://developer.intersystems.com/intersystems-challenge-at-rakathon-2026/)
- [FHIR-AI-Hackathon-Kit (větev V2)](https://github.com/intersystems-community/FHIR-AI-Hackathon-Kit)
- [iris-vector-search](https://github.com/intersystems-community/iris-vector-search), [iris-fhir-template](https://github.com/intersystems-community/iris-fhir-template), [iris-healthtoolkit-service](https://github.com/grongierisc/iris-healthtoolkit-service)
- Claude Code: [permission modes](https://code.claude.com/docs/en/permission-modes), [advisor](https://code.claude.com/docs/en/advisor), [subagenti](https://code.claude.com/docs/en/sub-agents), [skilly](https://code.claude.com/docs/en/skills), [hooky](https://code.claude.com/docs/en/hooks-guide), [worktrees](https://code.claude.com/docs/en/worktrees), [GitHub Actions](https://code.claude.com/docs/en/github-actions)
- GitHub Copilot: [podporované modely](https://docs.github.com/en/copilot/reference/ai-models/supported-models), [ceny modelů](https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing), [cloud agent](https://docs.github.com/en/copilot/concepts/agents/cloud-agent/about-cloud-agent), [prostředí cloud agenta](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/customize-the-agent-environment), [merge queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue)
- HL7: [České FHIR příručky](https://hl7.cz/fhir/), [Cancer Common](https://hl7.eu/fhir/cancer-common/), [mCODE STU4](https://hl7.org/fhir/us/mcode/STU4/)
- [Hanna TP et al., BMJ 2020 – zpoždění léčby a mortalita](https://www.bmj.com/content/371/bmj.m4087)
