# Volunteer Opportunity Sources (research, 2026-10-04)

> Local examples use the San Francisco Bay Area as an example region; nothing here is specific to a person, and every adapter considered would be region-agnostic. Claims were checked on 2026-10-04 and decay: re-verify terms, robots.txt and API docs before building anything.

Research only. No code written, no accounts created, no keys requested, no forms submitted. Only public pages, robots.txt files, sitemaps and a handful of single public page GETs (identifying UA `research-check`) were read.

## 1. Summary and recommendation

- **READY (safe to automate today): none.** No source in scope offers an official public, unauthenticated, free API or feed with documented terms that permit automated use.
- **Best candidate: Grassroots Ecology event calendar** (Palo Alto / Cupertino / Menlo Park habitat-restoration volunteer days, all ages with guardian waiver for under 18). It is the only source verified to have: robots.txt allowing generic crawlers on the HTML pages, a sitemap listing every event URL, and schema.org `Event` JSON-LD on each event page (start/end/location). Automation rank 3. Free, no auth, no card. Weaknesses: JSON-LD has no description and no stable numeric ID (use URL path), age text is only in body prose, and the site's terms of use were not found (404 at `/terms`) so terms stance is **unverified**.
- **Second candidate: Galaxy Digital tenant sites** (verified on Save The Bay, `volunteer.savebay.org`). Public HTML list and detail pages with a stable `need_id`, free-text description, an explicit age field ("8 and older", "Age 16+") and family-friendly/outdoors flags. Automation rank 4 (bounded HTML parser). Weaknesses: no sitemap, no JSON-LD, Galaxy Digital's own terms **unverified**, and each tenant has its own robots.txt. The official Galaxy Digital API needs an organization-issued key (unverified specifics), so it is not usable by an outside party.
- **Aggregators are closed.** Idealist/VolunteerMatch (also powers California Volunteers search) forbids bots in its Terms of Service and its API is partner/syndication only. Points of Light Engage API is partner-only. Both REJECT.
- **Federal:** Volunteer.gov has a public sitemap with stable opportunity IDs and permissive robots, but pages are a JavaScript shell (rank 5, browser automation, needs explicit owner approval) and no API was found. MANUAL-MONITOR.
- Most high-value teen STEM/health/museum programs (Tech Interactive, Exploratorium, CHM, Lawrence Hall, Stanford Health Care, El Camino Health, Valley Medical Center, SFPL, SJPL, FIRST) are static pages or application cycles with a handful of roles. They are best handled as a curated, owner-reviewed "manual monitor" list with periodic link/last-checked review, not scraped.
- **Cost/access:** everything recommended is $0, no account, no card. Nothing requires a partner agreement.
- **Recommended next step:** build one narrow adapter for Grassroots Ecology (sitemap + JSON-LD), after owner reviews and confirms it is OK with the site's terms (ask by email if desired). Then a Galaxy Digital adapter limited to explicitly allowlisted tenant hosts. See section 6.

## 2. Method

- Searched the web for official pages (WebSearch) and fetched official pages, robots.txt, sitemaps and terms (WebFetch). Where WebFetch returned an AI summary of a page, claims are only as strong as that summary; claims I confirmed by fetching raw bytes with curl/PowerShell are marked "raw-verified".
- For candidate sources I did single GETs of robots.txt, a sitemap, a listing page and one detail page. No crawling, no form submission, no login.
- "Unverified" means I could not find or read the official statement. I did not guess.
- Terms stance reads: Idealist ToS fetched directly. Better Impact terms were only seen via a third-party clause aggregator (secondary evidence, flagged). Other platforms' terms were not located.
- Classification: READY = official API/feed + permissive documented terms, can build now; PROMISING = technically feasible at rank 3-4 with robots allowing it, pending owner review of terms; MANUAL-MONITOR = useful but not safely automatable (JS-only, few listings, login, application cycles, or terms unverified); REJECT = terms prohibit it, partner/paid gate, or not a listing source.

