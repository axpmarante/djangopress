# Testes manuais da tab Chat do editor

Lista de pedidos para testar a tab **Chat** do editor visual à mão, com o resultado esperado. Corre-se no **demo-ai-lab**, nunca num site de cliente.

**Antes de começar**
- **Código novo:** no manager, faz **Stop** e depois **Start** do `demo-ai-lab`, para o servidor ler o código novo.
- **Cache do browser:** abre a página num separador novo; o editor pede os módulos pela versão, por isso não é preciso limpar a cache.
- **Onde testar:** abre http://localhost:8134/pt/?edit=v2, clica numa secção e abre a tab **Chat**.
- **Depois de cada teste que muda o site:** usa **Undo** (no cartão verde ou na barra de cima) para deixar o demo como estava, salvo se o teste disser outra coisa.

**Como marcar:** `[x]` passou · `[!]` passou com reparos (escreve-os por baixo) · `[ ]` falhou.

---

## 1. Cabeçalho

| ✓ | Ação | Resultado esperado |
|---|---|---|
| [ ] | Clica na secção `eventos` e abre a tab **Chat** | Mostra o chip **Section · eventos** e o seletor **Section / Page**. Por baixo aparece a linha **Matches:** com as cores do site, as duas fontes (Fraunces, Inter Tight) e "style of: …" com 2 a 3 secções. |
| [ ] | Clica num título dentro da secção | O chip passa a **Element · h2…**. O seletor mostra **Element / Section / Page**. |
| [ ] | Escreve `mais elegante` e depois `título a dourado` (sem enviar) | O rótulo junto ao clip muda entre **Auto · 3 directions** e **Auto · quick edit**. |
| [ ] | Clica no rótulo | Passa por **Quick edit**, **3 directions** e **Auto**. Quando está forçado, fica a azul. |

## 2. Pedido rápido (aplica logo)

| ✓ | Pedido (secção `eventos`) | Resultado esperado |
|---|---|---|
| [ ] | Chip **Tighter spacing** | Mostra um cartão de progresso ("Reading the request", "Saving…") e depois um cartão verde com o que mudou, "Updated EN." e **Undo**. A página **não recarrega** e a secção pisca a verde. Demora menos de 10 s. |
| [ ] | Muda para **EN** na barra de cima | A secção em inglês tem o mesmo espaçamento e mantém o texto em inglês. |
| [ ] | **Undo** no cartão verde | A página recarrega com a secção como estava, em PT e EN. |
| [ ] | `O título em vermelho da marca` com um título selecionado (Element) | Só o título muda, para a cor exata do site (um `text-[#…]`, não `text-red-600`). |

## 3. Três direções

| ✓ | Pedido (secção `chef`) | Resultado esperado |
|---|---|---|
| [ ] | Chip **✦ More elegant** | O cartão mostra **Original, A, B e C**. As três direções chegam uma a uma (a brilhar até chegarem), a primeira em cerca de 30 s e todas em cerca de 1 min. A primeira que chega aparece logo na página. |
| [ ] | Olha para as três | A = mesma estrutura, mais cuidada. B = mais contraste/presença. C = outro layout. Todas usam as cores e as fontes do site e parecem do mesmo site que o Hero e a Carta. |
| [ ] | Clica em cada mosaico e depois em **Original** | A página troca a secção pela opção escolhida. **Original** repõe a secção atual. "Why it fits" muda com a opção. |
| [ ] | Numa opção, **Compare** | Aparecem lado a lado, a metade do tamanho, **Original** e a opção, com etiquetas. **Single view** volta ao normal. |
| [ ] | **Regenerate** | Faz três direções novas para o mesmo pedido. |
| [ ] | Se aparecer "Matched to the site: …" | Lista o que foi corrigido (por exemplo, uma cor genérica trocada pela do site, ou "1 placeholder image(s)"). |

## 4. Refinar uma opção e aplicar

| ✓ | Ação | Resultado esperado |
|---|---|---|
| [ ] | Na opção B, **Refine this one…** | Por cima da caixa aparece "Refining B Bolder". O rótulo diz "New version of this option". |
| [ ] | `Gosto desta, mas com fundo escuro.` | Mostra um cartão novo com **Original, Before (B · Bolder) e New**. A versão nova parte da B, não da secção guardada. Demora cerca de 30 s. |
| [ ] | **Apply** | Mostra "✓ Applied New · Refined. Updated EN." com **Undo**. A página **não recarrega**. A barra de cima mostra "Undo AI section "chef"". A secção continua selecionada. |
| [ ] | Clica num texto da secção nova e edita-o | A edição funciona como em qualquer outra secção (o editor reconhece a secção nova). |
| [ ] | **Undo** | A secção volta ao que era, em PT e EN. |

## 5. Parar, imagens e casos de erro

| ✓ | Ação | Resultado esperado |
|---|---|---|
| [ ] | Pede `3 propostas para esta secção` e, passados 10 s, carrega no botão vermelho (ou em **Cancel**) | O cartão de progresso diz "Stopped after …". As direções que já chegaram ficam; as outras ficam "couldn't make it". Não há nada guardado. |
| [ ] | Arrasta uma imagem para a caixa (ou cola com ⌘V, ou usa o clip) | Aparece a miniatura com ✕. O rótulo passa a "Auto · 3 directions". Ao enviar, a miniatura aparece na mensagem. |
| [ ] | Tenta 6 imagens ou um PDF | Aparece um aviso ("At most 5 images" / "… is not an image") e o ficheiro não entra. |
| [ ] | Numa notícia (`/pt/news/<slug>/?edit=v2`), pedido rápido numa secção | Funciona como numa página: aplica, Undo. |
| [ ] | Seletor **Page**, `Torna a página mais compacta` | Usa o fluxo da página inteira: um mosaico **Page**, **Apply** grava e recarrega. |

## 6. Custo

| ✓ | Onde | Resultado esperado |
|---|---|---|
| [ ] | `/backoffice/ai/logs/` depois de um pedido rápido | Uma chamada `refine_routing` (flash). Nenhuma `translate_html` se só mudaram classes. |
| [ ] | Depois de **More elegant** | Uma `refine_routing` só se o pedido não for claramente aberto, e três `refine_section` (Gemini 3.8 Flash), uma por direção. |
