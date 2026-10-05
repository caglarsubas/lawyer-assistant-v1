# Data-Sourcing Plan for a Turkish Legal AI Assistant (October 2026)

You need about ten sources in your mandatory core, and nearly all of them are free and official. They are: Resmî Gazete, Mevzuat Bilgi Sistemi (MBS), the Adalet Bakanlığı "Bedesten" case-law backend (Yargıtay, Danıştay, BAM and first-instance courts), Yargıtay and Danıştay's own karar arama portals, the two Anayasa Mahkemesi (AYM) databases, HUDOC for Türkiye, TBMM for bills, and a curated set of reference tables. Get the freshness design right by running everything from the daily Resmî Gazete: a mükerrer-aware poll each day should trigger re-checks of MBS consolidated texts and of the courts and regulators affected. Below that sits a polite crawl ordered by decision ID or date, with a strict request-rate limit. The legal basis for ingesting statutes and court decisions is FSEK Article 31.\[1\] Your real constraints are KVKK (6698), portal robots and terms of use, and the sui generis database right that protects commercial compilations such as Lexpera, Kazancı and Legalbank. Treat those vendors as license-or-partner options, not scraping targets.

## TL;DR

- **Mandatory (Tier 0):** Resmî Gazete, MBS, Yargıtay, Danıştay, Bedesten/UYAP, AYM (individual applications and norm review), TBMM, HUDOC for Türkiye, and reference tables (interest rates, harçlar, money limits, severance ceiling, minimum wage). For your launch sub-domains, add the matching regulators (GİB, KİK, Rekabet, KVKK, SGK, SPK/BDDK). Commercial databases and doctrine are beneficial, not required.
- **Freshness:** Treat Resmî Gazete as the master clock. Poll it daily from 00:00 TRT, including mükerrer (repeat) issues, and use it to trigger targeted MBS and court re-fetches. Run incremental court crawls daily or weekly, keyed on decision date and E/K numbers. Sweep regulators weekly, doctrine monthly, and reference tables on event and calendar triggers. Store article-level versions with in-force and repeal dates, not just the latest text.
- **Fetching:** Most sources have no official public API. Use the JSON endpoints behind the official web apps (Bedesten, Yargıtay `aramadetaylist`/`getDokuman`, AYM) at about one request every 10 seconds. Parse ASP.NET forms for KİK, parse PDF/Word for MBS, TBMM and SPK, and use OCR for older Resmî Gazete issues. Ask Adalet Bakanlığı and Cumhurbaşkanlığı Hukuk ve Mevzuat Genel Müdürlüğü for bulk-access agreements early; resmigazete.gov.tr's robots policy already blocks automated agents.

---

## 1. Executive Summary

**The core is public, free and legally reusable.** FSEK Article 31 says: "Resmen yayımlanan veya ilân olunan kanun, Cumhurbaşkanlığı kararnamesi, yönetmelik, tebliğ, genelge ve kazai kararların çoğaltılması, yayılması, işlenmesi veya her hangi bir suretle bunlardan faydalanma serbesttir."\[1\] Statutes, presidential decrees, regulations, communiqués, circulars and court decisions can therefore be copied, processed and reused, including commercially. That freedom covers the official texts only. Third-party compilations are a different matter: FSEK protects databases as works (m.6/1-11) and gives database makers a 15-year sui generis right (ek m.8).\[2\] Headnotes, summaries, cross-links and annotations from commercial vendors are protected even when the decisions inside them are not.

**The hard parts are engineering and data protection, not copyright:**
1. Official APIs are almost nonexistent.
2. Portals throttle aggressively. One October 2026 test of karararama.yargitay.gov.tr hit HTTP 429 after about 5 fast requests and found 10-second spacing stable.\[3\]
3. Yargıtay's online coverage is thin before about 2015. In a 30-decision sample, all 15 decisions from 2015 onward were retrievable, 2 of 5 from 2010–14, and none of 9 from 2009 or earlier.\[3\]
4. KVKK guidance in 2025–2026 has hardened. Its September 2026 guide for lawyers, the "Avukatların Mesleki Faaliyetlerinde Kişisel Verilerin Korunmasına İlişkin Uygulama Rehberi", says that uploading client files to ChatGPT, Claude or Gemini can count as a data transfer under KVKK m.9, and even a domestic provider may count as a recipient.

**What this means for the product:** in Turkish law, how good your retrieval is depends less on how many documents you hold and more on three things:
- **Temporal correctness:** which version of a provision was in force on the relevant date.
- **Citation linkage:** E/K numbers, chamber and article references.
- **Same-day awareness:** of Resmî Gazete changes, including mükerrer issues.

**Recommended build order:**
1. Resmî Gazete and MBS (statute backbone with version history).
2. Yargıtay, Danıştay and BAM via Bedesten and the native portals.
3. AYM, HUDOC and the reference tables.
4. Regulators for each launch sub-domain.
5. Doctrine and a licensed commercial feed.

---

## 2. Grouped Source Inventory

### Tier definitions
- **Tier 0 – Mandatory core:** without it, answers are legally unsafe in every sub-domain.
- **Tier 1 – Mandatory per sub-domain:** required before you claim coverage of that practice area.
- **Tier 2 – Beneficial:** improves depth, recall and drafting quality.
- **Tier 3 – Nice-to-have:** marginal for phase 1.

### 2.1 Tier 0 – Primary legislation and official publication