## 3. Classification table

| Source | Access | Auth / cost | Stable IDs | Teen / age data | Closure semantics | Class |
|---|---|---|---|---|---|---|
| Idealist (incl. VolunteerMatch) | Website; API for partners only | Partner contact; pricing not published | URL contains 32-hex ID | Not structured (unverified) | Unverified | REJECT |
| California Volunteers search | Embeds Idealist search | n/a (inherits Idealist) | via Idealist | via Idealist | via Idealist | REJECT |
| Points of Light Engage | Search API/white label for partners | Contact required | unverified | none seen | unverified | REJECT |
| Volunteer.gov (federal) | Sitemap + JS Salesforce site | None; free | Yes (`a093...` Salesforce ID in URL) | Not seen; NPS says under 18 needs guardian signature | Sitemap lastmod; removal semantics unverified | MANUAL-MONITOR |
| Recreation.gov RIDB | Documented API | Key required (unverified details) | n/a | n/a | n/a | MANUAL-MONITOR (no volunteer endpoint verified) |
| data.americorps.gov | Socrata SODA API | Free (token optional, unverified) | dataset rows | n/a | n/a | REJECT (research datasets, no opportunity listing found) |
| my.americorps.gov / Serve.gov | HTML search; no API found | Free | `viewListing.do?id=` | Not verified | Unverified | MANUAL-MONITOR |
| Grassroots Ecology events | HTML + JSON-LD Event; sitemap | None; free | URL path (date + slug); no numeric ID in JSON-LD | Body text: all ages; under 18 guardian waiver; Grove Guardians for middle/HS | Past date; removed from sitemap | PROMISING |
| Save The Bay (Galaxy Digital) | HTML list/detail | None; free | `need_id` | Yes: "8 and older", "Age 16+" | Unverified (waitlist wording exists) | PROMISING |
| Galaxy Digital tenants (general) | HTML; org-key API | Key issued by org admin (unverified) | `need_id` | Per-opportunity age field | Unverified | PROMISING (per-tenant allowlist) |
| Better Impact (SJ city/library) | HTML public org pages | None | GUIDs in URL | Not in list view | Unverified | REJECT |
| Golden | Customer API | Customer only (unverified docs) | n/a | n/a | n/a | REJECT |
| VolunteerHub | Customer open API; PublicGood feed | Customer only | n/a | n/a | n/a | REJECT |
| HandsOn Bay Area | Calendar HTML, age filter | None | unverified | Min age 12; youth filter | Unverified | MANUAL-MONITOR |
| Golden Gate NP Conservancy | Calendar HTML + registration | None | unverified | No age policy on page | Past date | MANUAL-MONITOR |
| SFPL teens | Static page | None | none | FOG Readers 15+; YAB 16-18 | Deadline in text | MANUAL-MONITOR |
| SJPL teens | Static + Better Impact | None | none | Teens Reach 13-18 | Application cycle | MANUAL-MONITOR |
| Tech Interactive VIP | Static page | None | none | Age unverified | Monthly orientation | MANUAL-MONITOR |
| Exploratorium HS Explainer | Job listings (paid) | n/a | n/a | 15-18, work permit | Cycle | MANUAL-MONITOR (paid program, not volunteer) |
| Computer History Museum | Static; teen programs | Form | none | Grades 9-12 | Currently not accepting | MANUAL-MONITOR |
| Lawrence Hall of Science | Static page | None | none | Teen program | Cycle | MANUAL-MONITOR |
| Stanford Health Care | Static page | Application + background check | none | 16+ general; 18+ inpatient | Cycle | MANUAL-MONITOR |
| El Camino Health | Static page | Annual seminar | none | 14+ (completed 8th grade) | Annual cycle | MANUAL-MONITOR |
| Valley Medical Center | Static page | Paper application | none | 15+ | Rolling | MANUAL-MONITOR |
| FIRST (firstinspires.org) | Login-gated registration | Account | none | unverified | Event date | MANUAL-MONITOR |
| Girls Who Code / Black Girls Code | Chapter pages | Varies | none | unverified | n/a | MANUAL-MONITOR |
| Boys & Girls Clubs SV / YMCA SV | Org pages | Contact | none | unverified | n/a | MANUAL-MONITOR |
| Santa Clara Co. / SM Co. / city portals | Various HTML | Account to apply | none | San Mateo city: under 18 with guardian permission | n/a | MANUAL-MONITOR |

