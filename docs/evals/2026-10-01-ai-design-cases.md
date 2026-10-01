# In-site AI — layout & design test cases

**Purpose:** a fixed set of real requests to measure the in-site Gemini pipeline (editor AI Refine, new section, element refine, site assistant / Home chat) **before and after** the AI design pipeline work, and later to compare other models with the same yardstick.

**Site:** `demo-ai-lab` — a local demo copy of `checkinfaro-v3` (restaurant, editorial look; PT default + EN; 6 pages with sliders, galleries and a marquee), created 2026-10-01 for these runs. Uploads go to its own `demo-ai-lab` storage folder; no deploy, no sync. Client sites are never used for evals. Requests are written the way the operator writes them (Portuguese).

**How a run works:** every case goes through the same endpoints the editor and the Home chat call. The demo database is restored from a snapshot before each case, so cases don't affect each other. Each produced section is rendered in the real page in the browser and screenshotted at 1440 px and 390 px.

**Scoring per case**
- **Automatic checks** (pass/fail, listed per case). Always also:
  - **A1** the call succeeds (no exception, no "possible truncation");
  - **A2** every `<section>` keeps a unique `data-section` + matching `id`;
  - **A3** every language is updated and `check_site --only dom-parity,sections,links,components` passes (internal links carry the language prefix of their copy);
  - **A4** classes come from the site's design (theme tokens / classes already used on the site), not generic defaults like `bg-blue-500`;
  - **A5** nothing outside the target changed.
- **Design score** (operator, 1–5): looks like it belongs to the site · clearly does what was asked · has some craft (rhythm, hierarchy, detail) · works on mobile.
- **Cost:** seconds and tokens per case.

---

## Part 1 — 10 normal use cases (one request each)

| # | Site · page · target | Path | Request | Case-specific checks |
|---|---|---|---|---|
| N1 | demo · home · `conceito` | Editor · refine section | "Passa esta secção para duas colunas: texto à esquerda, foto à direita. No telemóvel a foto fica por cima." | 2-column grid ≥ md, image before text in DOM order or `order-*` for mobile; same text kept |
| N2 | demo · home · `testemunhos` | Editor · refine section | "Torna os testemunhos mais elegantes: aspas grandes, fundo creme e o nome do autor mais discreto." | still a Splide text slider recognised by the component panel (`components.audit` clean, same slide count) |
| N3 | demo · home · after `carta` | Editor · new section | "Acrescenta uma secção com o horário e o mapa (Google Maps), no estilo do resto do site." | new unique `data-section`; iframe map; hours taken from the site's contact data, not invented |
| N4 | demo · proposta-2 · after `chef` | Editor · new section | "Acrescenta uma galeria de 6 fotos de pratos da biblioteca de imagens, que abram em grande ao clicar." | 6 images from the media library (site storage URLs, not placeholders); lightbox gallery shape recognised by the panel |
| N5 | demo · home · `hero` "Reservar mesa" button | Editor · refine element | "Dá mais destaque a este botão, na cor principal da marca." | only that element changes; colour is the brand token/class, not a hard-coded hex unless the site does so |
| N6 | demo · proposta-1 · `pilares` | Editor · refine section | "Simplifica: só 3 pilares lado a lado, com um ícone simples cada e menos texto." | exactly 3 items; text shortened, meaning kept |
| N7 | demo · home · `fotos` | Editor · refine section | "No telemóvel esta grelha de fotos fica muito alta. Mostra 2 colunas e fotos mais baixas." | desktop unchanged; mobile 2 columns, smaller heights; same images |
| N8 | demo · reservas · before `contactos` | Assistant (Home chat) | "Na página Reservas, acrescenta uma secção de perguntas frequentes com 5 perguntas sobre reservas de grupos, antes dos contactos." | inserted before `contactos` (not appended at the end); accordion component; translated to EN |
| N9 | demo · proposta-2 · `carta` | Editor · refine section | "Mostra os pratos da carta em cartões com foto, nome e preço, 3 por linha." | 3-column card grid; existing dish names kept; prices not invented (placeholder marked); photos from the media library |
| N10 | demo · reservas · after `grupos` | Editor · new section | "Acrescenta uma secção com 3 menus de grupo, com o mesmo estilo dos cartões da secção eventos da página inicial." | reuses the card classes of `home › eventos` (cross-page context) |

---

## Part 2 — 10 conversations (memory and follow-ups)

Each conversation is one chat session (editor AI panel or Home assistant, as marked). The checks focus on whether later turns build on earlier ones.