| Source | Owner | Content | Coverage / depth | Format | Access method | Cadence | Typical lag | Obstacles | Legal / licensing |
|---|---|---|---|---|---|---|---|---|---|
| **Resmî Gazete** (resmigazete.gov.tr) | Cumhurbaşkanlığı İdari İşler Bşk. – Hukuk ve Mevzuat GM | Laws, presidential decrees and decisions, regulations, communiqués, AYM/Yargıtay İBK/Uyuşmazlık decisions, notices (ilanlar) | Every issue since 07.02.1921; electronic-only since September 2018. Recent issues: 01.09.2026 no. 33357, 17.09.2026 no. 33373\[4\]\[5\]\[6\] | HTML per item, PDF per issue; old issues are scanned PDF | Date-keyed URLs (`/eskiler/YYYY/MM/YYYYMMDD-N.htm`; mükerrer as `YYYYMMDDM1-N.htm`; daily pages at `/DD.MM.YYYY`); daily index (fihrist) page. No RSS or API found | Daily from 00:00 TRT, plus mükerrer issues | 0 (it is the event) | **robots.txt disallows automated access** (our fetch was refused); old PDFs need OCR | Official texts are free under FSEK 31; scraping is restricted by robots, so seek written permission or a data agreement |
| **Mevzuat Bilgi Sistemi** (mevzuat.gov.tr) | Cumhurbaşkanlığı Hukuk ve Mevzuat GM | Consolidated texts of Anayasa, kanunlar, CBK, KHK, tüzükler, presidential and ministerial regulations, institutional and university regulations, tebliğler, presidential decisions and circulars; Kanunlar Fihristi | About 18,358 items including 4,271 tebliğler (secondary count, 27.08.2025). Tebliğler only from 01.01.2004. Repealed (mülga) texts only partial\[7\]\[8\]\[9\] | HTML view, Word, PDF (`/MevzuatMetin/1.5.6098.pdf`, `/mevzuat?MevzuatNo=634&MevzuatTur=1&MevzuatTertip=5`, `/File/GeneratePdf?mevzuatNo=…&mevzuatTur=KurumVeKurulusYonetmeligi&mevzuatTertip=5`)\[10\]\[11\]\[12\]\[13\] | Structured URL crawl plus the "Bugün Güncellenenler" (updated today) list | Daily | Consolidation lag after Resmî Gazete **not officially stated; measure it** | No article-level history; mülga coverage incomplete; budget, ratification, amnesty and authorisation laws excluded from the kanun list\[14\] | Free (FSEK 31); ask HMGM for a bulk/XML feed |
| **TBMM** (tbmm.gov.tr) | TBMM Kanunlar ve Kararlar Bşk. | Bills (esas no. 2/…), committee reports (sıra sayısı), plenary transcripts, laws as adopted, gerekçe\[15\] | Bills searchable by term; Kanun ve Karar Bilgi Sistemi article-level with gerekçe and transcripts from Law 5496 (10.5.2006); HTML from the 21st term; PDF from the 1st term\[16\] | HTML plus PDF bill texts | Search forms; GUID detail pages (e.g. bill 2/3703 of 22/05/2026 → Law 7587)\[17\] | Daily during sessions | Ahead of Resmî Gazete (pre-publication awareness) | No API; PDFs | Free; parliamentary documents are official |
| **KAYSİS Kamu Mevzuat Sistemi** | Cumhurbaşkanlığı | Public bodies' rules not published in Resmî Gazete\[18\] | Varies by institution | HTML/PDF | Crawl | Weekly | Varies | Coverage is uneven | Free |

### 2.2 Tier 0 – Case law (içtihat)

| Source | Owner | Content | Coverage | Format | Access method | Cadence | Lag | Obstacles | Legal |
|---|---|---|---|---|---|---|---|---|---|
| **Bedesten** (bedesten.adalet.gov.tr → `mevzuat.adalet.gov.tr/ictihat/{id}`) | Adalet Bakanlığı Bilgi İşlem GM | Single backend for Yargıtay, Danıştay, first-instance civil (YERELHUKUK), regional civil appeals (ISTINAFHUKUK), KYB\[19\] | 79 chamber codes for Yargıtay and Danıştay; date-range filters; Boolean operators (no wildcards or proximity)\[19\] | JSON search → HTML document | Unauthenticated JSON endpoints used by the official web app (open-source clients: yargi-cli, yargi-mcp)\[19\] | Daily incremental by `kararTarihi` | Unknown; measure the gap from decision date to first appearance | Undocumented; may change without notice; throttling | Decisions free under FSEK 31; the API is not an official public product, so seek a formal agreement |
| **Yargıtay Karar Arama** (karararama.yargitay.gov.tr) | Yargıtay | Chamber, HGK, CGK, BGK, İBK decisions | Free counts cited as ~8.05M (secondary, undated); in practice dense from 2015, sparse before 2010\[3\]\[20\] | JSON (`POST /aramadetaylist`, `GET /getDokuman?id=`)\[3\] | Same endpoints as the official SPA | Daily | Unknown (measure) | 429 after ~5 fast requests; ~10 s spacing stable; captcha may appear under load; esas formats vary (HGK "2024/10-389" → normalise)\[3\] | Free (FSEK 31); anonymised at source, but re-check names |
| **Danıştay Karar Arama** (karararama.danistay.gov.tr) | Danıştay | Chambers 1–17, İDDK, VDDK, İBK, AYİM | ~196k decisions cited (secondary)\[20\] | JSON/HTML (`getDokuman?id=`) | Portal endpoints plus Bedesten | Weekly (lower volume) | Unknown | Same as Yargıtay | Free |
| **UYAP Emsal** (emsal.uyap.gov.tr) | Adalet Bakanlığı | BAM (regional civil appeals) and first-instance decisions | Opened 2019; ~140k BAM civil decisions cited (secondary); **selective, not representative**\[20\]\[21\]\[22\] | HTML/JSON | Portal (captcha reported); prefer Bedesten for the same data | Weekly | Unknown | Captcha; selective sampling | Free; anonymisation quality varies, so run your own PII pass |
| **AYM Bireysel Başvuru** (kararlarbilgibankasi.anayasa.gov.tr) | Anayasa Mahkemesi | Individual-application judgments and admissibility decisions; plenary, section and commission decisions | From 23.09.2012 jurisdiction; decisions dated up to 2/9/2026 seen\[23\]\[24\] | HTML (`/BB/{yıl}/{no}`), with RG date/number, press notice and citation string\[24\] | Crawl ordered by application number and decision date; also annual "Seçme Kararlar" PDFs\[25\] | Weekly, plus Resmî Gazete triggers (pilot and plenary decisions appear there) | Days to weeks after decision (measure) | Large, partly UDF legacy files (kararlaryeni)\[26\] | Free |
| **AYM Norm Denetimi** (normkararlarbilgibankasi.anayasa.gov.tr) | Anayasa Mahkemesi | Annulment and objection decisions | Full | HTML/PDF | Crawl; **the Resmî Gazete publication is authoritative** | Triggered by Resmî Gazete | 0 vs Resmî Gazete | Annulment takes effect on a deferred date that must be captured | Free |
| **HUDOC** (hudoc.echr.coe.int, Turkish interface) | ECtHR, plus Adalet Bakanlığı İnsan Hakları Dairesi translations | Türkiye judgments; Turkish translations | Ministry has translated since 01.03.2012; over 2,600 Turkish translations (including all Türkiye judgments) when HUDOC-Turkish launched on 14.11.2013, per ECtHR press release ECHR 335 (2013); ~2,070 key cases translated by the Court's own project | JSON API behind the HUDOC UI; DOCX/PDF | HUDOC query API (respondent state = TUR, language = TUR) | Weekly (judgments on Tue/Thu) | Translation lag months (unverified) | Rate limits; mixed formats | **Ministry translations: non-commercial quoting with attribution only.**\[27\]\[28\] License before redistributing the Turkish text; link to the English/French originals instead |

