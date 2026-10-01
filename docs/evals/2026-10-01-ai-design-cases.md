# In-site AI — layout & design test cases

**Purpose:** a fixed set of real requests to measure the in-site Gemini pipeline (editor AI Refine, new section, element refine, site assistant / Home chat) **before and after** the AI design pipeline work, and later to compare other models with the same yardstick.

**Sites:** `checkinfaro-v3` (restaurant, editorial look; PT default + EN) and `quinta-do-rogel` (rural tourism, different design system; PT + EN). Requests are written the way the operator writes them (Portuguese).

**How a run works:** every case runs against the real site inside a rolled-back transaction, or on a page restored from a snapshot afterwards; nothing stays in the site. Each produced section is rendered in the real page in the browser and screenshotted at 1440 px and 390 px.

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
| N1 | checkinfaro-v3 · home · `conceito` | Editor · refine section | "Passa esta secção para duas colunas: texto à esquerda, foto à direita. No telemóvel a foto fica por cima." | 2-column grid ≥ md, image before text in DOM order or `order-*` for mobile; same text kept |
| N2 | checkinfaro-v3 · home · `testemunhos` | Editor · refine section | "Torna os testemunhos mais elegantes: aspas grandes, fundo creme e o nome do autor mais discreto." | still a Splide text slider recognised by the component panel (`components.audit` clean, same slide count) |
| N3 | checkinfaro-v3 · home · after `carta` | Editor · new section | "Acrescenta uma secção com o horário e o mapa (Google Maps), no estilo do resto do site." | new unique `data-section`; iframe map; hours taken from the site's contact data, not invented |
| N4 | checkinfaro-v3 · proposta-2 · after `chef` | Editor · new section | "Acrescenta uma galeria de 6 fotos de pratos da biblioteca de imagens, que abram em grande ao clicar." | 6 images from the media library (site storage URLs, not placeholders); lightbox gallery shape recognised by the panel |
| N5 | checkinfaro-v3 · reservas · `reservas-hero` main button | Editor · refine element | "Dá mais destaque a este botão, na cor principal da marca." | only that element changes; colour is the brand token/class, not a hard-coded hex unless the site does so |
| N6 | checkinfaro-v3 · proposta-1 · `pilares` | Editor · refine section | "Simplifica: só 3 pilares lado a lado, com um ícone simples cada e menos texto." | exactly 3 items; text shortened, meaning kept |
| N7 | checkinfaro-v3 · home · `fotos` | Editor · refine section | "No telemóvel esta grelha de fotos fica muito alta. Mostra 2 colunas e fotos mais baixas." | desktop unchanged; mobile 2 columns, smaller heights; same images |
| N8 | checkinfaro-v3 · reservas · before `contactos` | Assistant (Home chat) | "Na página Reservas, acrescenta uma secção de perguntas frequentes com 5 perguntas sobre reservas de grupos, antes dos contactos." | inserted before `contactos` (not appended at the end); accordion component; translated to EN |
| N9 | quinta-do-rogel · vinhos · `the-range` | Editor · refine section | "Mostra os vinhos em cartões com foto, nome, casta e preço, 3 por linha." | 3-column card grid; existing wine names/images kept; prices not invented (placeholder marked) |
| N10 | quinta-do-rogel · picadeiro · after `for-guests-and-riders` | Editor · new section | "Acrescenta uma secção de preços das aulas (3 pacotes) com o mesmo estilo dos cartões dos apartamentos." | reuses the card classes from `apartamentos › apartment-types` (cross-page context) |

---

## Part 2 — 10 conversations (memory and follow-ups)

Each conversation is one chat session (editor AI panel or Home assistant, as marked). The checks focus on whether later turns build on earlier ones.

| # | Path | Turns | What must be remembered / checks |
|---|---|---|---|
| C1 | Editor panel · checkinfaro-v3 · proposta-2 · `sala` | 1) "Redesenha esta secção, quero ver 3 propostas." → *operator applies option 2* · 2) "Gosto desta, mas com fundo escuro." | turn 2 starts from the **applied option 2**, not from the original section (its distinctive structure is still there) |
| C2 | Editor panel · checkinfaro-v3 · home | 1) on `conceito`: "Títulos com letra serifada grande e um traço dourado por baixo." · 2) "Agora aplica o mesmo estilo de título às secções chef e eventos." | turn 2 reuses the **same classes** created in turn 1 on both sections |
| C3 | Assistant · checkinfaro-v3 | 1) "Que secções tem a página inicial?" · 2) "Remove a quinta." | resolves "a quinta" from its own list in turn 1 (`galeria`); **asks for confirmation** before a destructive removal |
| C4 | Assistant · checkinfaro-v3 · reservas | 1) "Põe a foto do topo da página Reservas a ocupar o ecrã inteiro." · 2) "Não, volta atrás e só aumenta o tamanho do título." | turn 2 restores the turn-1 change (checkpoint/undo), then makes only the title change |
| C5 | Assistant · checkinfaro-v3 | 1) "Muda a cor dos botões." · 2) "Em todas as páginas, para o dourado da marca." | turn 1 **asks** which page/buttons instead of guessing; turn 2 applies the brand token everywhere, nothing else changes |
| C6 | Assistant · checkinfaro-v3 · proposta-2 · `manifesto` | 1) "Acrescenta uma frase no manifesto: 'Cozinha de mercado desde 2014'." · 2) "E em inglês como ficou?" · 3) "Muda para 'Market cuisine since 2014'." | turn 2 reads the EN copy back; turn 3 changes **only EN**, PT intact |
| C7 | Editor panel · checkinfaro-v3 · home · `eventos` | 1) "Quero 3 cartões: casamentos, empresas, aniversários." · 2) "Os cartões estão muito altos." · 3) "Põe uma foto em cada um, da biblioteca de imagens." | final result keeps **all three constraints**: 3 cards, compact, real photos |
| C8 | Assistant · checkinfaro-v3 | 1) "Para este site prefiro sempre fundos claros e sem sombras." · 2) "Cria uma secção de newsletter antes do rodapé na página inicial." · 3) "Agora uma de prémios na proposta-3." | turns 2 and 3 both respect the stated preference (light backgrounds, no `shadow-*`) |
| C9 | Assistant · quinta-do-rogel · vinhos | 1) "Na página dos vinhos, põe os prémios numa faixa horizontal." · 2) "Já agora, qual é o título SEO dessa página?" · 3) "Volta à faixa dos prémios e põe os logótipos a preto e branco." | turn 2 answers from the page's SEO fields; turn 3 targets the **same `awards` section** after the detour |
| C10 | Assistant · checkinfaro-v3 | 1) "Tira a galeria." · 2) "Não, a da página proposta-1, não a da página inicial." | turn 1 asks which (two pages have `galeria`) or targets none; after turn 2 only proposta-1 changes and the home gallery is intact |

---

## Expected baseline (before the work)

From reading the code, these will likely fail today for plumbing reasons, independent of model quality:
- **Section refines (N1, N2, N6, N7, N9, C1, C2, C7):** rejected by the 50 % length check that compares one section with the whole page.
- **Element refine (N5):** at risk of nesting the section into the element.
- **N8:** the assistant has no insert-section tool.
- **Assistant layout changes:** stay in the default language only.
- **C1:** the editor history never records which option was applied.

Record the baseline anyway: it is the "before" column.