Counts: READY 0; PROMISING 3 rows (2 distinct sources: Grassroots Ecology; Galaxy Digital tenants incl. Save The Bay); MANUAL-MONITOR 20 rows; REJECT 6 rows.

## 4. Per-source notes

### Idealist and VolunteerMatch
- Merger announced 2025-01-14; the two platforms were combined by 2025-09-08, with volunteer and job features at idealist.org (https://www.idealist.org/en/about/volunteermatch-and-idealist-are-now-one-platform , https://www.idealist.org/en/about/idealist-and-volunteermatch-announce-merger).
- API: the "VolunteerMatch, powered by Idealist" page lists API, Search Module, Volunteer Engagement Pages and CSR Partners; access is via a general inquiry form; a separate "Activate a New Client" form is for a named partner team; no pricing or public docs on the page (https://www.idealist.org/volunteermatch-api-groundswell). Treat as partner gated.
- Terms: the Terms of Service prohibit "spiders, robots, scrapers, crawlers ... data mining tools", and forbid to "scrape, copy, republish, license or sell the data or information on the Services" (https://www.idealist.org/en/terms-of-service). robots.txt only disallows third-party-login paths and points to `https://www.idealist.org/sitemap.xml` (https://www.idealist.org/robots.txt), but the ToS controls.
- Verdict REJECT. California Volunteers' volunteer search is "powered by Idealist" (https://www.californiavolunteers.ca.gov, per search results), so the same restriction applies.

### Volunteer.gov and Recreation.gov RIDB
- robots.txt: allows all, blocks only a password-reset path; sitemap at `https://www.volunteer.gov/s/sitemap.xml` (https://www.volunteer.gov/robots.txt).
- Sitemap index has four child sitemaps including `sitemap-volunteer_opportunity__c-1.xml`, which lists 1,000+ opportunity URLs of the form `/s/volunteer-opportunity/<18-char Salesforce ID>/<slug>` with ISO lastmod (https://www.volunteer.gov/s/sitemap.xml and child sitemap). The Salesforce ID is a stable opportunity ID.
- A detail page returned only a JavaScript shell with no opportunity fields (https://www.volunteer.gov/s/volunteer-opportunity/a093d000000ZuG7AAK/volunteer-map-editor). Plain HTTP parsing is not viable; headless browser needed (rank 5, needs owner approval).
- No public Volunteer.gov API or terms-of-use page found (`/s/terms-of-use` 404). Relationship with RIDB: RIDB is a documented API for recreation sites (activities, facilities, events, tours, etc., per search summary) and I found no volunteer endpoint; RIDB docs page did not render, so key/rate-limit details are **unverified** (https://ridb.recreation.gov/docs).
- Age: NPS guidance seen via search says youth under 18 need parent/guardian signature (e.g. https://www.nps.gov/obed/getinvolved/volunteer.htm); Volunteer.gov itself has no verified age field.
- Verdict MANUAL-MONITOR. Federal Bay Area content (NPS Golden Gate, Point Reyes, refuges) overlaps Conservancy listings.

### AmeriCorps, Serve.gov, data.americorps.gov
- data.americorps.gov is a Socrata portal with Catalog, Datasets (SODA) and Metadata APIs (https://data.americorps.gov ; https://providers.apievangelist.com/providers/americorps/). Datasets seen are research/survey data (e.g. member exit survey, civic engagement supplement). I found no dataset of volunteer opportunities. Terms page not read: **unverified**.
- my.americorps.gov has public listing search (`publicRequestSearch.do`, `viewListing.do?id=`) for national service positions, which are AmeriCorps member service rather than ad hoc volunteering (https://my.americorps.gov/mp/listing/publicRequestSearch.do). americorps.gov returned 403 to my fetch; robots **unverified**.
- Serve.gov: no API found.
- Verdict: data portal REJECT for this purpose; listing search MANUAL-MONITOR.

### California Volunteers
- Search is powered by Idealist; CaliforniansForAll is an email/network sign-up; Youth Service Corps are programs (https://www.californiavolunteers.ca.gov/youth-jobs-corps-interest-form/). No API found. REJECT (inherits Idealist), but Youth Service Corps is worth owner awareness.

### Points of Light Engage
- Catalog of ~300,000 opportunities from 40+ partner platforms; search API and white-label offered to partners, "contact us" for details (https://engage.pointsoflight.org/faqs). robots.txt blocks only admin and login (https://engage.pointsoflight.org/robots.txt), no sitemap. Terms of use not read: **unverified**. A search result says Galaxy Digital acquired Engage; I could not confirm from an official page: **unverified**.
- Verdict REJECT (API is partner gated).

### Volunteer-management platforms (Galaxy Digital, Golden, VolunteerHub, Better Impact)
- Better Impact acquired Galaxy Digital per trade press (https://www.nonprofitpro.com/article/better-impact-acquires-galaxy-digital-to-expand-its-volunteer-tech/).
- **Galaxy Digital tenant sites.** Raw-verified on `volunteer.savebay.org`: `/need/` lists opportunities with `need_id=` links; detail pages include full description, registration notes, "Age requirements", a details block ("8 and older", "Is Family Friendly", "Is Outdoors", team size). No JSON-LD (0 blocks). robots.txt disallows many named SEO/scraper bots and sets Bingbot crawl-delay 10; generic agents not blocked (https://volunteer.savebay.org/robots.txt). No sitemap (404). Galaxy Digital's terms were not found: **unverified**. An org-issued API exists but its documentation page is blocked (`api.galaxydigital.com` 403): **unverified**.
- **Golden:** marketing page says a "flexible API" with documentation and support, access terms not public (https://goldenvolunteer.com/platform/api/). Customer-side. REJECT.
- **VolunteerHub:** "open API" for customers; PublicGood feed for customers (https://support.volunteerhub.com/support/solutions/articles/60001287143-publicgood). Not an outside-party feed. REJECT.
- **Better Impact:** SJ city and SJPL publish Better Impact public organization pages (e.g. https://app.betterimpact.com/PublicOrganization/972f1f4f-9417-4fb5-9865-8f141718713d/2) with activity GUIDs and shift counts, no age or description in list view. robots.txt only blocks system paths (https://app.betterimpact.com/robots.txt). A third-party terms aggregator quotes Better Impact terms as prohibiting "automated scripts to collect information" and "data mining, robots or similar data gathering" (secondary source, search result https://conductatlas.com/platform/impact/impact-terms-and-conditions/). Conservatively REJECT until the official terms are read.

### Grassroots Ecology (best candidate)
- robots.txt (raw-verified): `User-agent: *` disallows `?format=json`, `?format=ical`, `?format=page-context` etc. query variants but not event pages; sitemap at https://www.grassrootsecology.org/sitemap.xml (https://www.grassrootsecology.org/robots.txt). Named AI crawlers (e.g. ClaudeBot, GPTBot) are separately disallowed. So the Squarespace JSON/iCal variants must NOT be used; use sitemap + page HTML only, with an honest, non-AI-crawler user agent and a delay.
- Sitemap (raw-verified): 764 `event-calendar/YYYY/MM/DD/slug` URLs (includes past events); dates are in the path.
- Event page JSON-LD (raw-verified, e.g. https://www.grassrootsecology.org/event-calendar/2026/10/11/volunteer-at-mcclellan-ranch-preserve-in-cupertino): `@type Event`, `name`, `startDate` with offset, `endDate`, `location` (Place name + address). No `description`, no price/offers, no numeric ID.
- Body text states: all participants must register individually and approve the online waiver through an Eventbrite page; youth under 18 need guardian waiver approval; ages 12 and under need an accompanying adult (search summary https://www.grassrootsecology.org/event-calendar/2026/02/25/volunteer-at-arastradero-with-post). Grove Guardians is a middle/high-school program.
- Closure: past `startDate`, or URL absent from sitemap. Remote: no (in-person). Rate limits: none stated; Squarespace.
- STEM fit: environmental service/field ecology, good for a high-school senior. Terms of use: **unverified** (`/terms` 404).

### Save The Bay
- Restoration and cleanup events via Galaxy Digital (above). Age rule: 16+ independent; under 16 with guardian; restoration under 18 signed in by guardian (https://volunteer.savebay.org/youth-volunteering, search summary; main site calendar at https://savesfbay.org/calendar/ whose robots.txt has `Crawl-delay: 10` and `Disallow:` empty, https://savesfbay.org/robots.txt). Per-event age text confirmed on a need detail page (raw-verified).

### Golden Gate National Parks Conservancy
- Volunteer calendar filterable by county with registration buttons; no RSS/iCal/JSON/schema.org seen; robots blocks admin/search and has no sitemap (https://www.parksconservancy.org/volunteer , https://www.parksconservancy.org/robots.txt). Youth policy PDF exists (https://www.parksconservancy.org/sites/default/files/youth-policy-guidelines.pdf); a program page notes Teens on Trails 15+ and guardian approval under 18 (search result). MANUAL-MONITOR; rank 4 would be possible but unverified markup.

### HandsOn Bay Area
- Points of Light affiliate; Community Calendar at /calendar with an age-appropriate filter; minimum age 12; HandsOn Tomorrow (HS leadership camp) and Youth Volunteer Council (https://www.handsonbayarea.org/youth). robots.txt returns 404; terms-of-use not found (404 at `/terms-of-use`); sitemap only lists static pages. Largest Bay Area general source but terms **unverified**. MANUAL-MONITOR, ask owner to contact them about a feed.

### Libraries
- SFPL: school-year volunteers (ongoing, per branch), FOG Readers literacy tutoring (15+, 6-month), Youth Advisory Board (paid, 16-18, deadline Sept 14, passed), YELL (paid, applications open in March, "support STEM and literacy activities") (https://sfpl.org/teens/volunteer-job-opportunities). Static page, no IDs.
- SJPL: Teens Reach (13-18 youth council), Teen Library Volunteer, Teen Book Reviewer (virtual, California residents), Homework Coach (https://www.sjpl.org/teensreach ; Better Impact public page above). SJPL robots allows general crawl, sitemap `https://www.sjpl.org/sitemap.xml`, no crawl-delay (https://www.sjpl.org/robots.txt), but volunteer listings live on Better Impact. MANUAL-MONITOR.

### Museums
- Tech Interactive Volunteer Innovator Program: 3-hour monthly orientation, 2 shifts/month for 6 months; minimum age unverified (https://www.thetech.org/support-us/volunteer).
- Exploratorium High School Explainers: paid ($19/hr in search listing), 15-18 first-time, work permit; applications annual (job-board listings). Not volunteer.
- Computer History Museum: grades 9-12 teen programs, currently not accepting applications, mailing-list form (https://computerhistory.org/internships/ and search result).
- Lawrence Hall of Science: teen volunteer program (https://www.lawrencehallofscience.org/support/volunteer-teen/).
- California Academy of Sciences: no teen volunteer program verified (**unverified**).
- All MANUAL-MONITOR: annual cycles, no feed.

### STEM nonprofits and youth orgs
- FIRST: volunteers register by account at firstinspires.org/community/volunteers; event roles (judges, referees, inspectors); several Bay Area FLL/FTC events also appear on Idealist (https://www.firstinspires.org/community/volunteers). Login gated, no public API found. MANUAL-MONITOR (season Nov-May; high-value STEM for the owner).
- Black Girls Code (Bay Area chapter): volunteer sign-up, programs ages 7-17 (search results only); Girls Who Code: **unverified**.
- Boys & Girls Clubs of Silicon Valley (ages 6-18, 11 San Jose clubhouses) and YMCA of Silicon Valley (teen "Get Summer"): no teen volunteer specifics verified. MANUAL-MONITOR.

### Health systems
- Stanford Health Care: min age 16 at application, 18+ inpatient, 6-month minimum with weekly shift, background check and orientation (https://stanfordhealthcare.org/for-patients-visitors/volunteering.html). Stanford Children's has its own page (https://www.stanfordchildrens.org/en/volunteer/programs.html).
- El Camino Health Junior Auxiliary: 14+ and completed 8th grade, 1-year commitment, annual application seminars (search result, https://elcaminohealth.org/node/121266).
- Santa Clara Valley Medical Center: 15+, 100 hours / 6 months, paper application (https://scvmc.scvh.org/giving-volunteering/volunteer-services).
- Kaiser: **unverified** (only a Idealist listing seen).
- All MANUAL-MONITOR: cycle-based, no feeds.

### City / county portals
- San Jose: Youth Commission 13+, Teen Centers (https://sanjoseca.gov/your-government/departments-offices/parks-recreation-neighborhood-services/get-involved). Portal is Better Impact. San Mateo city: under 18 welcome with guardian permission (https://www.cityofsanmateo.org/2309). Santa Clara County: https://www.santaclaracounty.gov/residents/volunteer-opportunities (not deeply read). SF city portal: **unverified**.

### University outreach
- Stanford CEHG outreach (2015-17 era, possibly stale) and Lawrence Hall teen program only; no feeds. MANUAL-MONITOR.

## 5. Rejected and why

| Source | Reason |
|---|---|
| Idealist / VolunteerMatch | ToS bans bots/scrapers and copying data; API is partner/syndication via inquiry form |
| California Volunteers search | Powered by Idealist; no separate API |
| Points of Light Engage | API only for partners/white label; terms unread |
| Better Impact public pages | Terms reportedly forbid automated scripts (secondary source; read official terms before reconsidering); list view lacks age/description anyway |
| Golden, VolunteerHub APIs | Customer-only APIs, no public feed |
| data.americorps.gov | Research datasets, not an opportunity listing; use only if a listing dataset appears |
| Squarespace `?format=json` / `?format=ical` on Grassroots Ecology | Explicitly disallowed in that site's robots.txt (do not use even though technically available) |

## 6. Recommended next step

1. Owner decision (no code yet): approve a prototype adapter for **Grassroots Ecology** limited to host `www.grassrootsecology.org`, path prefix `/event-calendar/`, fed by `/sitemap.xml`, parsing only `application/ld+json` Event blocks. Use the URL path as the stable external ID, `startDate` for closure (past = closed/expired), a conservative fixed delay (for example 1 request per 5 seconds) and a cap on pages per sync (only future-dated URLs from the sitemap, by date in path). Mark age as "unknown/see page" because it is not structured.
2. Optionally email Grassroots Ecology and Save The Bay (volunteer@grassrootsecology.org, volunteer@savebay.org per their pages) asking permission/preferred feed; this also resolves the unverified terms.
3. Second: Galaxy Digital adapter with a per-tenant allowlist (start with `volunteer.savebay.org`), `need_id` as external ID, parse "N and older"/"Age N+" into min age. Read Galaxy Digital terms first.
4. Everything else: a small hand-curated seed list (owner-reviewed, with `last_checked` and `next_review` dates) for FIRST events, SJPL/SFPL, museums, Stanford/El Camino/Valley Medical, HandsOn Bay Area and Volunteer.gov. This fits "manual monitor" and keeps the $0/no-partner constraint.
5. Revisit Volunteer.gov only if the owner approves rank 5 browser automation later.