### 2.3 Tier 1 – Regulators by sub-domain

| Sub-domain | Source / URL | Content | Access method | Cadence | Notes |
|---|---|---|---|---|---|
| Tax | **GİB** gib.gov.tr/mevzuat/arama | Laws, articles, CBK, BKK, tebliğ, **sirküler, özelge**, iç genelge, genel yazı, gerekçe\[29\]\[30\] | Faceted HTML search with Excel export; özelge URLs `/mevzuat/kanun/{id}/ozelge/{id}`\[30\]\[31\] | Weekly; daily in tax season | Özelges are published under VUK 413 and bind only the requester; tag them as "non-binding guidance"\[31\]\[32\] |
| Public procurement | **KİK / EKAP** ekap.kik.gov.tr/EKAP/Vatandas/KurulKararSorgu.aspx | Uyuşmazlık, düzenleyici and mahkeme kararları; Kamu İhale Bülteni PDF archive\[33\]\[34\]\[35\] | ASP.NET WebForms (ViewState postbacks); also mirrored on e-Devlet\[36\]\[37\] | Weekly | ~100k dispute decisions since 2003 (vendor claim); filter by year\[35\]\[38\] |
| Competition | **Rekabet Kurumu** rekabet.gov.tr/tr/Kararlar (+ /SonkurulKararlari, /Davalar, /Safahatlar) | Board decisions with reasons, court history | HTML form (type, number, decision date, publication date); PDF/Word downloads (unconfirmed)\[39\] | Weekly | Latest seen: published 1.9.2026, no. 25-44/1086-615\[39\] |
| Data protection | **KVKK** kvkk.gov.tr (Icerik pages: Kurul Karar Özetleri; Rehberler) | Board decision summaries, principle decisions, guides | Paginated HTML lists; full decisions only sometimes in Resmî Gazete | Weekly | Key 2025–26 guides: AI recommendations (Apr 2025), generative-AI guide (24.11.2025), workplace GenAI (Feb 2026), lawyers' guide (22.09.2026)\[40\]\[41\]\[42\]\[43\]\[44\] |
| Capital markets | **SPK** spk.gov.tr/spk-bultenleri | Bulletin (several issues a week, e.g. 2026/67 on 30.09.2026), communiqués\[45\] | Index scrape → PDF (opaque hex IDs); KAP notices\[46\] | 2–3× per week | Subscribe to email alerts as a trigger |
| Banking | **BDDK** bddk.org.tr/Mevzuat/Liste/55 (published in Resmî Gazete) and /56 (not published) | Board decisions, regulations\[47\]\[48\] | HTML lists → `/Mevzuat/DokumanGetir/{id}` PDF\[49\] | Weekly | Add TCMB and MASAK regulations to the same sweep |
| IP | **TÜRKPATENT** turkpatent.gov.tr/bultenler | Patent and trademark bulletins, official trademark gazette\[50\] | Filterable list → files on webim.turkpatent.gov.tr\[50\]\[51\] | Monthly or per bulletin | **No public YİDK decision database found**; YİDK decisions come only from commercial sources |
| Labor and social security | SGK genelgeler; ÇSGB | Circulars and general letters | HTML/PDF crawl | Weekly | Plus Yargıtay 9th Civil Chamber and HGK via Bedesten |
| Jurisdiction disputes | Uyuşmazlık Mahkemesi | Decisions (also in Resmî Gazete) | Portal crawl; yargi-mcp client exists\[52\] | Monthly, plus Resmî Gazete triggers | — |
| Public finance | Sayıştay | Daire, Temyiz Kurulu and Genel Kurul decisions | Portal crawl (8 chamber filters in yargi-mcp)\[53\] | Monthly | Municipal and public-entity work |
| Profession | TBB (meslek kuralları, disiplin, Avukatlık Asgari Ücret Tarifesi); Noterler Birliği; Arabuluculuk and Bilirkişilik Daire Başkanlıkları | Rules, tariffs, circulars | HTML/PDF crawl | Monthly, plus annual tariff triggers | The fee tariff is also published in Resmî Gazete; use that copy |

### 2.4 Tier 2 – Beneficial

| Source | Value | Access | Licensing |
|---|---|---|---|
| **Lexpera** (On İki Levha) | Industry standard; 1.6M+ Yargıtay decisions, books, articles, version timelines, "Etkilediği Mevzuat" for omnibus laws; has its own LEXI AI\[54\]\[55\]\[56\]\[57\]\[58\] | Commercial; terms limit use to the member's professional activity\[59\] | Requires a licence or partnership; the vendor's own AI makes it a competitor |
| **Legalbank** (Legal Yayıncılık) | 2M+ decisions, 44k+ legislation items, petitions, gerekçeler, journals\[54\]\[60\] | Commercial | Licence |
| **Kazancı** | Long-established decision and legislation archive with pre-2010 depth | Commercial (campus-only at many universities)\[60\] | Licence; best route to pre-2010 Yargıtay |
| HukukTürk, Sinerji, Lebib Yalkın (tax), Seçkin | Niche depth (tax, commentary) | Commercial | Licence |
| **UYAP Mevzuat** (mevzuat.adalet.gov.tr) | Consolidated legislation plus 40k+ selected high-court decisions, AYM, AİHM-Türkiye, Uyuşmazlık\[61\] | Same Bedesten backend | Free |
| DergiPark law journals, YÖK Tez Merkezi, bar journals, Yargıtay/Danıştay Dergisi | Doctrine for reasoning and terminology | OAI-PMH (DergiPark), crawl | Copyright belongs to the authors; check each journal's CC licence and index metadata or abstracts unless the licence allows more |
| English translations (MBS links, Ministry of Justice, CoE) | Cross-lingual retrieval and English UI | Crawl | Unofficial; never cite as authoritative |
| EUR-Lex / CJEU | Customs-union and harmonised areas (competition, KVKK–GDPR, product safety) | Official API/SPARQL | Free (EU reuse policy) |

### 2.5 Tier 0 – Reference tables (keep as structured data, not text)

