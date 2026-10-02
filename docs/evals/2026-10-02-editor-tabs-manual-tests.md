# Testes manuais das tabs Content, Structure e Images

Lista para testar à mão as tabs refeitas do editor visual, com o resultado esperado. Corre-se no **demo-ai-lab**, nunca num site de cliente.

**Antes de começar**
- No manager, faz **Stop** e depois **Start** do `demo-ai-lab`, para o servidor ler o código novo.
- Abre http://localhost:8134/pt/?edit=v2 num separador novo.
- Depois de cada teste que muda o site, usa **Undo** (barra de cima) ou **Discard** para deixar o demo como estava.

**Como marcar:** `[x]` passou · `[!]` passou com reparos (escreve-os por baixo) · `[ ]` falhou.

---

## 1. Content: secção

| ✓ | Ação | Resultado esperado |
|---|---|---|
| [ ] | Sem nada selecionado, abre a tab **Content** | Lista as secções da página pelo nome, cada uma com uma descrição ("Title + 2 texts + button + photo"). Clicar numa seleciona-a. |
| [ ] | Clica na secção **Eventos** | Aparece "Page › Eventos", o título **Eventos** e a descrição. Por baixo, um formulário com Eyebrow, Heading, Text, Text, Button, Button e Image, pela ordem da página. |
| [ ] | Passa o rato por um campo | O elemento correspondente fica destacado a azul na página. |
| [ ] | Escreve no campo **Heading** | O título muda na página enquanto escreves. **Save** grava só em PT. |
| [ ] | Olha por baixo de cada campo | Mostra "EN …" com o texto em inglês, ou "EN missing" se faltar. |
| [ ] | Numa secção com um parágrafo que tem negrito ou um link | Esse campo não é editável e diz "Has formatting". **Edit on the page** começa a edição na página e mantém a formatação. |

## 2. Content: título

| ✓ | Ação | Resultado esperado |
|---|---|---|
| [ ] | Clica no título de **Eventos** | Mostra o texto com contagem de caracteres, **Level** (H1 H2 H3 H4 Text) com H2 ativo, e "Also in this block" com chips. |
| [ ] | Carrega em **H3** | A página recarrega com o título em H3, em PT e EN (a letra pode mudar com o estilo de H3). **Undo** volta a H2. |
| [ ] | Carrega em **H1** | Aparece o aviso "This page already has an H1". |

## 3. Content: botão e link

| ✓ | Ação | Resultado esperado |
|---|---|---|
| [ ] | Clica no botão **968 070 776** | Mostra **Label**, **Goes to** com **Phone** ativo, o link `tel:+351…`, **Open in a new tab** e **Advanced**. |
| [ ] | **Goes to → Page → Reservas**, depois **Save** | Em PT o link fica `/pt/reservas/`. Muda para **EN**: o mesmo botão aponta para `/en/book-a-table/`. |
| [ ] | **Goes to → WhatsApp**, com número e primeira mensagem | O link fica `https://wa.me/351…?text=…`. |
| [ ] | **Open in a new tab** | Ao gravar, o link abre num separador novo (`target="_blank"`). |

## 4. Content: imagem

| ✓ | Ação | Resultado esperado |
|---|---|---|
| [ ] | Clica na foto de **Eventos** | Aparecem a pré-visualização com "847 × 635 · sharp at this size", **Replace**, **Upload** (e **Unsplash** se estiver ligado), o alt com contador /125, **Describe the photo**, **Focus point** e **Advanced**. |
| [ ] | **Upload** | Abre o seletor de imagens já no separador Upload. |
| [ ] | **Describe the photo** | Ao fim de poucos segundos o alt em PT fica preenchido (falta gravar) e aparece "also saved EN". A linha EN mostra o texto novo. |
| [ ] | **Focus point → Top** | A foto, se estiver recortada, mostra a parte de cima. Ao gravar, a classe `object-top` fica em todas as línguas. |

## 5. Structure

| ✓ | Ação | Resultado esperado |
|---|---|---|
| [ ] | Abre **Structure** | Mostra o título da página e "N sections", a pesquisa, Header no topo e Footer no fim. Cada secção aparece pelo nome, com a descrição. |
| [ ] | Com algo selecionado em Eventos | **Eventos** está aberta e mostra Eyebrow, Heading, Text, Button e Image com o texto (e miniatura nas imagens). O item selecionado fica destacado. |
| [ ] | Escreve `grupos` na pesquisa | Ficam só as secções com esse nome ou com esse texto lá dentro. |
| [ ] | Passa o rato numa secção | Aparecem ↑ ↓, duplicar, olho (esconder em mobile) e lixo. Entre secções aparece "+ Add section". |
| [ ] | Arrasta **Contactos** pela pega para cima de **Eventos** | Aparece uma linha azul no sítio. Ao largar, a página recarrega com Contactos antes de Eventos, em PT e EN, e com Undo. |
| [ ] | Olho numa secção, depois **Save** | A secção fica com "hidden on mobile". No preview Mobile não aparece; no Desktop continua visível. |

## 6. Images

| ✓ | Ação | Resultado esperado |
|---|---|---|
| [ ] | Abre **Images** | Mostra "Images on this page N" e os filtros com contagem (só aparecem os que têm problemas). As fotos estão agrupadas por secção, com o alt como legenda. |
| [ ] | Apaga o alt de uma foto (Content) e volta a **Images** | Aparece o filtro "No alt text 1", e a foto tem a etiqueta "No alt" e a legenda a âmbar. |
| [ ] | Clica numa foto | A foto fica selecionada na página e abre-se um cartão com o alt, **Replace…**, **Describe the photo** e **Show on page**. |
| [ ] | Numa secção com placeholders de IA | Aparece "Generate N placeholder(s)", que abre o processamento de imagens dessa secção. |