| # | Path | Turns | What must be remembered / checks |
|---|---|---|---|
| C1 | Editor panel · demo · proposta-2 · `sala` | 1) "Redesenha esta secção, quero ver 3 propostas." → *operator applies option 2* · 2) "Gosto desta, mas com fundo escuro." | turn 2 starts from the **applied option 2**, not from the original section (its distinctive structure is still there) |
| C2 | Editor panel · demo · home | 1) on `conceito`: "Títulos com letra serifada grande e um traço dourado por baixo." · 2) on `chef`: "Aplica o mesmo estilo de título a esta secção." · 3) on `eventos`: "E nesta também, o mesmo estilo de título." (the editor targets one section per request) | turn 2 reuses the **same classes** created in turn 1 on both sections |
| C3 | Assistant · demo | 1) "Que secções tem a página inicial?" · 2) "Remove a quinta." | resolves "a quinta" from its own list in turn 1 (`galeria`); **asks for confirmation** before a destructive removal |
| C4 | Assistant · demo · reservas | 1) "Põe a foto do topo da página Reservas a ocupar o ecrã inteiro." · 2) "Não, volta atrás e só aumenta o tamanho do título." | turn 2 restores the turn-1 change (checkpoint/undo), then makes only the title change |
| C5 | Assistant · demo | 1) "Muda a cor dos botões." · 2) "Em todas as páginas, para o dourado da marca." | turn 1 **asks** which page/buttons instead of guessing; turn 2 applies the brand token everywhere, nothing else changes |
| C6 | Assistant · demo · proposta-2 · `manifesto` | 1) "Acrescenta uma frase no manifesto: 'Cozinha de mercado desde 2014'." · 2) "E em inglês como ficou?" · 3) "Muda para 'Market cuisine since 2014'." | turn 2 reads the EN copy back; turn 3 changes **only EN**, PT intact |
| C7 | Editor panel · demo · home · `eventos` | 1) "Quero 3 cartões: casamentos, empresas, aniversários." · 2) "Os cartões estão muito altos." · 3) "Põe uma foto em cada um, da biblioteca de imagens." | final result keeps **all three constraints**: 3 cards, compact, real photos |
| C8 | Assistant · demo | 1) "Para este site prefiro sempre fundos claros e sem sombras." · 2) "Cria uma secção de newsletter antes do rodapé na página inicial." · 3) "Agora uma de prémios na proposta-3." | turns 2 and 3 both respect the stated preference (light backgrounds, no `shadow-*`) |
| C9 | Assistant · demo · proposta-3 | 1) "Na proposta-3, põe a secção de reconhecimento numa faixa horizontal." · 2) "Já agora, qual é o título SEO dessa página?" · 3) "Volta à faixa do reconhecimento e põe os logótipos a preto e branco." | turn 2 answers from the page's SEO fields; turn 3 targets the **same `reconhecimento` section** after the detour |
| C10 | Assistant · demo | 1) "Tira a galeria." · 2) "Não, a da página proposta-1, não a da página inicial." | turn 1 asks which (two pages have `galeria`) or targets none; after turn 2 only proposta-1 changes and the home gallery is intact |


---

## Part 3 — assistant tools (phase 4)

Added 2026-10-01 with `docs/plans/2026-10-01-assistant-tools-design.md`. All on the Home chat; run on `demo-ai-eval`. Emails go to the runner's in-memory outbox, never out.

| # | Turns | Checks |
|---|---|---|
| N11 | "Na proposta-2, no slider do foie gras, põe a foto da equipa a empratar em primeiro." | `list_components` → `reorder_items`, no AI refine; `foto-foie` keeps 6 slides in PT and EN with the team photo first; nothing else changes |
| N12 | 1) "Na página Reservas, procura uma foto melhor para o fundo do topo: algo com a sala do restaurante." · 2) *operator clicks the first thumbnail* ("Usa a foto <ref>") | turn 1 calls `find_photos` and shows candidates (library and/or Unsplash) without changing the page; turn 2 changes only `reservas-hero`, in PT and EN, keeping the overlay |
| N13 | "Testa o formulário de reservas." | `test_form`: every email goes only to the operator with `[TESTE]` in the subject; no submission left behind; the reply reports each step |
| N14 | "Verifica se os contactos do site estão certos." | `validate_contacts`; reports the landline used on the pages vs the mobile in Settings, with where; changes nothing |
| C11 | 1) "Na página Reservas, muda o fundo do topo para outra foto da biblioteca, à tua escolha." · 2) "Desfaz isso." | turn 2 calls `undo_last_change`; every page is **byte-identical** to the start |
| C12 | 1) the N8 request (FAQ before the contacts) · 2) *operator clicks "Undo this"* | turn 1 uses `insert_section` (only the new section appears, in PT and EN); after the undo every page is byte-identical to the start |

N8 and C8 are re-run with the phase 4 code: adding a section must no longer re-translate the other sections.

---

## Expected baseline (before the work)

From reading the code, these will likely fail today for plumbing reasons, independent of model quality:
- **Section refines (N1, N2, N6, N7, N9, C1, C2, C7):** rejected by the 50 % length check that compares one section with the whole page.
- **Element refine (N5):** at risk of nesting the section into the element.
- **N8:** the assistant has no insert-section tool.
- **Assistant layout changes:** stay in the default language only.
- **C1:** the editor history never records which option was applied.

Record the baseline anyway: it is the "before" column.