| Table | 2026 value (verified) | Source / trigger |
|---|---|---|
| Yeniden değerleme oranı (revaluation rate) | **25.49%**\[62\] | VUK GT 585, Resmî Gazete 27.11.2025 no. 33090; annual (Nov–Dec)\[62\] |
| HMK money limits | İstinaf **50,000 TL**; temyiz **682,000 TL**; temyizde duruşma **1,023,000 TL**; senetle ispat **41,000 TL**\[63\] | Automatic under HMK Ek m.1 via the revaluation rate (sources conflict: 680k/1.02M, 42k). Since Law 7550 the limit on the **filing date** applies. A possible 16.07.2026 amendment by Law 7589 to HMK 362 is **unverified; check it**\[64\]\[65\]\[66\]\[67\] |
| Kıdem tazminatı tavanı (severance ceiling) | **73,729.87 TL** (01.07–31.12.2026); 64,948.77 TL (H1 2026)\[68\] | HMB pay-coefficient circular; semi-annual (Jan/Jul)\[69\]\[70\] |
| Brüt asgari ücret (gross minimum wage) | **33,030.00 TL/month** (1,101 TL/day; net 28,075.50)\[71\]\[72\] | Resmî Gazete 26.12.2025 no. 33119; annual\[71\] |
| Legal and default interest (3095), avans faizi (TCMB), harçlar tarifeleri, Avukatlık Asgari Ücret Tarifesi, adli tatil (20 Jul–31 Aug), public holidays | Not verified in this research | Resmî Gazete triggers plus a calendar of annual dates |

### 2.6 Sub-domain → minimum source map

| Sub-domain | Legislation core | Case law | Regulator / secondary |
|---|---|---|---|
| Civil / obligations / property (TMK, TBK) | MBS | Yargıtay civil chambers, HGK, İBK; BAM | — |
| Criminal (TCK, CMK, infaz) | MBS | Yargıtay criminal chambers, CGK; AYM; ECtHR | Adalet Bak. genelgeler |
| Commercial / company (TTK) | MBS | Yargıtay 11th Civil Chamber; BAM commercial; Emsal asliye ticaret | Ticaret Bakanlığı, MERSİS/TTSG |
| Labor and social security | MBS (4857, 5510, 7036) | Yargıtay 9th Civil Chamber and HGK | SGK, ÇSGB, severance ceiling, minimum wage |
| Tax | MBS + GİB | Danıştay tax chambers, VDDK | GİB özelge/sirküler, revaluation rate |
| Administrative | MBS | Danıştay, İDDK, BİM | KAYSİS |
| Constitutional / human rights | Anayasa | AYM (both databases), HUDOC | Ministry ECtHR bulletins |
| Enforcement and bankruptcy (İİK) | MBS | Yargıtay 12th Civil Chamber (and successors) | Harçlar, interest |
| Family | MBS (TMK, 6284) | Yargıtay 2nd Civil Chamber | — |
| Real estate / land registry | MBS (634, 2644, 3194) | Yargıtay civil chambers, Danıştay (zoning) | TKGM genelgeleri |
| IP (6769, FSEK) | MBS | Yargıtay 11th Civil Chamber; IP courts (Emsal) | TÜRKPATENT bulletins |
| Data protection (6698) | MBS | AYM, Danıştay | KVKK decisions and guides |
| Competition (4054) | MBS | Danıştay 13th Chamber, İDDK | Rekabet Kurumu |
| Public procurement (4734/4735) | MBS | Danıştay 13th Chamber | KİK/EKAP |
| Capital markets / banking | MBS | Danıştay, Yargıtay | SPK bulletin, BDDK, TCMB, MASAK |
| Consumer (6502) | MBS | Yargıtay 3rd Civil Chamber; BAM | Ticaret Bak. (hakem heyetleri) |
| Immigration / foreigners (6458) | MBS | Danıştay, AYM, ECtHR | Göç İdaresi |

---

## 3. Freshness Policy and Change Detection

### 3.1 Cadence by source class

| Class | Trigger | Rule | Change detection | Avoid re-crawl |
|---|---|---|---|---|
| Resmî Gazete | Clock | Poll from 00:00 TRT every 15 min until the day's fihrist appears, then hourly until 23:59 for **mükerrer** (M1, M2…) issues; check the next morning for late mükerrer\[73\]\[74\] | Fihrist hash; new item URLs | Issues never change, so fetch each item once and keep it immutably |
| MBS consolidated texts | Resmî Gazete items that amend, repeal or add provisions | **Event-driven:** re-fetch every act cited in the day's Resmî Gazete changes, then re-poll daily for 14 days until the consolidated hash changes. **Weekly** sweep of "Bugün Güncellenenler"; **monthly** full hash sweep | SHA-256 of normalised text per article; ETag/Last-Modified where present | Fetch only listed or affected acts |
| TBMM | Daily during sessions | Track bill state machine (submitted → committee → plenary → adopted → Resmî Gazete) | Status-field diff | Fetch the detail page only on status change |
| Yargıtay / Danıştay / Bedesten | Daily (Yargıtay), weekly (Danıştay) | Sliding window: query `kararTarihi` from the last 60 days each run, because decisions are backfilled late | Document-ID watermark plus (court, chamber, E, K) unique key | Skip known IDs; re-fetch only on content-hash mismatch in a monthly sample |
| AYM | Weekly, plus Resmî Gazete triggers | Application-number and decision-date window | ID watermark | Same |
| HUDOC | Weekly | `kpdate` > last run; separately poll for Turkish translations of old judgments | itemid plus language | — |
| Regulators | Weekly (SPK 2–3× per week) | List-page diff | Hash of list rows | Fetch only new rows |
| Doctrine | Monthly | OAI-PMH `from=` date | Record datestamp | — |
| Reference tables | Resmî Gazete triggers plus calendar (Jan 1, Jul 1, late Nov revaluation, Dec minimum wage) | Owner-approved update with effective date | Manual and QA | — |

**Lag:** we found no official numbers for MBS consolidation lag or Yargıtay publication lag. Build lag telemetry from day 1: record decision or Resmî Gazete date, first-seen timestamp, and the gap between them for each source. Publish your own SLA once you have 60 days of data.

### 3.2 Versioning model (the main driver of retrieval quality)
- **Unit = article (madde), with fıkra and bent anchors.** Key: `{mevzuatTur}.{tertip}.{no}/m.{madde}`, matching MBS's `1.5.6098` convention.\[11\]\[75\]
- Each article version stores `valid_from` (yürürlük), `valid_to` (mülga or amended), the amending act (Law no., Resmî Gazete date/number), and an AYM annulment flag with its *effective* date. AYM often defers effect by 9–12 months, so the annulment date and the effective date differ.
- Build history yourself from the Resmî Gazete amendment chain. MBS shows only the current text, and repealed texts are only partly available. For past versions of the main codes, Lexpera's version timelines are the commercial shortcut.
- Store gerekçe (from TBMM) linked to article versions.
- Retrieval must filter by `as_of_date`. Default to today, but read the date of the facts from the user's question.

### 3.3 Index refresh
- Re-embed incrementally at chunk level, keyed by content hash; never re-embed unchanged text.
- Use hybrid retrieval: BM25 on Turkish-normalised text plus dense vectors. Metadata filters: court, chamber, decision type (bozma/onama/İBK), date, E/K, cited articles, sub-domain.
- **Citation graph:** extract "6098 sayılı Kanun'un 49. maddesi", "TBK m.49", "HGK 2024/389 E." and similar patterns into edges between decisions and articles and between decisions themselves. When an article changes, flag the decisions that interpret the old version.
- Hot index (last 90 days) refreshes hourly; cold index refreshes nightly.

---

## 4. Fetching Architecture

### 4.1 Pipeline
1. **Scheduler and trigger bus.** The Resmî Gazete poller emits events (new law no., amended act IDs, AYM decisions), and these drive the MBS, court and table jobs.
2. **Fetchers, one per source:**
   - Polite HTTP client: per-host token bucket (Yargıtay ≤6 requests/min); exponential backoff on 429; fixed user-agent with contact email; TR-based egress.
   - Headless browser only where JS or captcha forces it (Emsal, some AYM views). Never solve captchas automatically; escalate to a partnership request instead.
   - ASP.NET ViewState handling for EKAP.
3. **Raw store.** Keep originals immutably (HTML, PDF, DOCX, UDF) with fetch metadata, for audit and re-parsing.
4. **Parsing:**
   - HTML → structured JSON.
   - PDF: text layer first; OCR (Tesseract or a commercial engine with the Turkish model) for scanned Resmî Gazete issues and old bulletins.
   - UDF (UYAP Editör format) → XML extraction.
   - DOCX via a document converter.
5. **Normalisation (Turkish-specific):**
   - NFC Unicode normalisation.
   - Locale-aware case folding (İ/i, I/ı). Never use default `lower()`, which turns "İ" into "i̇".
   - Map legacy encodings (Windows-1254, ISO-8859-9) and circumflex variants (â, î, û) to search-equivalent forms.
   - Morphology-aware stemming (Zemberek or a similar Turkish analyser) for BM25.
   - Hyphenation repair in PDFs.
6. **Entity extraction and metadata.** See 4.2.
7. **PII pass.** Courts anonymise only partly. Run NER-based masking (names, TCKN, addresses, plates, IBAN) before indexing, and keep the raw text in a restricted vault or discard it.
8. **Versioner → index → evaluation.** Build a gold set of about 500 lawyer-written queries per sub-domain, measure recall@k and citation accuracy, and run regression tests on every index build.

### 4.2 Canonical identifiers (metadata schema)
- **Legislation:** `kanun_no` (e.g. 6098), `mevzuat_tur` (1 = Kanun; 7 = Yönetmelik; 9 = Tebliğ, as in MBS URLs), `tertip`, `rg_tarih`, `rg_sayi`, `mukerrer` (bool and sequence), `madde`, `fikra`, `bent`, `yururluk`, `mulga`.\[10\]\[13\]
- **Decisions:** `mahkeme`, `daire`/`kurul` (e.g. "9. Hukuk Dairesi", HGK, CGK, İBK, İDDK, VDDK), `esas_no` (YYYY/N), `karar_no` (YYYY/N), `karar_tarihi`, `karar_turu`, `kesinlesme` where known, `source_doc_id` (Bedesten documentId / getDokuman id), `rg_tarih_sayi` (for İBK, AYM and Uyuşmazlık decisions).
  - Normalise HGK esas formats: "2024/10-389" carries a chamber prefix, so store both the raw and the normalised form.\[3\]
  - Detect BAM decisions from the header, not the body.\[3\]
- **AYM:** `basvuru_no` (YYYY/N), `bolum`/`genel_kurul`, `karar_tarihi`, standard citation string (e.g. "*Güher Ergun ve Tosun Tayfun Ergun* [2. B.], B. No: 2012/12, 17/9/2013").\[24\]
- **ECtHR:** application no., itemid, language, importance level.

### 4.3 Source-specific methods and obstacles

| Source | Method | Key obstacles | Mitigation |
|---|---|---|---|
| Resmî Gazete | Date-keyed fetch of fihrist → items; OCR the archive | robots disallow; scanned pre-2000s PDFs | Written permission from HMGM; until then, take daily amendments from MBS and TBMM and limit the backfill |
| MBS | Structured URL crawl (PDF/Word/HTML) | No history; no API | Build versions from the Resmî Gazete chain; ask HMGM for XML |
| Bedesten | JSON search (court type, chamber, date) → doc | Undocumented and changeable | Contract tests; fall back to the native portals |
| Yargıtay | `POST /aramadetaylist`, `GET /getDokuman?id=` | 429, captcha, pre-2015 gaps | ≥10 s spacing; overnight backfill (~11,600 requests ≈ 32 h per batch of that size);\[3\] license Kazancı/Lexpera for pre-2010 |
| AYM | HTML crawl by application number; Seçme Kararlar PDFs | Volume; UDF legacy | Incremental by date |
| HUDOC | Query API | Translation licensing | Store the English/French originals; link to Turkish translations |
| KİK | WebForms postback crawl | ViewState and session | Session-aware scraper; yargi-mcp has a working module to learn from\[52\] |
| GİB | Faceted search, Excel export | — | Use the export to seed ID lists |
| SPK / BDDK / TÜRKPATENT | List scrape → PDF | Opaque IDs | Diff the list pages |

---

## 5. Legal and Compliance Guardrails

1. **Copyright.** Official texts and court decisions are free to reuse (FSEK 31).\[1\] Do **not** scrape commercial databases: their compilations carry work protection (m.6/1-11) and the 15-year sui generis right (ek m.8),\[2\] and their terms of use (e.g. Lexpera's) limit use to the member's own professional work.\[59\] Doctrine (journal articles, theses) belongs to its authors, so use abstracts, metadata and links unless a CC licence allows full text. Ministry ECtHR translations may be quoted only for non-commercial purposes with attribution.\[27\]\[76\]
2. **Portal terms and robots.** resmigazete.gov.tr disallows automated agents. Respect that and get permission. For the other portals: identify yourself, throttle, cache, avoid peak hours, and never bypass captchas. Using undocumented JSON endpoints is technically workable but legally grey; formalise it with Adalet Bakanlığı Bilgi İşlem GM.
3. **KVKK (6698):**
   - Court decisions contain personal data, including special-category data (health, criminal records). Run your own anonymisation and keep a documented anonymisation method, following KVKK's 2017 guide on deletion, destruction and anonymisation.\[44\]
   - KVKK's generative-AI guide (Üretken Yapay Zekâ ve Kişisel Verilerin Korunması Rehberi – 15 Soruda, published 24.11.2025) states, as summarised by Mondaq, that publicly accessible data "yapay zekânın eğitilmesi amacıyla serbestçe kullanılamayacağını". Treat ingestion as processing that needs a legal basis and a legitimate-interest assessment, and use retrieval, not training, wherever possible.
   - KVKK's "Avukatların Mesleki Faaliyetlerinde Kişisel Verilerin Korunmasına İlişkin Uygulama Rehberi" (KVKK Yayınları No. 115, dated Temmuz 2026, announced 22.09.2026, prepared with TBB's input) says in section VIII.C that lawyers uploading client files to foreign LLMs can be a cross-border transfer under m.9, and that a domestic provider can also be a recipient. Design for TR-region hosting, a no-training/zero-retention LLM contract, client-side masking, and a VERBİS registration where applicable.
4. **UYAP / e-Devlet.** Never ingest from a lawyer's UYAP Avukat Portal session (case files are confidential and access is personal). Use only the public portals.
5. **Regulatory watch:**
   - There is no standalone AI law as of October 2026. Bills pending or submitted: 2/2234 (June 2024); a July 2025 TCK/5651 bill; 2/3358 (07.11.2025). The TBMM Yapay Zeka Araştırma Komisyonu report (Sıra Sayısı 260, published 30 March 2026) proposes a Türkiye Yapay Zeka Kurumu and a Yapay Zeka Etik Kurulu.
   - The Ministry's Yargı Reformu Stratejisi 2025–2029, announced on 23.01.2025, has 5 aims, 45 targets and 264 activities (110 legislative, 125 administrative, 29 mixed) according to its Eylem Planı. Faaliyet 1.9.a calls for "yapay zekâ temelli öneri sistemleri" to support adjudication, and 1.9.h for new UYAP software (2026). This brings both a partnership opportunity and a competitive risk.

---

## 6. Phased Roadmap

| Phase | Weeks | Deliverables | Exit criteria |
|---|---|---|---|
| **0 – Access and legal** | 0–4 | Letters to HMGM (Resmî Gazete/MBS bulk), Adalet Bakanlığı BİGM (Bedesten), Yargıtay; KVKK DPIA; TR hosting; vendor talks (Kazancı/Lexpera/Legalbank) | Written positions; DPIA signed |
| **1 – Statute backbone** | 2–8 | MBS full crawl (laws, CBK, regulations, tebliğ); Resmî Gazete daily poller from go-live, plus backfill to 2004; article-level versioning for the ~40 most-used codes (TMK, TBK, TTK, HMK, İİK, TCK, CMK, 4857, 5510, 6698, 2577, VUK, KDV, GVK, 6502, 634, 6458…) | Same-day Resmî Gazete detection; temporal QA on 200 amended articles |
| **2 – Case law core** | 4–14 | Bedesten plus Yargıtay/Danıştay 2015 onward; all HGK, CGK, İBK, İDDK, VDDK; AYM both databases; HUDOC-TUR; citation graph | ≥95% retrievability on a gold set of E/K citations from 2015 onward |
| **3 – Sub-domain packs** | 10–20 | GİB, KİK, Rekabet, KVKK, SGK, SPK/BDDK, TÜRKPATENT; reference tables with an owner workflow | Sub-domain evaluation ≥ target |
| **4 – Depth** | 16–30 | Licensed pre-2015 Yargıtay; doctrine metadata; TBMM gerekçe linking; English translations | Licence executed |

### Open risks
1. **Undocumented endpoints break, or access is revoked.** Mitigate with contract tests, fallbacks and a formal agreement.
2. **Pre-2015 Yargıtay gap.** Free sources are thin, so licensing is likely needed for "settled case law" questions.
3. **Representativeness.** Emsal and BAM sets are curated, so do not present them as statistically complete.
4. **Conflicting secondary data.** The HMK limits are a live example (680k vs 682k).\[67\]\[77\] Treat Resmî Gazete or the statutory formula as the source of truth and show your working.
5. **Tightening KVKK enforcement** on AI and lawyers' data flows.
6. **State competition.** Ministry AI systems inside the new UYAP may reduce public-portal openness or compete directly.

## Caveats
- We could not verify these and they need confirming: Resmî Gazete's exact publication time (reported as "around 00:00", not official);\[73\] MBS consolidation lag; Yargıtay/Danıştay publication lag; captcha thresholds; decision totals (secondary, undated); the Law 7589 amendment to HMK 362; and the 2026 interest and harç values.
- The Yargıtay rate-limit and coverage figures come from one developer's 30-decision test (October 2026), not official documentation.\[3\] Re-measure them yourself.

## Sources

1. [5846 sayılı Fikir ve Sanat Eserleri Kanunu - Konsolide metin](https://www.lexpera.com.tr/mevzuat/kanunlar/fikir-ve-sanat-eserleri-kanunu-5846)
2. [5846 Sayılı Fikir Ve Sanat Eserleri Kanunu Kapsamında Veritabanlarının Eser Niteliği - Ozay Law](https://ozay.av.tr/publication/5846-sayili-fikir-ve-sanat-eserleri-kanunu-kapsaminda-veritabanlarinin-eser-niteligi)
3. [docs: karararama.yargitay.gov.tr verification spike by orhanors · Pull Request #5 · Siestai/hukuk-yz](https://github.com/Siestai/hukuk-yz/pull/5)
4. [T.C. Resmî Gazete](https://resmigazete.gov.tr/)
5. [https://www.resmigazete.gov.tr/eski](https://www.resmigazete.gov.tr/eski)
6. [T.C. Resmî Gazete - Vikipedi](https://tr.wikipedia.org/wiki/T.C._Resm%C3%AE_Gazete)
7. [Mevzuat Bilgi Sistemi](https://www.mevzuat.gov.tr/Anasayfa)
8. [Mevzuat Bilgi Sistemi](https://www.altaslar.com/blog/mevzuat-bilgi-sistemi/)
9. [Mevzuat Bilgi Sistemi](https://mevzuat.gov.tr/)
10. [Sakarya Üniversitesi Hukuk Fakültesi Dergisi » Submission » İfaya Eklenen Ceza Koşulunda Çekince İleri Sürülmesi](https://dergipark.org.tr/en/pub/shd/article/1673334)
11. [Medical and legal evaluation of injuries due to dog bites: a Türkiye study - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC10977485/)
12. [Kanun ve Yönetmelikler](https://ymbd.org/bilgi-ve-haber/kanun-ve-yonetmelikler/)
13. [MEVZUAT](https://abaybarsgogez.net/mevzuat/)
14. [Mevzuat Bilgi Sistemi](https://www.mevzuat.tr/hakkimizda)
15. [TÜRKİYE BÜYÜK MİLLET MECLİSİ](https://www.tbmm.gov.tr/Sayfa/Kanun-Teklifleri-Sorgu-Formu-Kullanim-Bilgileri)
16. [Kanun ve Karar Bilgi Sistemi](https://www.tbmm.gov.tr/kanun-ve-karar-bilgi-sistemi)
17. [kanun teklifi komisyon bilgileri](https://www.tbmm.gov.tr/Yasama/KanunTeklifi/8ee04de6-20b3-4f98-a3ef-019e4f741b51)
18. [Mevzuat Bilgi Sistemi](https://www.mevzuat.gov.tr/faydalilinkler)
19. [yargi-cli/README.tr.md at main · saidsurucu/yargi-cli](https://github.com/saidsurucu/yargi-cli/blob/main/README.tr.md)
20. [Ücretsiz olarak ulaşabileceğiniz karar arama linkleri:](https://www.ihtisashukuk.com/haberdetay/ucretsiz-olarak-ulasabileceginiz-karar-arama-linkleri)
21. [İstanbul Barosu on X: "UYAP Ücretsiz Emsal Karar Arama Bilgi Bankası hizmete açıldı! Linklerden inceleyebilirsiniz. BAM ve yerel mahkeme kararları için: https://t.co/0v8HVgvVop Yargıtay kararları için: https://t.co/XWuazOBcES" / X](https://x.com/istbarosu/status/1130493787359334400)
22. [emsal.uyap.gov.tr - ekşi sözlük](https://eksisozluk.com/emsal-uyap-gov-tr--7285352)
23. [Anayasa Mahkemesi Kararlar bilgi Bankası](https://kararlarbilgibankasi.anayasa.gov.tr/kbb/pages/search/BireyselBasvuru)
24. [T.C. Anayasa Mahkemesi](https://kararlarbilgibankasi.anayasa.gov.tr/BB/2012/12)
25. [Bireysel Başvuru Seçme Kararlar](https://www.anayasa.gov.tr/tr/yayinlar/bireysel-basvuru-secme-kararlar/)
26. [Karar Arama](http://kararlaryeni.anayasa.gov.tr/)
27. [© T.C. Adalet Bakanlığı, 2020. Bu gayriresmî çeviri, Adalet Bakanlığı, İnsan](https://hudoc.echr.coe.int/app/conversion/docx/pdf?library=ECHR&id=001-202103&filename=%C4%B0NAN+v.+TURKEY+-+%5BTurkish+Translation%5D+by+the+Turkish+Ministry+of+Justice.pdf&logEvent=False)
28. [İKİNCİ BÖLÜM KABUL EDİLEBİLİRLİK HAKKINDA KARAR](https://hudoc.echr.coe.int/app/conversion/docx/pdf?library=ECHR&id=001-177922&filename=K%C3%96KSAL+v.+TURKEY+-+%5BTurkish+Translation%5D+by+the+Turkish+Ministry+of+Justice.pdf&logEvent=False)
29. [Mevzuat Arama - Gelir İdaresi Başkanlığı](https://gib.gov.tr/mevzuat/arama?tur=vergi-mevzuati&amp=&ktype=99&amp=&kanun-turu=ozelge)
30. [Mevzuat Arama - Gelir İdaresi Başkanlığı](https://www.gib.gov.tr/mevzuat/arama?tur=vergi-mevzuati)
31. [Özelgeler - Gelir İdaresi Başkanlığı](https://gib.gov.tr/mevzuat/kanun/433/ozelge/38742)
32. [Özelgeler - Gelir İdaresi Başkanlığı](https://www.gib.gov.tr/mevzuat/kanun/436/ozelge/38962)
33. [Kurul Karar - EKAP - Kamu İhale Kurumu](https://ekap.kik.gov.tr/EKAP/Vatandas/KurulKararSorgu.aspx)
34. [EKAP (Elektronik Kamu Alımları Platformu)](https://ekap.kik.gov.tr/ekap/vatandas/kurulkarartutanaksorgu.aspx)
35. [KİK Karar Arama 2026 - Avukatistan](https://avukatistan.com/kik)
36. [Kamu İhale Kurumu - Kurul Kararları (Uyuşmazlık Kararları)](https://www.turkiye.gov.tr/kik-kurul-karar-sorgula)
37. [Kamu İhale Kurumu - Kurul Karar Tutanakları Sorgulama](https://www.turkiye.gov.tr/kik-kurul-karar-tutanaklari-sorgulama)
38. [Anasayfa - Kamu İhale Kurulu Kararları](https://www.kikkararlari.com/)
39. [Rekabet Kurumu - Kurul Kararı Arama](https://www.rekabet.gov.tr/tr/Kararlar)
40. [Üretken Yapay Zekâ ve Kişisel Verilerin Korunması Rehberi (15 Soruda) Yayınlanmıştır - Duyurular](https://www.zumbul.av.tr/tr/duyurular/uretken-yapay-zeka-rehberi-kvkk-yayinlanmistir)
41. [Üretken Yapay Zekâ ve Kişisel Verilerin Korunması Rehberi 24.11.2025 tarihinde Kişisel Verileri Koruma Kurumu’nun internet sitesinde yayımlanmıştır. - Srp-Legal](https://www.srp-legal.com/tr/uretken-yapay-zeka-ve-kisisel-verilerin-korunmasi-rehberi-24-11-2025-tarihinde-kisisel-verileri-koruma-kurumunun-internet-sitesinde-yayimlanmistir/)
42. [KVKK'nın Avukatlar İçin Rehberi: Dosyayı Yapay Zekâya Yüklemek Yurt Dışına Aktarım Sayılabilir](https://sinanogluhukuk.com/tr/makaleler/kvkk-avukatlar-rehberi-yapay-zeka-yurt-disi-aktarim)
43. [Yapay Zekâ Alanında Kişisel Verilerin Korunması](https://www.cottgroup.com/tr/blog/kvkk-gdpr/item/yapay-zeka-alaninda-kisisel-verilerin-korunmasina-dair-tavsiyeler)
44. [KVKK Rehberleri](https://afyonluoglu.org/kvk/kvkk-rehberler/)
45. [Sermaye Piyasası Kurulu - 2026 yılı SPK Bültenleri](https://spk.gov.tr/spk-bultenleri/2026-yili-spk-bultenleri)
46. [KAP \*\*\* SERMAYE PİYASASI KURULU \*\*\* SPK Bülteni](https://www.yenisafak.com/ekonomi/kap-haberleri/kap-sermaye-piyasasi-kurulu-spk-bulteni-5100077)
47. [Resmi Gazetede Yayımlanan Kurul Kararları](https://www.bddk.org.tr/Mevzuat/Liste/55)
48. [Resmi Gazetede Yayımlanmayan Kurul Kararları](https://www.bddk.org.tr/Mevzuat/Liste/56)
49. [Konut Kredilerine İlişkin 24.08.2023 tarihli 10655 ve 10656 ...](https://www.bddk.org.tr/Duyuru/Detay/2039)
50. [Bültenler](https://www.turkpatent.gov.tr/bultenler)
51. [Sayı 215 Yayım Tarihi 16.02.2026 - Web-IM](https://webim.turkpatent.gov.tr/file/8384d6be-3eb4-4564-97b8-8426e7f86c9b?download=&name=215)
52. [GitHub - erenizgi/yargi-mcp: Fork of MCP Server For Turkish Legal Databases · GitHub](https://github.com/erenizgi/yargi-mcp)
53. [Yargı MCP by saidsurucu](https://glama.ai/mcp/servers/saidsurucu/yargi-mcp)
54. [GSÜ Suna Kıraç Kütüphanesi - GSU Veritabanları](https://kutuphane.gsu.edu.tr/tr/e-kaynaklar/gsu-veritabanlari)
55. [LEXI AI](https://www.lexpera.com.tr/lexi-yapay-zeka)
56. [LEXPERA Yeni Nesil Hukuk Bilgi Sistemi Veritabanı erişime açılmıştır.](https://kutuphane.aku.edu.tr/2023/01/02/lexpera-yeni-nesil-hukuk-bilgi-sistemi-veritabani-erisime-acilmistir/)
57. [Yeni Veritabanı - LEXPERA Hukuk Bilgi Sistemi](https://kddb.kastamonu.edu.tr/index.php/component/content/article/yeni-veritabani-lexpera-hukuk-bilgi-sistemi?catid=12&Itemid=214)
58. [Karar (İçtihat) Arama - Türk Hukuk Kaynakları - LibGuides at Koç University](https://libguides.ku.edu.tr/TurkHukuku/ictihat)
59. [LEXPERA - Ücretsiz Öğrenci Üyeliği](https://www.lexpera.com.tr/uyelik-destek/ogrenci)
60. [Veri Tabanı - Hukuk - LibGuides at Özyeğin University](https://ozyegin.libguides.com/c.php?g=701616&p=5042193)
61. [UYAP Mevzuat - Google Play'de Uygulamalar](https://play.google.com/store/apps/details?id=tr.gov.uyap.mevzuat&hl=en_US)
62. [2026 Yılı Güncel Tutarlar](https://ms.hmb.gov.tr/uploads/2026/01/Ek-4-BKS_2026_YDO_GUNCEL.TUTARLAR-5d367d135f56b5e2.pdf)
63. [İstinaf Sınırı 2026: Kesinlik ve İstinafa Kapalı Kararlar](https://hukukcularevi.com/istinaf-kesinlik-siniri-2026-hangi-kararlara-istinaf-kapali/)
64. [2026 İstinaf, Temyiz ve Senetle İspat Sınırı](https://smarthukuk.com/blog/2026-yargida-parasal-sinirlar-istinaf-temyiz)
65. [2026 YILI PARASAL SINIRLAR](https://www.mychukuk.com/post/parasal-s%C4%B1n%C4%B1rlar-2026)
66. [HMK Madde 362 - Temyiz edilemeyen kararlar](https://av-saimincekas.com/kanun/hukuk-muhakemeleri-kanunu/madde-362-hmk/)
67. [2026 Yargıda Parasal Sınırlar - Konya Avukat Sami Işılak](https://samiisilak.av.tr/makaleler/2026-yargida-parasal-sinirlar)
68. [Kıdem Tazminatı](https://www.verginet.net/dtt/1/kidem-tazminati-tavani.aspx)
69. [Kıdem Tazminatı Tavanı 1/7/2026  31/12/2026 Dönemi için 73.729,87 TL Olarak Belirlendi - Verginet](https://www.verginet.net/dtt/11/sgk-2026-23.aspx)
70. [2026 Kıdem Tazminatı Tavanı: 73.729,87 TL](https://prozon.net/kidem-tazminati-tavani/)
71. [2026 YILINDA GEÇERLİ OLACAK ASGARİ ÜCRET BRÜT 33.030,00 TL, NET 28.075,50 TL OLARAK BELİRLENDİ](https://www.vizyongrubu.com/tr/sirkuler/2026-yilinda-gecerli-olacak-asgari-ucret-brut-3303000-tl-net-2807550-tl-olarak-belirlendi/)
72. [2026 Asgari Ücret Ne Kadar? Net 28.075,50 TL, Brüt 33.030,00 TL (Resmî Gazete)](https://uzmanmuhasebe.net/mevzuat/2026-asgari-ucret/)
73. [Resmi Gazete ne zaman ve saat kaçta yayınlanıyor? Resmi Gazete nedir?](https://www.haberturk.com/resmi-gazete-ne-zaman-yayinlaniyor-resmi-gazete-saat-kacta-aciklaniyor-ve-resmi-gazete-nedir-3597677)
74. [Resmî Gazete Görüntüleyici 2026](https://sevdasahin.com/resmi-gazete)
75. [AÖF ADL102U Hukuk Dili ve Adli Yazışmalar Ders Notları](https://afyonluoglu.org/PublicWebFiles/AOF-ADALET/ders-notlari/DONEM_2/Hukuk%20Dili%20-%20%C3%96zet%202022.pdf)
76. [AVRUPA İNSAN HAKLARI MAHKEMESİ](https://hudoc.echr.coe.int/app/conversion/docx/pdf?library=ECHR&id=001-200593&filename=CASE+OF+ERDO%C4%9EAN+AND+OTHERS+v.+TURKEY+-+%5BTurkish+Translation%5D+by+the+Turkish+Ministry+of+Justice.pdf&logEvent=False)
77. [Temyiz Sınırı 2026: 682.000 TL](https://hukukcularevi.com/temyiz-siniri-2026-yargitaya-hangi-kararlar-goturulur/)
